#!/usr/bin/env bash
# Read-only host checks for DGX Spark (also runs on any Linux docker host).
#   scripts/spark-preflight.sh [--json <output-file>]
set -uo pipefail

JSON_OUT=""
[[ "${1:-}" == "--json" ]] && JSON_OUT="${2:-}"

MODEL_ROOT="${MODEL_ROOT:-/data/models}"
FAILS=0
declare -a ROWS=()

ok()   { printf '  [ OK ] %s\n' "$1"; ROWS+=("ok|$1"); }
warn() { printf '  [WARN] %s\n' "$1"; ROWS+=("warn|$1"); }
fail() { printf '  [FAIL] %s\n' "$1"; ROWS+=("fail|$1"); FAILS=$((FAILS+1)); }
section() { printf '\n== %s\n' "$1"; }

section "host"
ARCH="$(uname -m)"
[[ "$ARCH" == "aarch64" ]] && ok "arch: $ARCH" || warn "arch: $ARCH (DGX Spark is aarch64)"
ok "kernel: $(uname -r)"
[[ -r /etc/os-release ]] && ok "os: $(. /etc/os-release; echo "$PRETTY_NAME")"
ok "user: $(id -un) uid=$(id -u) groups=$(id -Gn | tr ' ' ',')"

section "docker"
if command -v docker >/dev/null; then
  if docker info >/dev/null 2>&1; then
    ok "docker: $(docker version --format '{{.Server.Version}}')"
    RUNTIMES="$(docker info --format '{{range $k,$v := .Runtimes}}{{$k}} {{end}}')"
    [[ "$RUNTIMES" == *nvidia* ]] && ok "runtimes: $RUNTIMES" || warn "nvidia runtime not listed: $RUNTIMES (CDI/--gpus may still work)"
    docker compose version >/dev/null 2>&1 && ok "compose: $(docker compose version --short)" || fail "docker compose plugin missing"
  else
    fail "docker daemon not accessible by $(id -un) (add user to docker group?)"
  fi
else
  fail "docker not installed"
fi

section "nvidia"
if command -v nvidia-smi >/dev/null; then
  if Q="$(nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader 2>&1)"; then
    ok "gpu: $Q"
  else
    fail "nvidia-smi failed: $Q"
  fi
  command -v nvidia-ctk >/dev/null && ok "nvidia-ctk: $(nvidia-ctk --version 2>/dev/null | head -n1)" || warn "nvidia-ctk not found"
else
  fail "nvidia-smi not found"
fi

section "memory (unified)"
MEM_TOTAL_GB=$(awk '/MemTotal/ {printf "%.1f", $2/1048576}' /proc/meminfo)
MEM_AVAIL_GB=$(awk '/MemAvailable/ {printf "%.1f", $2/1048576}' /proc/meminfo)
SWAP_GB=$(awk '/SwapTotal/ {printf "%.1f", $2/1048576}' /proc/meminfo)
ok "MemTotal ${MEM_TOTAL_GB} GB, MemAvailable ${MEM_AVAIL_GB} GB, Swap ${SWAP_GB} GB"

section "disk"
while read -r line; do ok "$line"; done < <(df -h --output=target,size,used,avail,pcent -x tmpfs -x devtmpfs -x overlay -x squashfs 2>/dev/null | tail -n +2)
DOCKER_ROOT="$(docker info --format '{{.DockerRootDir}}' 2>/dev/null || echo /var/lib/docker)"
ok "docker root: $DOCKER_ROOT ($(df -h --output=avail "$DOCKER_ROOT" 2>/dev/null | tail -n1 | tr -d ' ') free)"

section "MODEL_ROOT"
if [[ -d "$MODEL_ROOT" ]]; then
  ok "$MODEL_ROOT exists (owner $(stat -c '%u:%g %a' "$MODEL_ROOT"), free $(df -h --output=avail "$MODEL_ROOT" | tail -n1 | tr -d ' '))"
  [[ -r "$MODEL_ROOT" && -x "$MODEL_ROOT" ]] && ok "readable by $(id -un)" || fail "not readable by $(id -un)"
  [[ -w "$MODEL_ROOT" ]] && ok "writable by $(id -un)" || warn "not writable by $(id -un) (needed for downloads)"
  N=$(find "$MODEL_ROOT" -mindepth 2 -maxdepth 2 -name config.json 2>/dev/null | wc -l)
  ok "models with config.json: $N"
else
  fail "$MODEL_ROOT does not exist (sudo mkdir -p $MODEL_ROOT && sudo chown $(id -un): $MODEL_ROOT)"
fi
HF_CACHE="${HF_HOME:-$HOME/.cache/huggingface}/hub"
[[ -d "$HF_CACHE" ]] && ok "HF cache: $HF_CACHE ($(ls -1d "$HF_CACHE"/models--* 2>/dev/null | wc -l) repos)" || ok "HF cache: none at $HF_CACHE"

section "network"
for url in https://registry-1.docker.io/v2/ https://huggingface.co https://docker.litellm.ai; do
  code=$(curl -s -o /dev/null -m 10 -w '%{http_code}' "$url" || echo 000)
  [[ "$code" != "000" ]] && ok "reach $url ($code)" || warn "cannot reach $url"
done
for p in 4000 8000; do
  if command -v ss >/dev/null && ss -ltn "( sport = :$p )" | grep -q LISTEN; then warn "port $p in use"; else ok "port $p free"; fi
done

section "summary"
if [[ $FAILS -eq 0 ]]; then echo "  preflight OK"; else echo "  preflight: $FAILS failure(s)"; fi

if [[ -n "$JSON_OUT" ]]; then
  {
    echo "{"
    echo "  \"timestamp\": \"$(date -Iseconds)\","
    echo "  \"failures\": $FAILS,"
    echo "  \"checks\": ["
    n=${#ROWS[@]}
    for i in "${!ROWS[@]}"; do
      lvl="${ROWS[$i]%%|*}"; msg="${ROWS[$i]#*|}"
      msg="${msg//\\/\\\\}"; msg="${msg//\"/\\\"}"
      sep=","; [[ $i -eq $((n-1)) ]] && sep=""
      echo "    {\"level\": \"$lvl\", \"message\": \"$msg\"}$sep"
    done
    echo "  ],"
    echo "  \"nvidia_smi\": $(nvidia-smi 2>&1 | python3 -c 'import json,sys;print(json.dumps(sys.stdin.read()))' 2>/dev/null || echo '""'),"
    echo "  \"meminfo\": $(python3 -c 'import json;print(json.dumps(open("/proc/meminfo").read()))' 2>/dev/null || echo '""')"
    echo "}"
  } > "$JSON_OUT"
  echo "  saved: $JSON_OUT"
fi

[[ $FAILS -eq 0 ]]
