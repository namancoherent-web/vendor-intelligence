"""Dedicated auth API server (OTP + sessions).

  .venv\\Scripts\\python.exe run_auth_api.py
  → http://127.0.0.1:8001/docs
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from vendor_intel.placeholders.load_keys import apply_env_overrides

apply_env_overrides()

from fastapi import FastAPI
from vendor_intel.auth.db import init_db
from vendor_intel.auth.routes import router as auth_router

app = FastAPI(title="Vendor Intelligence Auth", version="0.1.0")
app.include_router(auth_router)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/health")
def health():
    return {"status": "ok", "service": "auth"}


def main() -> None:
    import uvicorn

    uvicorn.run(
        "run_auth_api:app",
        host="0.0.0.0",
        port=int(__import__("os").getenv("AUTH_API_PORT", "8001")),
        reload=False,
    )


if __name__ == "__main__":
    main()
