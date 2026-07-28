#!/usr/bin/env python3
"""Create auth tables (Postgres or local SQLite).

  .venv\\Scripts\\python.exe scripts/init_auth_db.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vendor_intel.placeholders.load_keys import apply_env_overrides

apply_env_overrides()


def _add_password_columns() -> None:
    """Base.metadata.create_all() only creates missing tables, not new columns
    on an existing one — this adds password_hash/email_verified to `users`
    for databases that had auth tables from before those columns existed.
    """
    from sqlalchemy import inspect, text

    from vendor_intel.auth.db import get_engine

    engine = get_engine()
    insp = inspect(engine)
    if "users" not in insp.get_table_names():
        return  # create_all() will make it fresh with the columns already
    existing = {c["name"] for c in insp.get_columns("users")}
    with engine.begin() as conn:
        if "password_hash" not in existing:
            conn.execute(text("ALTER TABLE users ADD COLUMN password_hash VARCHAR(200)"))
            print("  Added column: users.password_hash")
        if "email_verified" not in existing:
            conn.execute(
                text("ALTER TABLE users ADD COLUMN email_verified BOOLEAN NOT NULL DEFAULT false")
            )
            print("  Added column: users.email_verified")


def main() -> None:
    from vendor_intel.auth.config import get_auth_settings
    from vendor_intel.auth.db import init_db

    settings = get_auth_settings()
    print(f"Connecting to: {settings.database_url.split('@')[-1]}")
    init_db()
    _add_password_columns()
    print("Auth tables ready: users, otp_challenges, sessions, auth_events")


if __name__ == "__main__":
    main()
