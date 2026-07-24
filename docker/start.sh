#!/usr/bin/env sh
set -eu

python -m alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-proxy-headers --no-server-header
