#!/usr/bin/env bash
# Create deploy/.env with random secrets.
#   scripts/init-env.sh [spark|dev]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT/deploy/.env"
PROFILE="${1:-spark}"

if [[ -f "$ENV_FILE" ]]; then echo "deploy/.env already exists"; exit 0; fi

if docker volume inspect dgxsp-pgdata >/dev/null 2>&1; then
  cat <<'EOF'
deploy/.env is missing, but the Gateway database volume (dgxsp-pgdata) already exists.
A new .env would contain a NEW random POSTGRES_PASSWORD that the existing database does not accept,
and LiteLLM would fail with "P1000: Authentication failed".

Options:
  - restore your previous deploy/.env (recommended), or
  - start fresh (deletes all API keys stored in the Gateway):
      docker compose -f deploy/compose.yaml down
      docker volume rm dgxsp-pgdata
      scripts/init-env.sh
EOF
  exit 1
fi

rand() { head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n'; }
HOST_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
WEB_PORT="$(grep '^WEB_PORT=' "$ROOT/deploy/.env.example" | cut -d= -f2)"

MODEL_ROOT_DEFAULT="$(grep '^MODEL_ROOT=' "$ROOT/deploy/.env.example" | cut -d= -f2)"
OWNER_UID="$(stat -c '%u' "$MODEL_ROOT_DEFAULT" 2>/dev/null || id -u)"
OWNER_GID="$(stat -c '%g' "$MODEL_ROOT_DEFAULT" 2>/dev/null || id -g)"

sed -e "s|^DGXSP_PROFILE=.*|DGXSP_PROFILE=$PROFILE|" \
    -e "s|^MODEL_OWNER_UID=.*|MODEL_OWNER_UID=$OWNER_UID|" \
    -e "s|^MODEL_OWNER_GID=.*|MODEL_OWNER_GID=$OWNER_GID|" \
    -e "s|^DGXSP_ADMIN_TOKEN=.*|DGXSP_ADMIN_TOKEN=$(rand)|" \
    -e "s|^LITELLM_MASTER_KEY=.*|LITELLM_MASTER_KEY=sk-$(rand)|" \
    -e "s|^LITELLM_SALT_KEY=.*|LITELLM_SALT_KEY=sk-$(rand)|" \
    -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(rand)|" \
    "$ROOT/deploy/.env.example" > "$ENV_FILE"
chmod 600 "$ENV_FILE"

echo "created deploy/.env (profile=$PROFILE)"
echo "Web Console: http://${HOST_IP:-<spark-ip>}:${WEB_PORT:-8088}"
echo "admin token for Web Console login:"
grep '^DGXSP_ADMIN_TOKEN=' "$ENV_FILE" | cut -d= -f2
