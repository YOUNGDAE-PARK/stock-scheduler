#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/stock_scheduler}"
BACKUP_DIR="${BACKUP_DIR:-$APP_DIR/backups}"
CONTAINER="${CONTAINER:-stock_scheduler-backend-1}"
STAMP="$(date +%Y%m%d-%H%M%S)"

mkdir -p "$BACKUP_DIR"
docker cp "$CONTAINER:/data/stock_scheduler.db" "$BACKUP_DIR/stock_scheduler-$STAMP.db"
find "$BACKUP_DIR" -name 'stock_scheduler-*.db' -type f -mtime +14 -delete
echo "$BACKUP_DIR/stock_scheduler-$STAMP.db"
