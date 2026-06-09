#!/usr/bin/env bash
# Daemonized launcher for the paper-agent scheduler.
# Subcommands: start | stop | restart | status
#
# The main app log is written by Python's FileHandler (config.yaml → logging.file),
# so it does NOT depend on this script's stderr redirection staying open.
# This script's stdout/stderr redirect (logs/daemon.stdout.log) only captures
# crash tracebacks and any output before logging is initialized.
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON_BIN="${PYTHON_BIN:-python}"
CONFIG="${CONFIG:-config.yaml}"
LOG_DIR="${LOG_DIR:-logs}"
PID_FILE="$LOG_DIR/daemon.pid"
STDOUT_LOG="$LOG_DIR/daemon.stdout.log"
MAIN_LOG="$LOG_DIR/daemon.log"
STATE_FILE="${STATE_FILE:-paper_agent.db.daemon.json}"

cmd="${1:-status}"

alive() { [ -n "${1:-}" ] && kill -0 "$1" 2>/dev/null; }

read_pid() { [ -f "$PID_FILE" ] && cat "$PID_FILE" || echo ""; }

kill_pid() {
  local pid="$1"
  # On Windows git bash, `taskkill //PID <bash_pid>` fails because bash sees a
  # Cygwin-virtual PID, not the Windows PID. Bash's own `kill` proxies to the
  # real process via the Cygwin layer. Try `kill` first; only fall back to
  # taskkill on platforms where the bash PID IS the OS PID (Linux/macOS).
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
    echo "Daemon already running (PID $old). Use '$0 stop' first." >&2
    exit 1
  fi
  rm -f "$PID_FILE"

  export PYTHONIOENCODING="${PYTHONIOENCODING:-utf-8}"
  export PYTHONUNBUFFERED=1   # avoid buffered stderr fallback log

  nohup "$PYTHON_BIN" -m paper_agent.cli daemon -c "$CONFIG" \
    >> "$STDOUT_LOG" 2>&1 &
  local pid=$!
  echo "$pid" > "$PID_FILE"
  disown "$pid" 2>/dev/null || true
  sleep 2

  if ! alive "$pid"; then
    echo "Daemon failed to stay alive. Tail of $STDOUT_LOG:" >&2
    tail -n 30 "$STDOUT_LOG" >&2
    rm -f "$PID_FILE"
    exit 1
  fi
  echo "Daemon started: PID $pid"
  echo "  Main log:   $MAIN_LOG"
  echo "  Stdout log: $STDOUT_LOG"
  echo "  PID file:   $PID_FILE"
}

stop() {
  local pid
  pid="$(read_pid)"
  if [ -z "$pid" ]; then
    echo "No PID file at $PID_FILE — daemon not running (via this script)."
    echo "If a daemon is running outside script control, find it with:"
    echo "  ps -ef | grep paper_agent.cli"
    return 0
  fi
  if ! alive "$pid"; then
    echo "PID $pid not alive. Removing stale PID file."
    rm -f "$PID_FILE"
    return 0
  fi
  echo "Stopping daemon PID $pid..."
  kill_pid "$pid"
  rm -f "$PID_FILE"
  echo "Stopped."
}

status() {
  local pid
  pid="$(read_pid)"
  if [ -n "$pid" ] && alive "$pid"; then
    echo "Daemon: RUNNING (PID $pid)"
  elif [ -n "$pid" ]; then
    echo "Daemon: DEAD (stale PID file points to $pid)"
  else
    echo "Daemon: NOT MANAGED (no PID file at $PID_FILE)"
  fi
  if [ -f "$STATE_FILE" ]; then
    echo "Heartbeat:"
    cat "$STATE_FILE"
    echo
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
