#!/usr/bin/env python3
"""Phase 1 only: query plan + funnel L0–L2 + free search smoke test."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from vendor_intel.config import Settings
from vendor_intel.live_checks import print_run_banner, validate_live_settings
from vendor_intel.phase1.runner import print_phase1_summary, run_phase1_sync


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Phase 1 — foundation & free search")
    parser.add_argument("query", nargs="?", default="Give me the best laptop companies in India")
    parser.add_argument("--mock", action="store_true", help="Use mock query plan (no LLM)")
    parser.add_argument("--live", action="store_true", help="Force live (USE_MOCK_DATA=false)")
    args = parser.parse_args()

    from vendor_intel.placeholders.load_keys import apply_env_overrides

    apply_env_overrides()
    settings = Settings.load()
    if args.live:
        settings = settings.model_copy(update={"use_mock_data": False, "mock_mode": False})
    if args.mock:
        settings = settings.model_copy(update={"mock_mode": True, "use_mock_data": True})

    warnings = validate_live_settings(settings)
    print_run_banner(settings, warnings)

    manifest = run_phase1_sync(args.query, settings)
    print_phase1_summary(manifest)


if __name__ == "__main__":
    main()
