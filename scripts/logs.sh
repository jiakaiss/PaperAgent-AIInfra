#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

SERVICE="${1:-}"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is not installed or not in PATH." >&2
  exit 1
fi

if [ -n "$SERVICE" ]; then
  exec docker compose logs -f "$SERVICE"
fi

exec docker compose logs -f
