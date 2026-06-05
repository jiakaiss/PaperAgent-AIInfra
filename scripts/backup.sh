#!/usr/bin/env sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT_DIR"

DB_PATH="${DB_PATH:-deploy/data/paper_agent.db}"
BACKUP_DIR="${BACKUP_DIR:-deploy/backups}"

if [ ! -f "$DB_PATH" ]; then
  echo "Database not found: $DB_PATH" >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_PATH="$BACKUP_DIR/paper_agent-$STAMP.db"

if command -v sqlite3 >/dev/null 2>&1; then
  sqlite3 "$DB_PATH" ".backup '$BACKUP_PATH'"
else
  cp "$DB_PATH" "$BACKUP_PATH"
  [ -f "$DB_PATH-wal" ] && cp "$DB_PATH-wal" "$BACKUP_PATH-wal"
  [ -f "$DB_PATH-shm" ] && cp "$DB_PATH-shm" "$BACKUP_PATH-shm"
fi

echo "Backup written: $BACKUP_PATH"
