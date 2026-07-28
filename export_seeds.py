"""export_seeds.py <slug>

Build a separate, clean Excel + Word of the curated SEED companies whose websites discovery could
NOT confirm in a run - each profiled properly so the sheet reads like a normal company list.

These are REAL companies from the analyst's curated list; when a site is unreachable we profile the
company from public knowledge with CAUTIOUS, FACTUAL text (no invented specifics). Output:
    output/demo/<slug>_seeds.csv   and   _seeds.docx

Usage (after the run finishes):
    python export_seeds.py satcom_systems_market_global
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from vendor_intel.placeholders.load_keys import apply_env_overrides  # noqa: E402

apply_env_overrides()
from vendor_intel.clients.claude import ClaudeClient  # noqa: E402
from vendor_intel.config import Settings  # noqa: E402
from vendor_intel.pipeline.orchestrator import save_pipeline_csv, save_pipeline_docx  # noqa: E402

HAIKU = "claude-haiku-4-5-20251001"


def _nk(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def _clean_dom(d: str) -> str:
    d = str(d or "").strip().lower()
    return d.removeprefix("https://").removeprefix("http://").removeprefix("www.").split("/")[0]


_SYS = (
    "For each company (name + the SECTION it belongs to + its domain) produce, from public knowledge:\n"
    "- role: a 1-3 word market role that fits the SECTION.\n"
    "- detail: a functionality phrase (max 12 words) describing its activity in the market - no "
    "company name, no marketing words, no trailing period.\n"
    "- summary: 2-3 FACTUAL sentences about the company. Use only what you reliably know; do NOT "
    "invent specific products, figures, customers or claims - stay general but accurate.\n"
    'Return ONLY JSON: {"items":[{"i":<index>,"role":"<label>","detail":"<phrase>","summary":"<2-3 sentences>"}]}'
)


def main() -> None:
    slug = sys.argv[1] if len(sys.argv) > 1 else "satcom_systems_market_global"
    jp = ROOT / "output" / "demo" / f"{slug}.json"
    if not jp.exists():
        print(f"  not found: {jp} (run the pipeline first)")
        return
    result = json.loads(jp.read_text(encoding="utf-8"))
    ctx = result.get("query_context") or {}
    seed_sections: dict = ctx.get("seed_sections") or {}
    seed_names = list(seed_sections.keys()) or [
        str(s) for s in (ctx.get("seed_companies") or []) if str(s).strip()
    ]
    if not seed_names:
        print("  no seed companies recorded in this run's query_context.")
        return
    market = str(ctx.get("industry") or result.get("query") or "")
    country = str(ctx.get("country") or "")

    relevant = [c for c in (result.get("relevant_companies") or []) if c.get("is_relevant")]
    by_name = {_nk(c.get("company") or c.get("brand")): c for c in relevant}

    def _well_profiled(row: dict | None) -> bool:
        if not row:
            return False
        summ = str(row.get("company_summary") or "").strip()
        return len(summ) >= 60 and not row.get("_inferred_profile")

    not_found = []  # (name, section, domain)
    for nm in seed_names:
        row = by_name.get(_nk(nm))
        if _well_profiled(row):
            continue
        dom = _clean_dom((row or {}).get("website") or (row or {}).get("domain") or "")
        not_found.append((nm, seed_sections.get(nm, ""), dom))

    if not_found:
        print(f"  {len(not_found)} seed(s) not confirmed by discovery - profiling them:")
        for nm, sec, _ in not_found:
            print(f"     - {nm}  [{sec or 'no section'}]")
    else:
        print("  every seed was confirmed by discovery - nothing to export.")
        return

    client = ClaudeClient(Settings.load())
    if not getattr(client, "available", False):
        print("  LLM not configured - cannot profile seeds.")
        return

    rows: list[dict] = []
    for s in range(0, len(not_found), 8):
        batch = not_found[s : s + 8]
        payload = [
            {"i": i, "name": n, "section": sec, "domain": d}
            for i, (n, sec, d) in enumerate(batch)
        ]
        user = f"MARKET: {market}\n\nCOMPANIES:\n" + "\n".join(
            json.dumps(p, ensure_ascii=False) for p in payload
        )
        try:
            out = client.complete_json(_SYS, user, model=HAIKU, max_tokens=2560)
        except Exception as e:
            print(f"  profile batch failed: {e}")
            out = {}
        arr = out.get("items") if isinstance(out, dict) else out
        by = {int(x["i"]): x for x in (arr or []) if "i" in x}
        for i, (n, sec, d) in enumerate(batch):
            x = by.get(i, {})
            rows.append(
                {
                    "company": n,
                    "brand": "",
                    "domain": d,
                    "website": (f"https://{d}" if d else ""),
                    "industry": market,
                    "country": country,
                    "is_relevant": True,
                    "role": str(x.get("role") or ""),
                    "market_role": str(x.get("role") or ""),
                    "market_role_detail": str(x.get("detail") or ""),
                    "company_summary": str(x.get("summary") or ""),
                    "_forced_section": sec,
                    "confidence": 0.6,
                }
            )

    result2 = dict(result)
    result2["relevant_companies"] = rows
    result2["unverified_companies"] = []
    # group strictly by each seed's OWN assigned section (not the run's market taxonomy)
    qc2 = dict(ctx)
    qc2["sections"] = sorted({s for s in seed_sections.values() if str(s).strip()})
    qc2["exclude_segments"] = []
    result2["query_context"] = qc2
    csv_path = ROOT / "output" / "demo" / f"{slug}_seeds.csv"
    save_pipeline_csv(result2, str(csv_path))
    try:
        save_pipeline_docx(result2, str(ROOT / "output" / "demo" / f"{slug}_seeds.docx"))
    except Exception as e:
        print(f"  docx export failed: {e}")
    print(f"  wrote {csv_path.name} (+ .docx) with {len(rows)} profiled seed companies")


if __name__ == "__main__":
    main()
