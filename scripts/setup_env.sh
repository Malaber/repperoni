#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-python3.14}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python 3.14 is required (set PYTHON_BIN to its executable)." >&2
  exit 1
fi

"$PYTHON_BIN" -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install invoke
.venv/bin/inv install-deps
