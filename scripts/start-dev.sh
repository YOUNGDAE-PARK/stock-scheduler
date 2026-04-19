#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT_DIR/.runlogs"
BACKEND_LOG="$LOG_DIR/backend.log"
FRONTEND_LOG="$LOG_DIR/frontend.log"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
HOST_IP="${HOST_IP:-10.0.0.2}"

mkdir -p "$LOG_DIR"

is_listening() {
  local port="$1"
  ss -ltn | awk '{print $4}' | grep -Eq "(:|\\])${port}$"
}

start_backend() {
  if is_listening "$BACKEND_PORT"; then
    echo "backend already listening on :$BACKEND_PORT"
    return
  fi

  echo "starting backend on :$BACKEND_PORT"
  cd "$ROOT_DIR"
  nohup .venv/bin/uvicorn backend.app.main:app --host 0.0.0.0 --port "$BACKEND_PORT" >> "$BACKEND_LOG" 2>&1 &
}

start_frontend() {
  if is_listening "$FRONTEND_PORT"; then
    echo "frontend already listening on :$FRONTEND_PORT"
    return
  fi

  echo "starting frontend on :$FRONTEND_PORT"
  cd "$ROOT_DIR/frontend"
  nohup npm run dev -- --host 0.0.0.0 --port "$FRONTEND_PORT" >> "$FRONTEND_LOG" 2>&1 &
}

wait_for_port() {
  local name="$1"
  local port="$2"
  for _ in {1..20}; do
    if is_listening "$port"; then
      echo "$name ready on :$port"
      return
    fi
    sleep 0.5
  done
  echo "$name did not start on :$port. Check logs." >&2
  return 1
}

start_backend
start_frontend
wait_for_port backend "$BACKEND_PORT"
wait_for_port frontend "$FRONTEND_PORT"

echo
echo "Local:"
echo "  frontend  http://localhost:$FRONTEND_PORT"
echo "  backend   http://localhost:$BACKEND_PORT/api/health"
echo
echo "Phone on same network:"
echo "  frontend  http://$HOST_IP:$FRONTEND_PORT"
echo "  backend   http://$HOST_IP:$BACKEND_PORT/api/health"
echo
echo "Logs:"
echo "  backend   $BACKEND_LOG"
echo "  frontend  $FRONTEND_LOG"
echo
echo "If phone access fails, run the Windows portproxy/firewall commands in an Administrator PowerShell."
