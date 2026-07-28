#!/usr/bin/env python3
"""Phase 2 only: discovery search + candidate aggregation + optional website scrape."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from vendor_intel.config import Settings
from vendor_intel.live_checks import print_run_banner, validate_live_settings
from vendor_intel.phase2.runner import print_phase2_summary, run_phase2_sync


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Phase 2 — fast discovery (name+domain) or legacy discovery+scrape"
    )
    parser.add_argument(
        "query",
        nargs="?",
        default=None,
        help="Natural-language query (optional if --from-plan is set)",
    )
    parser.add_argument(
        "--from-plan",
        metavar="PATH",
        help="Reuse Phase 1 JSON (output/phase1/phase1_plan_*.json) — skips LLM re-compile",
    )
    parser.add_argument("--mock", action="store_true", help="Use mock discovery (no search)")
    parser.add_argument("--live", action="store_true", help="Force live (USE_MOCK_DATA=false)")
    parser.add_argument(
        "--legacy",
        action="store_true",
        help="Legacy Phase 2: full discovery JSON + optional website scrape",
    )
    parser.add_argument(
        "--no-scrape",
        action="store_true",
        help="Skip backend website fetch for top candidates",
    )
    parser.add_argument(
        "--max-scrape",
        type=int,
        default=80,
        metavar="N",
        help="Max candidate sites to scrape (default 80; tiered depth by confidence)",
    )
    args = parser.parse_args()

    if not args.query and not args.from_plan:
        parser.error("Provide a query or --from-plan PATH")

    from vendor_intel.placeholders.load_keys import apply_env_overrides

    apply_env_overrides()
    settings = Settings.load()
    if args.live:
        settings = settings.model_copy(update={"use_mock_data": False, "mock_mode": False})
    if args.mock:
        settings = settings.model_copy(update={"mock_mode": True, "use_mock_data": True})

    warnings = validate_live_settings(settings)
    print_run_banner(settings, warnings)

    use_fast = not args.legacy
    manifest = run_phase2_sync(
        args.query,
        settings,
        phase1_plan_path=args.from_plan,
        scrape_websites=not args.no_scrape,
        max_scrape=max(1, args.max_scrape),
        fast_discovery=use_fast,
    )
    if use_fast:
        print(f"\n=== Phase 2 fast complete ===")
        print(f"  Companies: {manifest.get('company_count', 0)}")
        print(f"  Output: {manifest.get('output_path')}")
        return
    print_phase2_summary(manifest)


if __name__ == "__main__":
    main()
