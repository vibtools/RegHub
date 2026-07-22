#!/bin/sh
set -eu

python -m scripts.startup
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --no-proxy-headers
