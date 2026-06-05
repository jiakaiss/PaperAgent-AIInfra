#!/usr/bin/env sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [ $# -ne 1 ]; then
  echo "Usage: scripts/restore.sh <backup-db-file>" >&2
  exit 1
fi

BACKUP_PATH="$1"
DB_PATH="${DB_PATH:-deploy/data/paper_agent.db}"

if [ ! -f "$BACKUP_PATH" ]; then
  echo "Backup file not found: $BACKUP_PATH" >&2
  exit 1
fi

if command -v docker >/dev/null 2>&1 && [ -f docker-compose.yml ]; then
  echo "Stopping services before restore..."
  docker compose stop web daemon || true
fi

mkdir -p "$(dirname "$DB_PATH")"
cp "$BACKUP_PATH" "$DB_PATH"
rm -f "$DB_PATH-wal" "$DB_PATH-shm"

echo "Restored $BACKUP_PATH to $DB_PATH"
echo "Restart services with: docker compose up -d"
