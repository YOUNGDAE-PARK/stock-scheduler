#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/stock_scheduler}"
RELEASE_ARCHIVE="${RELEASE_ARCHIVE:-/tmp/stock_scheduler-release.tar.gz}"
ENV_FILE="${ENV_FILE:-/tmp/stock_scheduler.env}"
CODEX_AUTH_FILE="${CODEX_AUTH_FILE:-/tmp/codex-auth.json}"
DEPLOY_COMPOSE_FILE="${DEPLOY_COMPOSE_FILE:-docker-compose.oracle-lite.yml}"

mkdir -p "$APP_DIR"
tar -xzf "$RELEASE_ARCHIVE" -C "$APP_DIR"

if [[ ! -s "$ENV_FILE" ]]; then
  echo "Missing env file: $ENV_FILE" >&2
  exit 1
fi
mv "$ENV_FILE" "$APP_DIR/.env"
chmod 600 "$APP_DIR/.env"

mkdir -p "$APP_DIR/secrets/codex"
if [[ -s "$CODEX_AUTH_FILE" ]]; then
  mv "$CODEX_AUTH_FILE" "$APP_DIR/secrets/codex/auth.json"
  chmod 600 "$APP_DIR/secrets/codex/auth.json"
elif [[ ! -s "$APP_DIR/secrets/codex/auth.json" ]]; then
  echo "Missing Codex auth.json. Set GitHub Secret CODEX_AUTH_JSON or upload $APP_DIR/secrets/codex/auth.json manually." >&2
  exit 1
fi

cd "$APP_DIR"
if [[ ! -f "$DEPLOY_COMPOSE_FILE" ]]; then
  echo "Missing compose file: $DEPLOY_COMPOSE_FILE" >&2
  exit 1
fi

if docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose)
else
  COMPOSE=(docker-compose)
fi

"${COMPOSE[@]}" -f "$DEPLOY_COMPOSE_FILE" up -d --build
docker image prune -f >/dev/null
"${COMPOSE[@]}" -f "$DEPLOY_COMPOSE_FILE" ps
