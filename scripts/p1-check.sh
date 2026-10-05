#!/usr/bin/env bash
# P1 end-to-end check against a running platform (deploy/compose.yaml).
#   scripts/p1-check.sh [model-dir-name]      default: Qwen2.5-0.5B-Instruct
# Creates a model service, waits for READY, tests via LiteLLM, restarts, stops, deletes.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT/deploy/.env"
[[ -f "$ENV_FILE" ]] || { echo "deploy/.env missing"; exit 1; }
TOKEN="$(grep '^DGXSP_ADMIN_TOKEN=' "$ENV_FILE" | cut -d= -f2-)"
PORT="$(grep '^WEB_PORT=' "$ENV_FILE" | cut -d= -f2- || true)"
BASE="http://127.0.0.1:${PORT:-8088}/api/v1"
MODEL="local:${1:-Qwen2.5-0.5B-Instruct}"
NAME="p1-check"
OUT="$ROOT/smoke/results/p1-check-$(date +%Y%m%d-%H%M%S).log"
mkdir -p "$(dirname "$OUT")"
exec > >(tee "$OUT") 2>&1

api() {
  local method="$1" path="$2" body="${3:-}"
  if [[ -n "$body" ]]; then
    curl -sS -X "$method" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d "$body" "$BASE$path"
  else
    curl -sS -X "$method" -H "Authorization: Bearer $TOKEN" "$BASE$path"
  fi
}
field() { python3 -c "import json,sys;d=json.load(sys.stdin);print(eval('d'+sys.argv[1]))" "$1"; }

wait_ready() {
  local id="$1" t0=$SECONDS
  while (( SECONDS - t0 < 1200 )); do
    local j st gw ph
    j="$(api GET "/instances/$id")"
    st="$(echo "$j" | field "['status']")"; gw="$(echo "$j" | field "['gateway_state']")"; ph="$(echo "$j" | field "['phase']")"
    printf '\r  %4ss status=%-8s phase=%-11s gateway=%-10s' "$((SECONDS - t0))" "$st" "$ph" "$gw"
    if [[ "$st" == "ERROR" ]]; then echo; echo "$j" | python3 -m json.tool; return 1; fi
    if [[ "$st" == "READY" && "$gw" != "pending" ]]; then echo; return 0; fi
    sleep 3
  done
  echo; echo "timeout"; return 1
}

COMPOSE=(docker compose --env-file "$ENV_FILE" -f "$ROOT/deploy/compose.yaml")

diagnose() {
  echo "== diagnostics"
  "${COMPOSE[@]}" ps -a || true
  for svc in backend web litellm; do
    echo "--- $svc logs (last 40)"
    "${COMPOSE[@]}" logs --tail 40 "$svc" 2>&1 || true
  done
}

echo "== wait for platform ($BASE)"
t0=$SECONDS
until curl -sf -o /dev/null "http://127.0.0.1:${PORT:-8088}/" && \
      [[ "$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $TOKEN" "$BASE/auth/me")" == "200" ]]; do
  if (( SECONDS - t0 > 180 )); then
    echo "platform not reachable after 180s"
    diagnose
    exit 1
  fi
  sleep 3
done
echo "  ready after $((SECONDS - t0))s"

echo "== system"
api GET /system/summary | python3 -m json.tool | head -n 40
echo "== models"
api GET /models | python3 -c "import json,sys;[print(' ',m['id'],m['size_bytes'],m['max_context']) for m in json.load(sys.stdin)]"

echo "== cleanup old $NAME"
OLD="$(api GET /instances | python3 -c "import json,sys;print(' '.join(i['id'] for i in json.load(sys.stdin) if i['served_model_name']=='$NAME'))")"
for id in $OLD; do api POST "/instances/$id/stop" >/dev/null || true; api DELETE "/instances/$id" >/dev/null || true; done

echo "== preview"
api POST /instances/preview "{\"model_id\":\"$MODEL\",\"preset\":\"low_memory\",\"served_model_name\":\"$NAME\",\"params\":{\"gpu_memory_utilization\":0.3,\"max_model_len\":4096}}" \
  | python3 -c "import json,sys;p=json.load(sys.stdin);print('  blocking',p['blocking']);print('  warnings',[w['code'] for w in p['warnings']]);print('  estimate',p['estimate']);print('  command',' '.join(p['command']))"

echo "== create + start"
ID="$(api POST /instances "{\"model_id\":\"$MODEL\",\"preset\":\"low_memory\",\"served_model_name\":\"$NAME\",\"params\":{\"gpu_memory_utilization\":0.3,\"max_model_len\":4096},\"start\":true}" | field "['id']")"
echo "  id=$ID"
wait_ready "$ID"

echo "== test via LiteLLM"
api POST "/instances/$ID/test" '{"content":"用一句話介紹你自己"}' | python3 -m json.tool

echo "== gateway models"
api GET /gateway/models | python3 -m json.tool

echo "== logs (last 5, noise filtered)"
api GET "/instances/$ID/logs?tail=200" | python3 -c "import json,sys;[print(' ',l['text'][:160]) for l in json.load(sys.stdin)['lines'][-5:]]"

echo "== restart"
api POST "/instances/$ID/restart" >/dev/null
wait_ready "$ID"
api POST "/instances/$ID/test" '{"content":"hi"}' | field "['ok']"

echo "== stop"
api POST "/instances/$ID/stop" | python3 -c "import json,sys;d=json.load(sys.stdin);print('  status',d['status'],'gateway',d['gateway_state'])"
echo "  gateway models after stop: $(api GET /gateway/models | python3 -c 'import json,sys;print(len(json.load(sys.stdin)))')"

echo "== events"
api GET "/instances/$ID/events" | python3 -c "import json,sys;print('  '+' > '.join(e['type'] for e in reversed(json.load(sys.stdin))))"

echo "== delete"
api DELETE "/instances/$ID"
echo "  managed containers left: $(docker ps -aq --filter label=dgxsp.managed=true | wc -l)"
echo
echo "P1 CHECK PASS  (log: $OUT)"
