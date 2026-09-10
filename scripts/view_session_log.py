"""Print a teammate's session_log.json in a readable form for auditing prompts.

Usage:
    python scripts/view_session_log.py path/to/their/session_log.json

Each teammate's tool runs locally with no shared server, so this reads whatever
session_log.json file they send you directly - no live server or admin login needed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/view_session_log.py path/to/session_log.json")
        raise SystemExit(1)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"File not found: {path}")
        raise SystemExit(1)

    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Could not parse {path}: {exc}")
        raise SystemExit(1)

    if not isinstance(entries, list):
        print("Unexpected file shape (expected a list of run entries).")
        raise SystemExit(1)

    entries = sorted(entries, key=lambda e: str(e.get("ran_at") or ""), reverse=True)

    for e in entries:
        status = str(e.get("status") or "")
        print("-" * 70)
        print(f"When:        {e.get('ran_at', '')}")
        print(f"User:        {e.get('owner_email', '(unknown)')}")
        print(f"Status:      {status}")
        print(f"Market name: {e.get('query', '')}")
        # raw_query/brief_text only exist on runs made after this feature shipped -
        # older entries won't have them, shown as (not recorded) rather than blank.
        raw_query = e.get("raw_query")
        brief = e.get("brief_text")
        print(f"What they typed:  {raw_query if raw_query else '(not recorded - older run)'}")
        if brief:
            print(f"Brief text:       {brief}")
        print(f"Country:     {e.get('country', '')}")
        if status == "ok":
            print(f"Companies:   {e.get('companies_exported', '')}")
            print(f"Time taken:  {e.get('elapsed_minutes', '')} min")
            cost = e.get("estimated_cost_usd")
            if cost is not None:
                print(f"Est. cost:   ${cost}")
        elif e.get("error"):
            print(f"Error:       {e.get('error')}")
    print("-" * 70)
    print(f"Total runs: {len(entries)}")


if __name__ == "__main__":
    main()
