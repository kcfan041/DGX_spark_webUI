#!/usr/bin/env bash
# Read-only health diagnosis for the platform stack. Never prints secrets.
#   scripts/doctor.sh
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT/deploy/.env"
COMPOSE=(docker compose --env-file "$ENV_FILE" -f "$ROOT/deploy/compose.yaml")
FAILS=0
ok()   { printf '  [ OK ] %s\n' "$*"; }
warn() { printf '  [WARN] %s\n' "$*"; }
bad()  { printf '  [FAIL] %s\n' "$*"; FAILS=$((FAILS + 1)); }
fix()  { printf '         fix: %s\n' "$*"; }
section() { printf '\n== %s\n' "$1"; }
envval() { grep "^$1=" "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true; }
fp() { printf '%s' "$1" | sha256sum | cut -c1-8; }

[[ -f "$ENV_FILE" ]] || { echo "deploy/.env missing (run scripts/init-env.sh)"; exit 1; }

section "containers"
"${COMPOSE[@]}" ps -a --format 'table {{.Service}}\t{{.Status}}' 2>/dev/null | sed 's/^/  /'
for svc in db litellm backend web; do
  st="$("${COMPOSE[@]}" ps -a --format '{{.Service}} {{.State}}' 2>/dev/null | awk -v s="$svc" '$1==s {print $2}')"
  case "$st" in
    running) ok "$svc running" ;;
    "") bad "$svc container missing"; fix "${COMPOSE[*]} up -d" ;;
    *) bad "$svc is $st" ;;
  esac
  info="$(docker inspect "dgxsp-$svc-1" --format '{{.RestartCount}}|{{.State.StartedAt}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}-{{end}}' 2>/dev/null || true)"
  if [[ -n "$info" ]]; then
    IFS='|' read -r restarts started health <<< "$info"
    printf '         restarts=%s started=%s health=%s\n' "$restarts" "${started%.*}" "$health"
    if [[ "$restarts" =~ ^[0-9]+$ ]] && (( restarts > 0 )); then
      warn "$svc has restarted $restarts time(s) since it was created (check: ${COMPOSE[*]} logs --tail 100 $svc)"
    fi
  fi
done

section "shell environment overrides"
for v in POSTGRES_PASSWORD LITELLM_MASTER_KEY LITELLM_SALT_KEY DGXSP_ADMIN_TOKEN; do
  if [[ -n "${!v:-}" ]]; then
    bad "$v is exported in this shell; docker compose uses it INSTEAD of deploy/.env"
    fix "unset $v   (and remove it from ~/.bashrc / ~/.profile if present)"
  fi
done
[[ $FAILS -eq 0 ]] && ok "no overriding variables in this shell"

section "database password"
ENV_PW="$(envval POSTGRES_PASSWORD)"
if docker exec -e PGPASSWORD="$ENV_PW" dgxsp-db-1 psql -h 127.0.0.1 -U litellm -d litellm -tAc 'select 1' >/dev/null 2>&1; then
  ok "deploy/.env POSTGRES_PASSWORD can log in to the database"
else
  bad "deploy/.env POSTGRES_PASSWORD is rejected by the database"
  fix "docker exec dgxsp-db-1 psql -U litellm -d litellm -c \"ALTER USER litellm WITH PASSWORD '<value from deploy/.env>';\""
fi
URL="$(docker inspect dgxsp-litellm-1 --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null | sed -n 's/^DATABASE_URL=//p')"
if [[ -z "$URL" ]]; then
  warn "cannot read DATABASE_URL from litellm container"
else
  C_PW="$(printf '%s' "$URL" | sed -E 's#^[a-z]+://[^:]+:([^@]*)@.*#\1#')"
  C_HOST="$(printf '%s' "$URL" | sed -E 's#^.*@([^:/]+).*#\1#')"
  if [[ "$C_PW" == "$ENV_PW" ]]; then
    ok "litellm container uses the same DB password as deploy/.env (fingerprint $(fp "$C_PW"))"
  else
    bad "litellm container was created with a DIFFERENT DB password (container $(fp "$C_PW") vs .env $(fp "$ENV_PW"))"
    fix "${COMPOSE[*]} up -d --force-recreate litellm"
  fi
  ok "litellm DATABASE_URL host = $C_HOST"
  RESOLVED="$(docker run --rm --network dgxsp busybox nslookup "$C_HOST" 2>/dev/null | awk '/^Address/ {print $NF}' | tail -n +2 | tr '\n' ' ')"
  DB_IP="$(docker inspect dgxsp-db-1 --format '{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}' 2>/dev/null)"
  echo "         '$C_HOST' resolves to: ${RESOLVED:-?}  | dgxsp-db-1 IP: ${DB_IP:-?}"
  OTHERS="$(docker network inspect dgxsp --format '{{range .Containers}}{{.Name}} {{end}}' 2>/dev/null)"
  echo "         containers on network dgxsp: $OTHERS"
fi

section "database auth errors (last 24h, newest 15)"
AUTH_ERR="$(docker logs --since 24h --timestamps dgxsp-db-1 2>&1 | grep -E 'FATAL|DETAIL|authentication' | tail -n 15)"
if [[ -n "$AUTH_ERR" ]]; then
  printf '%s\n' "$AUTH_ERR" | sed 's/^/  /'
  warn "database rejected logins in the last 24h (see above)"
else
  ok "no authentication errors in the last 24h"
fi

section "litellm"
R="$(curl -s -m 5 "http://127.0.0.1:$(envval GATEWAY_PORT | sed 's/^$/4000/')/health/readiness" || true)"
case "$R" in
  *'"db":"connected"'*) ok "gateway ready, database connected" ;;
  "") bad "gateway not responding on port $(envval GATEWAY_PORT)" ;;
  *) bad "gateway responding but not ready: ${R:0:200}" ;;
esac
"${COMPOSE[@]}" logs --tail 200 litellm 2>/dev/null | grep -E 'P1000|P1001|Error:|ERROR' | tail -n 5 | sed 's/^/  /'

section "ports"
for p in "$(envval WEB_PORT)" "$(envval GATEWAY_PORT)"; do
  [[ -z "$p" ]] && continue
  if ss -ltn "( sport = :$p )" 2>/dev/null | grep -q LISTEN; then ok "port $p listening"; else bad "port $p not listening"; fi
done

section "summary"
if [[ $FAILS -eq 0 ]]; then echo "  all checks passed"; else echo "  $FAILS problem(s) found (see fix: lines above)"; fi
exit $(( FAILS > 0 ))
