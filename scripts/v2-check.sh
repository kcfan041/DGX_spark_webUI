#!/usr/bin/env bash
# Spark validation 2.0: large model, concurrency, real startup failure, reboot + autostart.
#
#   scripts/v2-check.sh all              big + concurrent + oom + reboot-prep (then: sudo reboot)
#   scripts/v2-check.sh big              7B lifecycle, memory, load time, throughput
#   scripts/v2-check.sh concurrent       7B + 0.5B running at the same time
#   scripts/v2-check.sh oom              deliberately start 7B with too little memory
#   scripts/v2-check.sh reboot-prep      create 2 autostart services and start them
#   scripts/v2-check.sh reboot-verify    after reboot: check autostart result
#   scripts/v2-check.sh cleanup          stop + delete all v2-* services
#
# Env overrides: MODEL_BIG, MODEL_SMALL (model ids), OOM_PARAMS (JSON), GATEWAY_URL.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT/deploy/.env"
[[ -f "$ENV_FILE" ]] || { echo "deploy/.env missing"; exit 1; }
envval() { grep "^$1=" "$ENV_FILE" | cut -d= -f2- || true; }
TOKEN="$(envval DGXSP_ADMIN_TOKEN)"
WEB_PORT="$(envval WEB_PORT)"
GW_PORT="$(envval GATEWAY_PORT)"
BASE="http://127.0.0.1:${WEB_PORT:-8088}/api/v1"
GATEWAY_URL="${GATEWAY_URL:-http://127.0.0.1:${GW_PORT:-4000}/v1}"
MODEL_BIG="${MODEL_BIG:-local:Qwen2.5-7B-Instruct}"
MODEL_SMALL="${MODEL_SMALL:-local:Qwen2.5-0.5B-Instruct}"
DEFAULT_OOM_PARAMS='{"gpu_memory_utilization":0.1,"max_model_len":8192}'
OOM_PARAMS="${OOM_PARAMS:-$DEFAULT_OOM_PARAMS}"
PY="${PYTHON:-python3}"
PHASE="${1:-all}"

OUT="$ROOT/smoke/results/v2-${PHASE}-$(date +%Y%m%d-%H%M%S).log"
mkdir -p "$(dirname "$OUT")"
exec > >(tee "$OUT") 2>&1

FAILS=0
pass() { echo "  [PASS] $*"; }
fail() { echo "  [FAIL] $*"; FAILS=$((FAILS + 1)); }
section() { printf '\n==== %s (%s)\n' "$1" "$(date +%H:%M:%S)"; }

api() {
  local method="$1" path="$2" body="${3:-}"
  local args=(-sS -X "$method" -H "Authorization: Bearer $TOKEN")
  if [[ -n "$body" ]]; then
    printf '%s' "$body" | curl "${args[@]}" -H 'Content-Type: application/json; charset=utf-8' --data-binary @- "$BASE$path"
  else
    curl "${args[@]}" "$BASE$path"
  fi
}
jq_() {
  "$PY" -c "
import json,sys
raw=sys.stdin.read()
try:
    d=json.loads(raw)
except ValueError:
    print('<non-json: ' + raw[:200].replace(chr(10),' ') + '>'); sys.exit()
class G(dict):
    def __missing__(self, k): return None
if isinstance(d, dict): d=G(d)
try:
    print($1)
except Exception as e:
    print('<api error: ' + json.dumps(d, ensure_ascii=False)[:300] + '>')"
}
ok_test() { [[ "$(echo "$1" | jq_ "d['ok']")" == "True" ]]; }

preflight() {
  section "preflight"
  local r
  r="$(curl -s -m 5 "${GATEWAY_URL%/v1}/health/readiness" || true)"
  if [[ "$r" != *'"db":"connected"'* ]]; then
    echo "  [STOP] Gateway (LiteLLM) not ready or its database is not connected: ${r:-no response}"
    echo "         run: scripts/doctor.sh"
    exit 3
  fi
  if ! curl -sf -o /dev/null -H "Authorization: Bearer $TOKEN" "$BASE/auth/me"; then
    echo "  [STOP] platform API not reachable at $BASE"
    exit 3
  fi
  pass "gateway ready (db connected) and platform API reachable"
}

cleanup_all() {
  for n in v2-7b v2-small v2-oom v2-auto-small v2-auto-7b; do remove "$n"; done
}

