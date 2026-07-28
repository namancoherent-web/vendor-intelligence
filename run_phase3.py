#!/usr/bin/env python3
"""Phase 3 only: validation gates on Phase 2 candidates (no re-discovery)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from vendor_intel.config import Settings
from vendor_intel.live_checks import print_run_banner, validate_live_settings
from vendor_intel.phase3.runner import print_phase3_summary, run_phase3_sync


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Phase 3 — validation & enrichment (from Phase 2 discovery JSON)"
    )
    parser.add_argument(
        "query",
        nargs="?",
        default=None,
        help="Optional; query is read from Phase 2 file if --from-discovery is set",
    )
    parser.add_argument(
        "--from-discovery",
        metavar="PATH",
        required=True,
        help="Phase 2 JSON (output/phase2/phase2_discovery_*.json)",
    )
    parser.add_argument("--mock", action="store_true", help="Use mock validation (no live search)")
    parser.add_argument("--live", action="store_true", help="Force live (USE_MOCK_DATA=false)")
    parser.add_argument(
        "--skip-search",
        action="store_true",
        help="Skip live gate searches (mock validation only; for testing)",
    )
    parser.add_argument(
        "--full-validation",
        action="store_true",
        help="Slower thorough validation (disable fast path: scrape reuse, early exit, parallel)",
    )
    parser.add_argument(
        "--no-agentic",
        action="store_true",
        help="Disable LLM adjudication for borderline rule outcomes",
    )
    args = parser.parse_args()

    from vendor_intel.placeholders.load_keys import apply_env_overrides

    apply_env_overrides()
    settings = Settings.load()
    if args.live:
        settings = settings.model_copy(update={"use_mock_data": False, "mock_mode": False})
    if args.mock:
        settings = settings.model_copy(update={"mock_mode": True, "use_mock_data": True})
    if args.no_agentic:
        settings = settings.model_copy(update={"phase3_agentic_validation": False})

    warnings = validate_live_settings(settings)
    print_run_banner(settings, warnings)
    fast = not args.full_validation
    mode = "fast (reuse Phase 2 scrape, combined search, parallel)" if fast else "full"
    agentic = "hybrid (rules + scrape + LLM borderline)" if settings.phase3_agentic_validation else "rules only"
    print(f"  Phase 3: validation gates → tier A/B/C [{mode}] | {agentic}\n")

    manifest = run_phase3_sync(
        args.query,
        settings,
        phase2_discovery_path=args.from_discovery,
        skip_search_validation=args.skip_search,
        fast_validation=fast,
    )
    print_phase3_summary(manifest)


if __name__ == "__main__":
    main()
