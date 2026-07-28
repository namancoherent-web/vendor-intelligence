#!/usr/bin/env python3
"""Phase 4 — export CSV from Phase 3 validation JSON."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from vendor_intel.config import Settings
from vendor_intel.phase4.runner import print_phase4_summary, run_phase4_export


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Phase 4 — CSV export from Phase 3 validation JSON"
    )
    parser.add_argument(
        "--from-validation",
        metavar="PATH",
        required=True,
        help="Phase 3 JSON (output/phase3/phase3_validation_*.json)",
    )
    parser.add_argument(
        "--csv-dir",
        metavar="DIR",
        default=None,
        help="Output base directory (default: CSV_OUTPUT_DIR from .env → output/)",
    )
    parser.add_argument(
        "--include-all-tiers",
        action="store_true",
        help="Include tier C in company_list.csv (default: only A and B)",
    )
    args = parser.parse_args()

    settings = Settings.load()
    import json
    from pathlib import Path

    p3 = Path(args.from_validation)
    if p3.is_file():
        plan = json.loads(p3.read_text(encoding="utf-8"))
        print(f"  Phase 4 input query: {plan.get('query', '?')}", flush=True)
        scope = plan.get("scope") or {}
        print(
            f"  Phase 4 market: {scope.get('market', '?')} | "
            f"geo: {(scope.get('geographies') or ['?'])[0]}",
            flush=True,
        )

    manifest = run_phase4_export(
        args.from_validation,
        settings,
        csv_dir=args.csv_dir,
        quality_filter=not args.include_all_tiers,
    )
    print_phase4_summary(manifest)


if __name__ == "__main__":
    main()
