#!/usr/bin/env python3
"""Verify company names from Phase 2 JSON via DuckDuckGo."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vendor_intel.clients.duckduckgo import reset_network_search_state
from vendor_intel.discovery.company_verify import verify_company_name


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "json_path",
        nargs="?",
        default=str(ROOT / "output" / "phase2" / "phase2_discovery_pharmaceutical_companies_india.json"),
    )
    parser.add_argument("--geo", default="India")
    args = parser.parse_args()

    reset_network_search_state()
    data = json.loads(Path(args.json_path).read_text(encoding="utf-8"))
    scope = data.get("scope") or {}
    geo = args.geo or (scope.get("geographies") or ["global"])[0]
    market = scope.get("market", "")

    candidates = data.get("candidates") or []
    print(f"\nVerifying {len(candidates)} candidates (geo={geo})\n")
    print(f"{'Name':<50} {'Verdict':<14} {'Conf':<5} Reason")
    print("-" * 90)

    counts: dict[str, int] = {}
    for c in candidates:
        name = c.get("canonical_name", "")
        vr = await verify_company_name(name, geo=geo, market=market)
        counts[vr.verdict] = counts.get(vr.verdict, 0) + 1
        print(f"{vr.name[:48]:<50} {vr.verdict:<14} {vr.confidence:<5} {vr.reason}")

    print("\nSummary:", counts)


if __name__ == "__main__":
    asyncio.run(main())
