#!/usr/bin/env bash
# Create deploy/.env with random secrets.
#   scripts/init-env.sh [spark|dev]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT/deploy/.env"
PROFILE="${1:-spark}"

if [[ -f "$ENV_FILE" ]]; then echo "deploy/.env already exists"; exit 0; fi

rand() { head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n'; }
HOST_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"

sed -e "s|^DGXSP_PROFILE=.*|DGXSP_PROFILE=$PROFILE|" \
    -e "s|^DGXSP_ADMIN_TOKEN=.*|DGXSP_ADMIN_TOKEN=$(rand)|" \
    -e "s|^LITELLM_MASTER_KEY=.*|LITELLM_MASTER_KEY=sk-$(rand)|" \
    -e "s|^LITELLM_SALT_KEY=.*|LITELLM_SALT_KEY=sk-$(rand)|" \
    -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(rand)|" \
    -e "s|^PUBLIC_API_BASE=.*|PUBLIC_API_BASE=http://${HOST_IP:-localhost}:4000/v1|" \
    "$ROOT/deploy/.env.example" > "$ENV_FILE"
chmod 600 "$ENV_FILE"

echo "created deploy/.env (profile=$PROFILE)"
echo "admin token for Web Console login:"
grep '^DGXSP_ADMIN_TOKEN=' "$ENV_FILE" | cut -d= -f2
