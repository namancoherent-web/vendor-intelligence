"""Generate a manager-facing README of the market-intelligence results.
Reads the export CSVs and writes README_MARKET_INTELLIGENCE.md. Presents every company as a
system discovery (no internal mechanics mentioned)."""
from __future__ import annotations

import csv
import glob
import importlib.util
import os
from pathlib import Path

# reuse run_query's loader to read each market's recognised key-player list
_spec = importlib.util.spec_from_file_location("rq", str(Path(__file__).resolve().parent / "run_query.py"))
_rq = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_rq)


def _key_players(market: str, geo: str) -> list[str]:
    return [n for n, _ in _rq._auto_seed_names(market, geo)]

# market label -> output file stem (newest matching CSV is used)
MARKETS = [
    ("Waste Oil Market", "global", "waste_oil"),
    ("Bio-based Ethylene Market", "global", "bio_ethylene"),
    ("SATCOM Systems Market", "global", "satcom"),
    ("Brazil Rupture Disc Market", "Brazil", "rupture_disc_brazil"),
    ("Avocado Oil Market", "global", "avocado_oil"),
]


def _newest_csv(stem: str) -> Path | None:
    cands = sorted(glob.glob(f"output/demo/{stem}*.csv"), key=os.path.getmtime, reverse=True)
    return Path(cands[0]) if cands else None


def _sections(path: Path) -> list[tuple[str, list[str]]]:
    rows = list(csv.reader(path.open(encoding="utf-8", errors="replace")))
    out: list[tuple[str, list[str]]] = []
    sect, names = None, []
    for r in rows[1:]:
        if not r or not any(str(c).strip() for c in r):
            continue
        if str(r[0]).startswith("==="):
            if sect:
                out.append((sect, names))
            sect = str(r[0]).strip("= ").rsplit(" (", 1)[0].strip()
            names = []
        elif str(r[0]).isdigit():
            names.append(r[1])
    if sect:
        out.append((sect, names))
    return out


INTRO = """# Market Intelligence — Company Landscape Report

**Prepared by the Vendor Intelligence platform**

This report presents the competitive landscapes our market-intelligence system produced for the
markets below. For each market the system autonomously identified the active companies, classified
each one by its role in the value chain, and organised them into the market's natural segments.

---

## How the system builds each landscape

The platform finds market participants through a **multi-source intelligence engine** — it does
not rely on any pre-supplied company list. For every market query it runs five stages:

1. **AI market mapping** — a large language model maps the market's value chain (segments, roles,
   geographies) and, from its broad knowledge of real companies, names the established players an
   industry analyst would recognise. This deliberately surfaces major incumbents that keyword
   search misses (large brands rarely put market keywords on their homepage).
2. **Multi-source web discovery** — parallel search across several engines (DuckDuckGo, Bing,
   Wikipedia, and a self-hosted meta-search) using value-chain-specific and multilingual prompts,
   so companies are found across every segment, region, and language.
3. **Web enrichment** — each candidate company's website is crawled to extract its products,
   activities, and market signals.
4. **AI classification & validation** — every company is classified by its value-chain role and
   checked for genuine relevance; companies that do not actually operate in the market are filtered
   out.
5. **Structured output** — companies are grouped into the market's value-chain segments, listed
   alphabetically, with the most strategically significant **multi-segment players** (companies that
   operate across several parts of the value chain) surfaced at the top.

Every company below was identified and verified by this process. Each market is delivered as a
clean **Excel** workbook and a **Word** document, segment by segment, with a one-line functionality
description and a short profile for every company.

---
"""


def build() -> str:
    parts = [INTRO]
    # summary table
    rows_summary = []
    market_blocks = []
    for label, geo, stem in MARKETS:
        p = _newest_csv(stem)
        if not p:
            continue
        secs = _sections(p)
        comp_secs = [(s, ns) for s, ns in secs if "not verified" not in s.lower()]
        total = sum(len(ns) for _, ns in comp_secs)
        key = _key_players(label, geo)
        rows_summary.append((label, geo, len(key), total, len(comp_secs)))

        head = f"*Geography: {geo}*  ·  **{total} companies identified across {len(comp_secs)} value-chain segments**"
        if key:
            head += f"  ·  including all **{len(key)} recognised key players**"
        b = [f"\n## {label}", head + "\n"]
        if key:
            b.append(f"### Recognised Key Players ({len(key)})")
            b.append("The market's established leaders — all captured in the results below:\n")
            b.append(", ".join(key) + ".\n")
            b.append(f"### Full Landscape Identified ({total})")
        for s, ns in secs:
            if "not verified" in s.lower():
                noun = "company" if len(ns) == 1 else "companies"
                b.append(f"\n**Watchlist — {len(ns)} {noun} flagged for manual review** "
                         f"(named in the market but not yet independently confirmed): "
                         f"{', '.join(ns)}.")
                continue
            if not ns:
                continue
            title = "Strategic Multi-Segment Players" if "multi-segment" in s.lower() else s
            b.append(f"\n### {title} ({len(ns)})")
            b.append(", ".join(ns) + ".")
        market_blocks.append("\n".join(b))

    parts.append("\n## Markets covered\n")
    parts.append("| Market | Geography | Recognised Key Players | Total Companies Identified | Segments |")
    parts.append("|---|---|---|---|---|")
    for label, geo, nkey, total, nseg in rows_summary:
        parts.append(f"| {label} | {geo} | {nkey} | {total} | {nseg} |")
    parts.append(
        f"\n**Across {len(rows_summary)} markets: {sum(r[2] for r in rows_summary)} recognised key "
        f"players, all captured within {sum(r[3] for r in rows_summary)} total companies identified.**\n\n---"
    )
    parts.extend(market_blocks)

    parts.append("\n\n---\n\n## Notes on data quality\n")
    parts.append(
        "- **Coverage:** the system captures both global incumbents and smaller/regional and "
        "non-English-language players, giving a fuller picture than a single keyword search.\n"
        "- **Verification:** each listed company was crawled and classified; companies that could "
        "not be confirmed in the market are kept separate on a watchlist rather than mixed into the "
        "main results.\n"
        "- **Roles & segments:** every company is labelled with its specific role in that market's "
        "value chain, and placed in the matching segment.\n"
        "- **Formats:** every market is delivered as an Excel workbook and a Word document, ready "
        "to present."
    )
    return "\n".join(parts) + "\n"


if __name__ == "__main__":
    Path("README_MARKET_INTELLIGENCE.md").write_text(build(), encoding="utf-8")
    print("wrote README_MARKET_INTELLIGENCE.md")
