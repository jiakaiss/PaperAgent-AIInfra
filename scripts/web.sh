#!/usr/bin/env bash
# Daemonized launcher for the paper-agent web UI.
# Subcommands: start | stop | restart | status
#
# Mirrors scripts/daemon.sh. The web server's main log is written by
# Python's FileHandler (--log-file logs/web.log), independent of the
# launching shell's stderr handle. The stdout fallback (logs/web.stdout.log)
# captures crash tracebacks and uvicorn's pre-logging output.
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON_BIN="${PYTHON_BIN:-python}"
CONFIG="${CONFIG:-config.yaml}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
LOG_DIR="${LOG_DIR:-logs}"
PID_FILE="$LOG_DIR/web.pid"
STDOUT_LOG="$LOG_DIR/web.stdout.log"
MAIN_LOG="$LOG_DIR/web.log"

cmd="${1:-status}"

alive() { [ -n "${1:-}" ] && kill -0 "$1" 2>/dev/null; }

read_pid() { [ -f "$PID_FILE" ] && cat "$PID_FILE" || echo ""; }

kill_pid() {
  local pid="$1"
  # See scripts/daemon.sh for the git-bash PID vs taskkill rationale.
  if kill "$pid" 2>/dev/null; then
    sleep 2
    alive "$pid" && kill -9 "$pid" 2>/dev/null || true
  elif command -v taskkill >/dev/null 2>&1; then
    taskkill //PID "$pid" //F >/dev/null || true
  else
    kill -9 "$pid" 2>/dev/null || true
  fi
}

start() {
  mkdir -p "$LOG_DIR"
  local old
  old="$(read_pid)"
  if alive "$old"; then
    echo "Web already running (PID $old). Use '$0 stop' first." >&2
    exit 1
  fi
  rm -f "$PID_FILE"

  export PYTHONIOENCODING="${PYTHONIOENCODING:-utf-8}"
  export PYTHONUNBUFFERED=1

  nohup "$PYTHON_BIN" -m paper_agent.cli web \
    -c "$CONFIG" --host "$HOST" --port "$PORT" --log-file "$MAIN_LOG" \
    >> "$STDOUT_LOG" 2>&1 &
  local pid=$!
  echo "$pid" > "$PID_FILE"
  disown "$pid" 2>/dev/null || true
  sleep 2

  if ! alive "$pid"; then
    echo "Web failed to stay alive. Tail of $STDOUT_LOG:" >&2
    tail -n 30 "$STDOUT_LOG" >&2
    rm -f "$PID_FILE"
    exit 1
  fi
  echo "Web started: PID $pid (http://${HOST}:${PORT})"
  echo "  Main log:   $MAIN_LOG"
  echo "  Stdout log: $STDOUT_LOG"
  echo "  PID file:   $PID_FILE"
}

stop() {
  local pid
  pid="$(read_pid)"
  if [ -z "$pid" ]; then
    echo "No PID file at $PID_FILE — web not running (via this script)."
    echo "If a web is running outside script control, find it with:"
    echo "  ps -ef | grep 'paper_agent.cli web'"
    return 0
  fi
  if ! alive "$pid"; then
    echo "PID $pid not alive. Removing stale PID file."
    rm -f "$PID_FILE"
    return 0
  fi
  echo "Stopping web PID $pid..."
  kill_pid "$pid"
  rm -f "$PID_FILE"
  echo "Stopped."
}

status() {
  local pid
  pid="$(read_pid)"
  if [ -n "$pid" ] && alive "$pid"; then
    echo "Web: RUNNING (PID $pid, http://${HOST}:${PORT})"
  elif [ -n "$pid" ]; then
    echo "Web: DEAD (stale PID file points to $pid)"
  else
    echo "Web: NOT MANAGED (no PID file at $PID_FILE)"
  fi
  if [ -f "$MAIN_LOG" ]; then
    echo "Last 5 log lines:"
    tail -n 5 "$MAIN_LOG"
  fi
}

case "$cmd" in
  start)   start ;;
  stop)    stop ;;
  restart) stop; sleep 1; start ;;
  status)  status ;;
  *) echo "Usage: $0 {start|stop|restart|status}" >&2; exit 1 ;;
esac