on_exit() {
  local rc=$?
  if [[ "$PHASE" != "reboot-prep" && "$PHASE" != "reboot-verify" && "$PHASE" != "cleanup" && "$PHASE" != "all" ]]; then
    echo; echo "  (cleanup: removing v2-* services)"
    cleanup_all
  fi
  exit "$rc"
}

mem() {
  awk '/^(MemTotal|MemFree|MemAvailable|Cached):/ {printf "%s %.1fGB  ", $1, $2/1048576}' /proc/meminfo
  echo
  if command -v nvidia-smi >/dev/null; then
    nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader 2>/dev/null | sed 's/^/    gpu-proc: /' || true
  fi
}

id_of() {
  api GET /instances | "$PY" -c "import json,sys;print(next((i['id'] for i in json.load(sys.stdin) if i['served_model_name']=='$1'),''))"
}

remove() {
  local id
  id="$(id_of "$1")"
  [[ -z "$id" ]] && return 0
  api POST "/instances/$id/stop" >/dev/null 2>&1 || true
  api DELETE "/instances/$id" >/dev/null 2>&1 || true
}

# wait until READY (rc 0) or ERROR / timeout (rc 1); prints elapsed seconds in LAST_WAIT
LAST_WAIT=0
wait_status() {
  local id="$1" timeout="${2:-1500}" t0=$SECONDS j st gw ph
  while (( SECONDS - t0 < timeout )); do
    j="$(api GET "/instances/$id")"
    st="$(echo "$j" | jq_ "d['status']")"; gw="$(echo "$j" | jq_ "d['gateway_state']")"; ph="$(echo "$j" | jq_ "d['phase']")"
    printf '\r    %5ss status=%-8s phase=%-11s gateway=%-10s' "$((SECONDS - t0))" "$st" "$ph" "$gw"
    LAST_WAIT=$((SECONDS - t0))
    if [[ "$st" == "ERROR" ]]; then echo; return 1; fi
    if [[ "$st" == "READY" && "$gw" != "pending" ]]; then echo; return 0; fi
    sleep 5
  done
  echo; echo "    timeout after ${timeout}s"; return 1
}

create() { # name model preset params_json autostart order start
  api POST /instances "{\"model_id\":\"$2\",\"preset\":\"$3\",\"served_model_name\":\"$1\",\"params\":$4,\"autostart\":$5,\"autostart_order\":$6,\"start\":$7}" \
    | jq_ "d.get('id') or json.dumps(d)"
}

preview() { # model preset params
  api POST /instances/preview "{\"model_id\":\"$1\",\"preset\":\"$2\",\"params\":$3,\"served_model_name\":\"v2-preview\"}" | "$PY" -c "
import json,sys
p=json.load(sys.stdin)
if 'estimate' not in p: print('    preview error:', p); sys.exit()
e=p['estimate']; g=lambda v: 'n/a' if v is None else f'{v/2**30:.1f}GB'
print('    params:', {k:p['params'][k] for k in ('max_model_len','gpu_memory_utilization','quantization','dtype')})
print('    estimate: weights', g(e['weights_bytes']), 'kv', g(e['kv_cache_bytes']), 'total', g(e['total_bytes']),
      'budget', g(e['budget_bytes']), 'avail', g(e['system_available_bytes']), 'free', g(e['system_free_bytes']))
print('    warnings:', [(w['level'], w['code']) for w in p['warnings']])
print('    command:', ' '.join(p['command']))"
}

throughput() { # served_name
  local created key kid t0 t1 resp
  created="$(api POST /gateway/keys '{"name":"v2-check throughput"}')"
  key="$(echo "$created" | jq_ "d['key']")"
  kid="$(echo "$created" | jq_ "d['id']")"
  if [[ "$key" != sk-* ]]; then
    fail "could not create API key: ${created:0:300}"
    return
  fi
  t0=$(date +%s.%N)
  resp="$(printf '%s' "{\"model\":\"$1\",\"max_tokens\":256,\"messages\":[{\"role\":\"user\",\"content\":\"Write about 200 words introducing Taiwan.\"}]}" | curl -sS "$GATEWAY_URL/chat/completions" -H "Authorization: Bearer $key" -H 'Content-Type: application/json' --data-binary @-)"
  t1=$(date +%s.%N)
  echo "$resp" | "$PY" -c "
import json,sys
r=json.load(sys.stdin); dt=$t1-$t0
u=r.get('usage') or {}
n=u.get('completion_tokens') or 0
print(f'    256-token request: {dt:.1f}s, completion_tokens={n}, ~{n/dt:.1f} tok/s (incl. prefill + gateway)')
print('    reply:', ((r.get('choices') or [{}])[0].get('message') or {}).get('content','')[:80].replace(chr(10),' '))" \
    || echo "    throughput call failed: ${resp:0:300}"
  api POST "/gateway/keys/$kid/revoke" >/dev/null
}

