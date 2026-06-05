#!/usr/bin/env sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -f .env ]; then
  echo "Missing .env. Copy .env.example to .env and fill required values." >&2
  exit 1
fi

if [ ! -f deploy/config/config.yaml ]; then
  echo "Missing deploy/config/config.yaml. Copy deploy/config/config.yaml.example first." >&2
  exit 1
fi

mkdir -p deploy/data deploy/logs deploy/backups

if command -v docker >/dev/null 2>&1; then
  DOCKER_COMPOSE="docker compose"
else
  echo "Docker is not installed or not in PATH." >&2
  exit 1
fi

echo "Running doctor checks..."
$DOCKER_COMPOSE build web
$DOCKER_COMPOSE run --rm web paper-agent doctor -c /app/config.yaml

echo "Starting services..."
$DOCKER_COMPOSE up -d

echo "Deployment complete. Check logs with: docker compose logs -f"
