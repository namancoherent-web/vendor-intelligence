#!/usr/bin/env bash
# Cloud Run entry for Next.js + FastAPI BFF (test service).
set -euo pipefail

PORT="${PORT:-8080}"
export PYTHONPATH="/app/src:/app${PYTHONPATH:+:$PYTHONPATH}"
export FRONTEND_DIST="${FRONTEND_DIST:-/app/frontend/out}"

echo "[entrypoint-api] Vendor Intelligence API starting (PORT=${PORT})"

if [[ -n "${DATABASE_URL:-}" ]]; then
  echo "[entrypoint-api] Waiting for Postgres / init auth tables..."
  for i in $(seq 1 30); do
    if python /app/scripts/init_auth_db.py; then
      echo "[entrypoint-api] Auth DB ready."
      break
    fi
    if [[ "$i" -eq 30 ]]; then
      echo "[entrypoint-api] WARNING: auth DB init failed after retries — login may fail."
      break
    fi
    echo "[entrypoint-api] DB not ready (attempt $i/30), sleep 2s..."
    sleep 2
  done
else
  echo "[entrypoint-api] DATABASE_URL not set — skipping auth DB init."
fi

mkdir -p /app/output/demo

exec python -m uvicorn api.main:app --host 0.0.0.0 --port "${PORT}"
