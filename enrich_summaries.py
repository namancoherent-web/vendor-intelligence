"""Rewrite company summaries as 3-4 sentence market/section-aware artifacts, and give
Not-Verified companies a real crawled description. Regenerate CSV + DOCX (alphabetical).
No pipeline re-run.

    python enrich_summaries.py "waste_oil_market_global_v2.json" ...
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from vendor_intel.placeholders.load_keys import apply_env_overrides  # noqa: E402

apply_env_overrides()
from vendor_intel.clients.claude import ClaudeClient  # noqa: E402
from vendor_intel.config import Settings  # noqa: E402
from vendor_intel.enrichment.smart_enrichment import supplement_crawl  # noqa: E402
from vendor_intel.pipeline.orchestrator import save_pipeline_csv, save_pipeline_docx  # noqa: E402
from vendor_intel.pipeline.quality_export import dedupe_export_rows  # noqa: E402
from vendor_intel.pipeline.sections import (  # noqa: E402
    build_section_taxonomy,
    group_into_sections,
    main_product_label,
)

HAIKU = "claude-haiku-4-5-20251001"
UNV_ONLY = "--unv-only" in sys.argv  # only (re)describe Not-Verified companies; keep summaries

SUM_SYS = (
    "You write factual company descriptions for a B2B market-intelligence deliverable. "
    "For EACH company write a 3-4 sentence summary covering: (1) what the company is and does; "
    "(2) its specific products or role; (3) how it relates to the stated MARKET; and (4) why it "
    "belongs in the stated value-chain SECTION. Be concrete and factual. No marketing words "
    "(no 'leading', 'innovative', 'world-class', 'cutting-edge'), no hype, no filler. Use the "
    "provided notes; if a detail is unknown, stay general but accurate and do not invent facts. "
    'Return ONLY JSON: {"items":[{"i":<index>,"summary":"<3-4 sentences>"}]}'
)

DESC_SYS = (
    "You write a factual 3-4 sentence description of a company for a market-research appendix, "
    "based only on the crawled website text provided. Cover what the company does, its products, "
    "and how it relates to the stated MARKET. No marketing language, no invented facts. "
    "Return only the description text."
)


def _u(market: str, section: str, batch: list[dict]) -> str:
    lines = [f"MARKET: {market}", f"SECTION: {section}", "", "COMPANIES (JSON per line):"]
    for it in batch:
        lines.append(
            json.dumps(
                {"i": it["i"], "name": it["name"], "domain": it["domain"],
                 "role": it["role"], "products": it["products"], "notes": it["notes"][:600]},
                ensure_ascii=False,
            )
        )
    return "\n".join(lines)


def summarize_section(client: ClaudeClient, market: str, section: str, rows: list[dict]) -> int:
    items = [
        {
            "i": i,
            "name": r.get("company") or r.get("brand") or "",
            "domain": r.get("domain") or r.get("website") or "",
            "role": r.get("role") or "",
            "products": str(r.get("key_products") or "")[:200],
            "notes": str(r.get("company_summary") or r.get("role_description") or "")[:600],
            "_row": r,
        }
        for i, r in enumerate(rows)
    ]
    done = 0
    for s in range(0, len(items), 8):
        batch = items[s : s + 8]
        try:
            out = client.complete_json(SUM_SYS, _u(market, section, batch), model=HAIKU, max_tokens=2048)
        except Exception as e:
            print(f"    summary batch failed ({section[:20]}): {e}", flush=True)
            continue
        arr = out.get("items") if isinstance(out, dict) else out
        by = {int(x["i"]): str(x.get("summary") or "") for x in (arr or []) if "i" in x}
        for it in batch:
            summ = by.get(it["i"], "").strip()
            if summ:
                it["_row"]["company_summary"] = summ
                done += 1
    return done


async def describe_unverified(client: ClaudeClient, market: str, unv: list[dict]) -> int:
    done = 0
    for u in unv:
        dom = (u.get("domain") or "").strip()
        if not dom:
            continue
        try:
            crawled = await supplement_crawl(dom)
        except Exception:
            crawled = {}

        acc: list[str] = []

        def _collect(obj) -> None:
            if isinstance(obj, str):
                s = obj.strip()
                if len(s) >= 40:
                    acc.append(s)
            elif isinstance(obj, dict):
                for v in obj.values():
                    _collect(v)
            elif isinstance(obj, list):
                for v in obj:
                    _collect(v)

        _collect(crawled)
        seen, parts = set(), []
        for s in acc:
            if s not in seen:
                seen.add(s)
                parts.append(s)
        text = " ".join(parts)[:2200]
        if not text.strip():
            print(f"    no crawl content: {u.get('company')} ({dom})", flush=True)
            continue
        try:
            desc = client.complete(
                DESC_SYS,
                f"MARKET: {market}\nCOMPANY: {u.get('company')}\nWEBSITE: {dom}\n\nCRAWLED TEXT:\n{text}",
                model=HAIKU,
                max_tokens=400,
            )
        except Exception:
            continue
        desc = (desc or "").strip()
        if desc:
            u["reason"] = desc
            done += 1
            print(f"    described: {u.get('company')}", flush=True)
    return done


async def process(jp: Path, client: ClaudeClient) -> None:
    r = json.loads(jp.read_text(encoding="utf-8"))
    ctx = r.get("query_context") or {}
    market = str(ctx.get("industry") or r.get("query") or jp.stem)
    scope = ctx.get("scope") if isinstance(ctx.get("scope"), dict) else r.get("scope")
    mp = main_product_label(ctx, scope if isinstance(scope, dict) else None)
    rows = dedupe_export_rows([c for c in (r.get("relevant_companies") or []) if c.get("is_relevant")])
    custom = [str(s).strip() for s in (ctx.get("sections") or []) if str(s).strip()]
    grouped = (
        group_into_sections(rows, custom, mp, custom=True)
        if custom
        else group_into_sections(rows, build_section_taxonomy(mp), mp)
    )
    total = 0
    if not UNV_ONLY:
        print(f"{jp.name}: summarizing {len(rows)} companies across {len(grouped)} sections...", flush=True)
        for section_name, section_rows in grouped:
            total += summarize_section(client, market, section_name, section_rows)

    # drop any Not-Verified entry that is now an exported company (no double-listing)
    import re as _re

    def _ck(s) -> str:
        return _re.sub(r"[^a-z0-9]", "", str(s or "").lower())

    exp_keys = {_ck(c.get("company") or c.get("brand")) for c in rows if _ck(c.get("company") or c.get("brand"))}
    unv = [
        u
        for u in (r.get("unverified_companies") or [])
        if not any(k and (k == _ck(u.get("company")) or k in _ck(u.get("company")) or _ck(u.get("company")) in k) for k in exp_keys)
    ]
    r["unverified_companies"] = unv
    described = await describe_unverified(client, market, unv) if unv else 0

    jp.write_text(json.dumps(r, indent=2, default=str), encoding="utf-8")
    save_pipeline_csv(r, str(jp.with_suffix(".csv")))
    save_pipeline_docx(r, str(jp.with_suffix(".docx")))
    print(f"{jp.name}: {total} summaries rewritten, {described} not-verified described -> CSV + DOCX", flush=True)


async def main() -> None:
    client = ClaudeClient(Settings.load())
    pats = [a for a in sys.argv[1:] if a != "--unv-only"] or ["waste_oil_market_global_v2.json"]
    for pat in pats:
        for jp in sorted(Path("output/demo").glob(pat)):
            if jp.suffix == ".json":
                await process(jp, client)


if __name__ == "__main__":
    asyncio.run(main())
