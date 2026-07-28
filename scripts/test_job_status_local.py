#!/usr/bin/env python3
"""Local-only check for durable job status (no Cloud Run deploy).

Writes to output/demo/job_status/ and optionally GCS if GCS_BUCKET is set.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

# Load .env if present
env_path = ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

os.environ.setdefault("MARKET_QUERY_OUTPUT_DIR", str(ROOT / "output" / "demo"))

from vendor_intel.storage.gcs_export import (  # noqa: E402
    gcs_enabled,
    list_job_statuses_for_owner,
    pull_job_status,
    push_job_status,
    serialize_job_status,
    status_to_registry_job,
)


def main() -> int:
    email = "local.test@coherentmarketinsights.com"
    run_id = f"localtest{int(time.time()) % 10_000_000:07d}"
    job = {
        "run_id": run_id,
        "owner_email": email,
        "running": True,
        "job_type": "pipeline",
        "query": "Local Job Status Test Market",
        "country": "global",
        "profile": "quality",
        "cap": "broad",
        "log": "[pipeline] Phase 1 — query plan\n[pipeline] Phase 2 — discovery\n",
        "result": None,
        "error": None,
        "cancelled": False,
        "cancel_requested": False,
        "started_at": time.time(),
    }

    print(f"GCS_BUCKET enabled: {gcs_enabled()}")
    print(f"Pushing job status run_id={run_id} …")
    ok = push_job_status(job)
    assert ok, "push_job_status returned False"

    loaded = pull_job_status(run_id)
    assert loaded, "pull_job_status returned None"
    assert loaded.get("run_id") == run_id
    assert loaded.get("owner_email") == email
    assert loaded.get("running") is True
    assert int(loaded.get("phase") or 0) >= 2
    assert "Phase 2" in str(loaded.get("log_tail") or "")
    print("pull_job_status: OK", serialize_job_status(loaded).get("phase"))

    owned = list_job_statuses_for_owner(email)
    assert any(e.get("run_id") == run_id for e in owned), "list_job_statuses_for_owner missing run"
    print(f"list_job_statuses_for_owner: OK ({len(owned)} row(s) for test user)")

    # Finish the job and re-read
    job["running"] = False
    job["result"] = {"_csv_path": str(ROOT / "output" / "demo" / "local_job_status_test_global.csv")}
    job["log"] += "[pipeline] CSV saved\n[pipeline] Total time: 1.0 min\n"
    push_job_status(job)
    done = pull_job_status(run_id)
    assert done and done.get("status") == "ok"
    assert done.get("has_result") is True
    assert done.get("running") is False
    print("finished status: OK", done.get("slug") or done.get("status"))

    reg = status_to_registry_job(done)
    assert reg.get("run_id") == run_id
    assert reg.get("_from_durable_status") is True
    print("status_to_registry_job: OK")

    local_path = ROOT / "output" / "demo" / "job_status" / f"{run_id}.json"
    assert local_path.exists(), f"missing local file {local_path}"
    print(f"local file: {local_path}")
    print("ALL CHECKS PASSED (local job status working)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