# ------------------------------------------------------------------ phases

phase_big() {
  section "big: $MODEL_BIG lifecycle"
  remove v2-7b
  echo "  memory before:"; mem
  preview "$MODEL_BIG" balanced '{}'
  local id
  id="$(create v2-7b "$MODEL_BIG" balanced '{}' false 100 true)"
  echo "  id=$id"
  if wait_status "$id"; then
    pass "7B READY in ${LAST_WAIT}s (Balanced)"
  else
    fail "7B did not become READY"
    api GET "/instances/$id" | jq_ "json.dumps(d.get('last_error'), ensure_ascii=False, indent=1)"
    api GET "/instances/$id/logs?tail=60" | jq_ "'\n'.join(l['text'] for l in d['lines'])"
    return
  fi
  echo "  memory after READY:"; mem
  local t
  t="$(api POST "/instances/$id/test" '{"content":"Introduce yourself in one sentence."}')"
  echo "    test: $t"
  ok_test "$t" && pass "test via LiteLLM" || fail "test via LiteLLM"
  throughput v2-7b
  echo "  vLLM memory lines from log:"
  api GET "/instances/$id/logs?tail=2000" | "$PY" -c "
import json,re,sys
for l in json.load(sys.stdin)['lines']:
    if re.search(r'(KV cache|Memory profiling|model weights took|Available KV|GPU blocks|Maximum concurrency|took .* GiB|CUDA graph)', l['text'], re.I):
        print('    ', l['text'][:220])"
}

phase_concurrent() {
  section "concurrent: 7B + 0.5B"
  local big small
  big="$(id_of v2-7b)"
  if [[ -z "$big" ]]; then
    big="$(create v2-7b "$MODEL_BIG" balanced '{}' false 100 true)"
    wait_status "$big" || { fail "7B not READY"; return; }
  fi
  remove v2-small
  preview "$MODEL_SMALL" low_memory '{"gpu_memory_utilization":0.15}'
  small="$(create v2-small "$MODEL_SMALL" low_memory '{"gpu_memory_utilization":0.15}' false 100 true)"
  if wait_status "$small"; then pass "0.5B READY next to 7B in ${LAST_WAIT}s"; else fail "0.5B failed next to 7B"; api GET "/instances/$small" | jq_ "json.dumps(d.get('last_error'), ensure_ascii=False)"; fi
  echo "  memory with both:"; mem
  for n in v2-7b v2-small; do
    local r
    r="$(api POST "/instances/$(id_of $n)/test" '{"content":"hi"}')"
    ok_test "$r" && pass "$n answers" || fail "$n test: $r"
  done
  api GET /gateway/models | jq_ "'\n'.join(f\"    gateway: {m['model_name']} sync={m['sync']}\" for m in d)"
  remove v2-small
  remove v2-7b
  sleep 5
  echo "  memory after stopping both:"; mem
}

phase_oom() {
  section "oom: $MODEL_BIG with params $OOM_PARAMS"
  remove v2-oom
  preview "$MODEL_BIG" custom "$OOM_PARAMS"
  local id
  id="$(create v2-oom "$MODEL_BIG" custom "$OOM_PARAMS" false 100 true)"
  if wait_status "$id" 900; then
    fail "expected startup failure but service became READY (budget was enough) - note for calibration"
  else
    local j
    j="$(api GET "/instances/$id")"
    echo "$j" | "$PY" -c "
import json,sys
e=json.load(sys.stdin).get('last_error') or {}
print('    code:', e.get('code'), '| exit:', (e.get('params') or {}).get('exit_code'))
print('    suggestions:', [(s['label_key'], s.get('patch')) for s in e.get('suggestions',[])])
print('    evidence:'); [print('      ', x[:240]) for x in e.get('evidence',[])]"
    [[ "$(echo "$j" | jq_ "(d.get('last_error') or {}).get('code')")" == "OOM" ]] && pass "classified as OOM" \
      || fail "not classified as OOM (see evidence above; add a pattern to configs/error-patterns.yaml)"
    echo "  full error-ish log lines (for error-patterns calibration):"
    api GET "/instances/$id/logs?tail=3000" | "$PY" -c "
import json,re,sys
lines=[l['text'] for l in json.load(sys.stdin)['lines']]
hits=[l for l in lines if re.search(r'(error|exception|memory|insufficient|cache blocks|failed)', l, re.I)]
for l in hits[-40:]: print('    ', l[:240])"
  fi
  remove v2-oom
}

