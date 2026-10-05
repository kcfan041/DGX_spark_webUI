#!/usr/bin/env bash
# DGX Spark smoke test orchestrator.
#   ./smoke/run-smoke.sh --init      create smoke/.env with random secrets
#   ./smoke/run-smoke.sh             run preflight + smoke test
#   ./smoke/run-smoke.sh --down      remove smoke gateway, network, volume
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
ENV_FILE="$HERE/.env"
COMPOSE=(docker compose --env-file "$ENV_FILE" -f "$HERE/compose.smoke.yaml")
RUNNER_IMAGE="dgxsp/smoke-runner:dev"
MOCK_IMAGE="dgxsp/mock-vllm:dev"

rand() { head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n'; }

case "${1:-}" in
  --init)
    if [[ -f "$ENV_FILE" ]]; then echo "smoke/.env already exists"; exit 0; fi
    sed -e "s|^LITELLM_MASTER_KEY=.*|LITELLM_MASTER_KEY=sk-$(rand)|" \
        -e "s|^LITELLM_SALT_KEY=.*|LITELLM_SALT_KEY=sk-$(rand)|" \
        -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(rand)|" \
        "$HERE/.env.example" > "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    echo "created smoke/.env - review MODEL_ROOT / SMOKE_MODEL_DIR before running"
    exit 0 ;;
  --down)
    "${COMPOSE[@]}" down -v --remove-orphans
    exit 0 ;;
esac

[[ -f "$ENV_FILE" ]] || { echo "smoke/.env missing - run: $0 --init"; exit 1; }
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

PROFILE="${SMOKE_PROFILE:-spark}"
RESULTS="$HERE/results"
mkdir -p "$RESULTS"
STAMP="$(date +%Y%m%d-%H%M%S)"

echo "== preflight"
bash "$ROOT/scripts/spark-preflight.sh" --json "$RESULTS/preflight-$STAMP.json" || {
  echo "preflight reported problems (see above). Continue anyway? [y/N]"; read -r ans; [[ "$ans" == "y" ]] || exit 1; }

[[ -f "$MODEL_ROOT/$SMOKE_MODEL_DIR/config.json" ]] || {
  echo "model not found: $MODEL_ROOT/$SMOKE_MODEL_DIR (use scripts/download-model.sh)"; exit 1; }

echo "== build runner"
docker build -q -t "$RUNNER_IMAGE" -f "$HERE/runner/Dockerfile" "$HERE" >/dev/null
if [[ "$PROFILE" == "dev" ]]; then
  docker build -q -t "$MOCK_IMAGE" "$ROOT/mock-vllm" >/dev/null
fi

cleanup() {
  if [[ "${SMOKE_KEEP_GATEWAY:-0}" != "1" ]]; then
    echo "== stop gateway"
    "${COMPOSE[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

echo "== start gateway (LiteLLM + Postgres)"
"${COMPOSE[@]}" up -d

echo "== run smoke ($PROFILE)"
set +e
docker run --rm \
  --name dgxsp-smoke-runner \
  --network dgxsp-smoke \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v "$MODEL_ROOT:/host-models:ro" \
  -v "$RESULTS:/results" \
  --env-file "$ENV_FILE" \
  -e LITELLM_URL=http://litellm:4000 \
  -e SMOKE_STAMP="$STAMP" \
  "$RUNNER_IMAGE" --profile "$PROFILE"
rc=$?
set -e

echo "== gateway log tail"
"${COMPOSE[@]}" logs --tail 40 litellm > "$RESULTS/litellm-$STAMP.log" 2>&1 || true
echo "saved: $RESULTS/litellm-$STAMP.log"
exit $rc
