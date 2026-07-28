#!/usr/bin/env python3
"""
Suggest Google Alert queries from Phase 1 output — copy-paste into google.com/alerts.

Usage:
  .venv\\Scripts\\python.exe suggest_google_alerts.py --latest
  .venv\\Scripts\\python.exe suggest_google_alerts.py --from output/phase1_debug/digital_signage_system_market_global.json
  .venv\\Scripts\\python.exe suggest_google_alerts.py -q "Digital Signage System Market"
  .venv\\Scripts\\python.exe suggest_google_alerts.py -q "Aluminium Cladding" --country Europe

Writes: output/phase1_debug/<slug>_google_alerts.md
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

DEBUG_DIR = ROOT / "output" / "phase1_debug"
PHASE1_DIR = ROOT / "output" / "phase1"


def _slug(query: str, country: str) -> str:
    text = f"{query}_{country}".lower()
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")[:72] or "market"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _find_manifest(*, query: str, country: str, from_path: str | None, latest: bool) -> tuple[dict, Path]:
    if from_path:
        p = Path(from_path)
        if not p.is_absolute():
            p = ROOT / p
        if not p.exists():
            raise FileNotFoundError(f"Phase 1 JSON not found: {p}")
        return _load_json(p), p

    if latest:
        candidates = sorted(
            list(DEBUG_DIR.glob("*.json")) + list(PHASE1_DIR.glob("phase1_plan_*.json")),
            key=lambda x: x.stat().st_mtime,
            reverse=True,
        )
        for p in candidates:
            if p.name.endswith("_google_alerts.md"):
                continue
            if "_google_alerts" in p.stem:
                continue
            return _load_json(p), p
        raise FileNotFoundError(
            f"No Phase 1 JSON in {DEBUG_DIR} or {PHASE1_DIR}. Run test_phase1.py first."
        )

    slug = _slug(query, country)
    for p in (
        DEBUG_DIR / f"{slug}.json",
        PHASE1_DIR / f"phase1_plan_{slug}.json",
    ):
        if p.exists():
            return _load_json(p), p

    # Fuzzy: any debug json containing market slug fragment
    frag = slug[:24]
    for p in sorted(DEBUG_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        if frag in p.stem:
            return _load_json(p), p

    raise FileNotFoundError(
        f"No Phase 1 JSON for '{query}' ({country}).\n"
        f"  Run: .venv\\Scripts\\python.exe test_phase1.py -q \"{query}\" --country {country}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Suggest Google Alert queries from Phase 1 JSON")
    parser.add_argument("--from", dest="from_path", help="Path to phase1_debug or phase1_plan JSON")
    parser.add_argument("--latest", action="store_true", help="Use newest Phase 1 JSON on disk")
    parser.add_argument("--query", "-q", default="", help="Market query (finds matching JSON)")
    parser.add_argument("--country", "-c", default="global")
    parser.add_argument("--max", type=int, default=6, help="Max alert suggestions (default 6)")
    args = parser.parse_args()

    if not args.from_path and not args.latest and not args.query.strip():
        parser.error("Provide --from PATH, --latest, or --query")

    manifest, src = _find_manifest(
        query=args.query.strip(),
        country=(args.country or "global").strip(),
        from_path=args.from_path,
        latest=args.latest,
    )

    from vendor_intel.alerts.suggest_queries import (
        format_alerts_report,
        suggest_google_alert_queries,
    )

    suggestions = suggest_google_alert_queries(manifest, max_alerts=max(3, min(args.max, 10)))
    report = format_alerts_report(manifest, suggestions)

    out_name = src.stem + "_google_alerts.md"
    out_path = DEBUG_DIR / out_name
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")

    print("=" * 60)
    print("  GOOGLE ALERTS — suggested queries")
    print(f"  From: {src}")
    print("=" * 60)
    print()
    for i, row in enumerate(suggestions, 1):
        print(f"  {i}. {row['query']}")
        print(f"     ({row['reason']})")
        print()
    print("-" * 60)
    print("  Next steps:")
    print("  1. Open https://www.google.com/alerts")
    print("  2. Paste each query above -> Create alert -> RSS icon -> copy feed URL")
    print("  3. Add URLs to .env as GOOGLE_ALERTS_RSS_URLS=url1,url2,...")
    print("  4. .venv\\Scripts\\python.exe scripts\\run_alerts_worker.py --no-browser")
    print()
    print(f"  Full guide saved: {out_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
