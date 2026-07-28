#!/usr/bin/env python3
"""
run_market_queries.py — Run four benchmark market queries in sequence.

Usage:
  python run_market_queries.py

Prefer one-at-a-time runs: python run_query.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

QUERIES: list[tuple[str, str, str]] = [
    ("Bio Based Ethylene Market", "Bio Based Ethylene Market", "global"),
    ("Atomic Clock Market", "Atomic Clock Market", "global"),
    ("NC G-code Simulation Market", "NC G-code Simulation Market", "global"),
    ("Smart Distributed Wind Infrastructure Market", "Smart Distributed Wind Infrastructure Market", "global"),
]



def _csv_slug(name: str, country: str) -> str:
    text = f"{name}_{country}".lower()
    return "".join(c if c.isalnum() else "_" for c in text).strip("_")


def main() -> None:
    from run_query import OUTPUT_DIR, _load_settings, _refresh_output_dir, _validate_env, run_one_query

    from vendor_intel.placeholders.load_keys import apply_env_overrides

    apply_env_overrides()
    _refresh_output_dir()

    for w in _validate_env():
        print(f"  WARNING: {w}")

    profile = os.getenv("PIPELINE_PROFILE", "quality").strip()
    settings = _load_settings(profile)
    from vendor_intel.pipeline.geo_limits import pipeline_limits

    lim = pipeline_limits(settings, recall=(profile == "recall"), country="global")
    enrich_cap = int(lim["enrich"])
    discover_cap = int(lim["discover"])

    print(f"\n  Batch: {len(QUERIES)} queries | profile={profile} | output={OUTPUT_DIR}")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    summary: list[dict] = []
    t_all = time.perf_counter()

    for idx, (display, industry, country) in enumerate(QUERIES, 1):
        print(f"\n{'=' * 70}\n  Query {idx}/{len(QUERIES)}: {display}\n{'=' * 70}")
        t0 = time.perf_counter()
        try:
            result = run_one_query(
                industry, country, settings,
                enrich_limit=enrich_cap,
                classify_limit=discover_cap,
            )
            n = len(result.get("relevant_companies") or [])
            elapsed = round(time.perf_counter() - t0, 1)
            csv_file = result.get("_csv_path", "")
            print(f"  OK: {n} companies in {elapsed / 60:.1f} min -> {csv_file}")
            summary.append({
                "query": display,
                "status": "ok",
                "companies_exported": n,
                "elapsed_minutes": round(elapsed / 60, 2),
                "csv_file": csv_file,
            })
        except Exception as exc:
            elapsed = round(time.perf_counter() - t0, 1)
            print(f"  FAILED: {exc}")
            summary.append({
                "query": display,
                "status": "error",
                "error": str(exc),
                "elapsed_seconds": elapsed,
            })

    run_summary = {
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "total_elapsed_minutes": round((time.perf_counter() - t_all) / 60, 2),
        "profile": profile,
        "queries": summary,
    }
    path = OUTPUT_DIR / "run_summary.json"
    path.write_text(json.dumps(run_summary, indent=2, default=str), encoding="utf-8")
    print(f"\n  Summary: {path}")

    try:
        from vendor_intel.clients.ddg_worker_pool import shutdown_ddg_pool
        shutdown_ddg_pool(wait=True)
    except Exception:
        pass


if __name__ == "__main__":
    main()
