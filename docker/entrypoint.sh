#!/usr/bin/env bash
set -euo pipefail

PORT="${PORT:-8080}"
export PYTHONPATH="/app/src:/app${PYTHONPATH:+:$PYTHONPATH}"

echo "[entrypoint] Vendor Intelligence starting (PORT=${PORT})"

if [[ -n "${DATABASE_URL:-}" ]]; then
  echo "[entrypoint] Waiting for Postgres / init auth tables..."
  for i in $(seq 1 30); do
    if python /app/scripts/init_auth_db.py; then
      echo "[entrypoint] Auth DB ready."
      break
    fi
    if [[ "$i" -eq 30 ]]; then
      echo "[entrypoint] WARNING: auth DB init failed after retries — login may fail."
      break
    fi
    echo "[entrypoint] DB not ready (attempt $i/30), sleep 2s..."
    sleep 2
  done
else
  echo "[entrypoint] DATABASE_URL not set — skipping auth DB init."
fi

mkdir -p /app/output/demo

exec streamlit run /app/app.py \
  --server.port="${PORT}" \
  --server.address=0.0.0.0 \
  --server.headless=true \
  --browser.gatherUsageStats=false \
  --server.enableCORS=false \
  --server.enableXsrfProtection=false
