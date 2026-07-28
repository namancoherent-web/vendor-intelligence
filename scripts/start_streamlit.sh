#!/usr/bin/env bash
# Vendor Intelligence — local Streamlit (no Node, no GCP)
set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v python3 >/dev/null 2>&1; then
  echo "Install Python 3.11+ first."
  exit 1
fi

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi

.venv/bin/python -m pip install --upgrade pip -q
.venv/bin/python -m pip install -r requirements.txt

if [[ ! -f .env ]]; then
  if [[ -f .env.local.example ]]; then
    cp .env.local.example .env
    echo "Created .env from .env.local.example — paste your LLM API key."
  else
    cp .env.example .env
  fi
fi

mkdir -p data output/demo
.venv/bin/python scripts/init_auth_db.py || true

if grep -q 'PASTE_YOUR_KEY_HERE' .env 2>/dev/null; then
  echo "Edit .env and replace PASTE_YOUR_KEY_HERE, then re-run."
  exit 1
fi

echo "Open http://127.0.0.1:8501"
exec .venv/bin/python -m streamlit run app.py --server.headless true --browser.gatherUsageStats false
