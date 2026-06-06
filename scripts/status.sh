#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

WEB_URL="${WEB_URL:-http://127.0.0.1:${WEB_PORT:-8000}}"

if command -v docker >/dev/null 2>&1 && [ -f docker-compose.yml ]; then
  echo "Docker Compose services:"
  docker compose ps
  echo
fi

echo "Web health: $WEB_URL/health"
if command -v curl >/dev/null 2>&1; then
  if curl -fsS "$WEB_URL/health"; then
    echo
    echo "Web health check passed."
  else
    echo
    echo "Web health check failed." >&2
    exit 1
  fi
else
  echo "curl not found; skipping HTTP health check."
fi
