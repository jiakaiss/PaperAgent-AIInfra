#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-all}"
CONFIG="${CONFIG:-config.yaml}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
PYTHON_BIN="${PYTHON_BIN:-python}"

cd "$(dirname "$0")/.."
export PYTHONIOENCODING="${PYTHONIOENCODING:-utf-8}"

usage() {
  cat <<'EOF'
Usage: scripts/start-local.sh [web|daemon|all]

Environment variables:
  CONFIG      Config file path (default: config.yaml)
  HOST        Web host (default: 127.0.0.1)
  PORT        Web port (default: 8000)
  PYTHON_BIN  Python executable (default: python)

Examples:
  scripts/start-local.sh web
  scripts/start-local.sh daemon
  scripts/start-local.sh all
  PYTHON_BIN=/opt/conda/envs/paper_agent/bin/python scripts/start-local.sh all
EOF
}

start_web() {
  echo "Starting Paper Agent web UI at http://${HOST}:${PORT}"
  exec "$PYTHON_BIN" -m paper_agent.cli web --host "$HOST" --port "$PORT" -c "$CONFIG"
}

start_daemon() {
  echo "Starting Paper Agent daemon"
  exec "$PYTHON_BIN" -m paper_agent.cli daemon -c "$CONFIG"
}

case "$MODE" in
  web)
    start_web
    ;;
  daemon)
    start_daemon
    ;;
  all)
    echo "Starting Paper Agent web and daemon. Press Ctrl+C to stop both."
    "$PYTHON_BIN" -m paper_agent.cli web --host "$HOST" --port "$PORT" -c "$CONFIG" &
    WEB_PID=$!
    "$PYTHON_BIN" -m paper_agent.cli daemon -c "$CONFIG" &
    DAEMON_PID=$!

    trap 'kill "$WEB_PID" "$DAEMON_PID" 2>/dev/null || true; wait 2>/dev/null || true' INT TERM EXIT
    wait -n "$WEB_PID" "$DAEMON_PID"
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    echo "Unknown mode: $MODE" >&2
    usage >&2
    exit 1
    ;;
esac
