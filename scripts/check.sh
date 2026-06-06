#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python}"
RUN_JS_TESTS="${RUN_JS_TESTS:-auto}"

cd "$(dirname "$0")/.."
export PYTHONIOENCODING="${PYTHONIOENCODING:-utf-8}"

echo "Running ruff..."
"$PYTHON_BIN" -m ruff check src/ tests/

echo "Running pytest..."
"$PYTHON_BIN" -m pytest tests/ -q

if [ -f tests/js/preferences.test.mjs ]; then
  if [ "$RUN_JS_TESTS" = "1" ] || { [ "$RUN_JS_TESTS" = "auto" ] && command -v node >/dev/null 2>&1; }; then
    echo "Running JS tests..."
    node --test tests/js/preferences.test.mjs
  elif [ "$RUN_JS_TESTS" = "auto" ]; then
    echo "Skipping JS tests: node not found. Set RUN_JS_TESTS=1 to require them."
  fi
fi

echo "All checks passed."