phase_reboot_prep() {
  section "reboot-prep: two autostart services"
  systemctl is-enabled docker >/dev/null 2>&1 && pass "docker starts on boot ($(systemctl is-enabled docker))" \
    || fail "docker service is not enabled on boot: run 'sudo systemctl enable docker'"
  remove v2-auto-small
  remove v2-auto-7b
  local a b
  a="$(create v2-auto-small "$MODEL_SMALL" low_memory '{"gpu_memory_utilization":0.15}' true 1 true)"
  b="$(create v2-auto-7b "$MODEL_BIG" balanced '{"gpu_memory_utilization":0.5}' true 2 true)"
  wait_status "$a" && pass "auto-small READY" || fail "auto-small"
  wait_status "$b" && pass "auto-7b READY" || fail "auto-7b"
  date +%s > "$ROOT/smoke/results/.v2-reboot-start"
  cat <<'EOF'

  Both autostart services are READY. Next:
    1) sudo reboot
    2) wait 3-5 minutes, ssh in again
    3) cd ~/projects/DGX_spark_webUI && scripts/v2-check.sh reboot-verify
EOF
}

phase_reboot_verify() {
  section "reboot-verify"
  echo "  uptime: $(uptime -p)"
  local t0=$SECONDS
  until curl -sf -o /dev/null -H "Authorization: Bearer $TOKEN" "$BASE/auth/me"; do
    (( SECONDS - t0 > 600 )) && { fail "platform not reachable 10 min after boot"; docker ps -a; return; }
    sleep 5
  done
  pass "platform reachable $((SECONDS - t0))s after script start"
  local s state
  t0=$SECONDS
  while :; do
    s="$(api GET /system/autostart)"
    state="$(echo "$s" | jq_ "d['state']")"
    printf '\r    autostart state=%-9s current=%-14s results=%s' "$state" "$(echo "$s" | jq_ "d['current']")" "$(echo "$s" | jq_ "d['results']")"
    [[ "$state" == "done" || "$state" == "cancelled" || "$state" == "idle" ]] && break
    (( SECONDS - t0 > 1800 )) && break
    sleep 5
  done
  echo
  [[ "$state" == "done" ]] && pass "autostart finished in ~$((SECONDS - t0))s after platform up" || fail "autostart state=$state"
  for n in v2-auto-small v2-auto-7b; do
    local id
    id="$(id_of "$n")"
    api GET "/instances/$id/events" | jq_ "'    $n events: ' + ' > '.join(e['type'] for e in reversed(d))"
    local r
    r="$(api POST "/instances/$id/test" '{"content":"hi"}' || true)"
    ok_test "$r" && pass "$n READY and answering after reboot" || fail "$n after reboot: $r"
  done
  api GET /instances | "$PY" -c "
import json,sys
ids=[(i['served_model_name'],i['autostart_order']) for i in json.load(sys.stdin) if i['served_model_name'].startswith('v2-auto')]
print('    order:', sorted(ids, key=lambda x: x[1]))"
  echo "  memory after autostart:"; mem
}

phase_cleanup() {
  section "cleanup"
  for n in v2-7b v2-small v2-oom v2-auto-small v2-auto-7b v2-preview; do remove "$n"; done
  echo "  managed containers left: $(docker ps -aq --filter label=dgxsp.managed=true | wc -l)"
}

case "$PHASE" in
  big|concurrent|oom|all|reboot-prep) preflight ;;
esac
trap on_exit EXIT

case "$PHASE" in
  big) phase_big ;;
  concurrent) phase_concurrent ;;
  oom) phase_oom ;;
  reboot-prep) phase_reboot_prep ;;
  reboot-verify) phase_reboot_verify ;;
  cleanup) phase_cleanup ;;
  all) phase_big; phase_concurrent; phase_oom; cleanup_all; phase_reboot_prep ;;
  *) echo "unknown phase: $PHASE"; exit 2 ;;
esac

echo
if (( FAILS == 0 )); then echo "V2 $PHASE: PASS"; else echo "V2 $PHASE: $FAILS FAIL(s)"; fi
echo "log: $OUT"
