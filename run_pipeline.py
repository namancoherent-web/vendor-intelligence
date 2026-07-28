#!/usr/bin/env python3
"""5-phase pipeline: Plan → Discovery → SSC → Quality classify → CSV (~20 min)."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from vendor_intel.config import Settings, _project_root
from vendor_intel.live_checks import print_run_banner, validate_live_settings
from vendor_intel.pipeline.orchestrator import run_pipeline_sync, save_pipeline_csv


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Vendor Intelligence — quality market landscape pipeline (default)"
    )
    parser.add_argument("--industry", required=True, help="Market / industry name")
    parser.add_argument(
        "--country",
        default="global",
        help="Geography (default: global). Use Brazil, India, etc. when scoped.",
    )
    parser.add_argument(
        "--global",
        dest="force_global",
        action="store_true",
        help="Force worldwide scope (same as --country global, higher volume caps)",
    )
    parser.add_argument("--functions", nargs="*", default=[], help="Optional role hints")
    parser.add_argument("--input-json", metavar="PATH", help='{"industry","country","functions":[]}')
    parser.add_argument("--live", action="store_true", help="Force live mode")
    parser.add_argument("--mock", action="store_true", help="Mock mode")
    parser.add_argument(
        "--profile",
        choices=("quality", "balanced", "recall", "deep"),
        default=None,
        help="quality=~20min, 25-65 vetted rows (default). recall=noisy bulk.",
    )
    parser.add_argument(
        "--recall",
        action="store_true",
        help="Same as --profile recall (more rows, more noise)",
    )
    parser.add_argument(
        "--full-crawl",
        action="store_true",
        help="Use smart_crawl instead of fast SSC (slower, richer pages)",
    )
    parser.add_argument("--enrich-limit", type=int, default=None)
    parser.add_argument("--classify-limit", type=int, default=None)
    parser.add_argument("--csv-out", metavar="PATH", default=None)
    args = parser.parse_args()

    if args.input_json:
        data = json.loads(Path(args.input_json).read_text(encoding="utf-8"))
        query_context = {
            "industry": data.get("industry", ""),
            "country": data.get("country", "global"),
            "functions": list(data.get("functions") or []),
        }
    else:
        query_context = {
            "industry": args.industry,
            "country": args.country,
            "functions": list(args.functions or []),
        }

    from vendor_intel.placeholders.load_keys import apply_env_overrides

    apply_env_overrides()
    settings = Settings.load()
    if args.live:
        settings = settings.model_copy(update={"use_mock_data": False, "mock_mode": False})
    if args.mock:
        settings = settings.model_copy(update={"mock_mode": True, "use_mock_data": True})

    profile = "recall" if args.recall else (args.profile or settings.pipeline_profile or "quality")
    updates: dict = {"pipeline_profile": profile, "pipeline_recall_mode": profile == "recall"}
    if args.full_crawl:
        updates["pipeline_use_ssc"] = False
    if profile in ("quality", "balanced"):
        updates.setdefault("pipeline_use_ssc", True)
        updates.setdefault("pipeline_recall_mode", False)
        updates.setdefault("pipeline_min_export_confidence", 0.55)
    settings = settings.model_copy(update=updates)

    warnings = validate_live_settings(settings)
    print_run_banner(settings, warnings)

    from vendor_intel.pipeline.geo_limits import is_global_geography, pipeline_limits

    lim = pipeline_limits(
        settings, recall=(profile == "recall"), country=query_context.get("country")
    )
    enrich_lim = args.enrich_limit
    classify_lim = args.classify_limit
    if enrich_lim is None and profile in ("quality", "balanced"):
        enrich_lim = int(lim["enrich"])
    if classify_lim is None and profile in ("quality", "balanced"):
        classify_lim = int(lim["discover"])
    if is_global_geography(query_context.get("country")):
        print(
            f"\n  [run] GLOBAL mode - discover<={lim['discover']}, enrich<={lim['enrich']}, "
            f"export {lim['export_min']}–{lim['export_max']} rows (no --recall)\n",
            flush=True,
        )

    try:
        result = run_pipeline_sync(
            query_context,
            settings,
            enrich_limit=enrich_lim,
            classify_limit=classify_lim,
        )
    finally:
        try:
            from vendor_intel.clients.ddg_worker_pool import shutdown_ddg_pool

            shutdown_ddg_pool(wait=True)
        except Exception:
            pass

    slug = (
        query_context["industry"][:30] + "_" + query_context["country"][:20]
    ).lower().replace(" ", "_")
    slug = "".join(c if c.isalnum() or c == "_" else "_" for c in slug)[:50]
    csv_path = args.csv_out or str(_project_root() / "output" / "pipeline" / f"pipeline_{slug}.csv")
    csv_saved = save_pipeline_csv(result, csv_path)

    summary_path = Path(csv_saved).with_suffix(".json")
    try:
        summary_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    except PermissionError:
        from datetime import datetime, timezone

        alt_json = summary_path.with_name(
            f"{summary_path.stem}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
        )
        alt_json.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        summary_path = alt_json
        print(f"  [pipeline] JSON locked — saved: {summary_path.resolve()}", flush=True)

    usage = result.get("llm_usage") or {}
    print("\n=== Pipeline complete ===")
    print(f"  Exported companies: {len(result.get('relevant_companies') or [])}")
    print(f"  Total time: {result.get('elapsed_minutes')} min")
    print(f"  LLM calls: {usage.get('llm_calls_total')} (classify: {usage.get('classify_calls')})")
    print(f"  Est. LLM cost: ${usage.get('estimated_cost_usd', 0)} ({usage.get('note', '')})")
    print(f"  CSV: {csv_saved}")
    print(f"  Summary JSON: {summary_path.resolve()}")


if __name__ == "__main__":
    main()
