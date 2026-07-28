"""Post-process existing run outputs: place curated must-haves (seed files with
'Name | Section') into their assigned sections and regenerate CSV + DOCX.

No pipeline re-run. Usage:
    python patch_seed_sections.py "bio_based_ethylene*.json" "waste_oil*.json"
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from vendor_intel.placeholders.load_keys import apply_env_overrides  # noqa: E402

apply_env_overrides()
from vendor_intel.config import Settings  # noqa: E402
from vendor_intel.pipeline.orchestrator import (  # noqa: E402
    save_pipeline_csv,
    save_pipeline_docx,
)
from vendor_intel.pipeline.plan_seeds import resolve_user_seeds  # noqa: E402

# load run_query for its keyword-matching seed loader
_spec = importlib.util.spec_from_file_location("rq", str(ROOT / "run_query.py"))
rq = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rq)


def ck(s) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def dnorm(c: dict) -> str:
    return (str(c.get("domain") or c.get("website") or "")).lower().removeprefix("www.").strip("/")


# Accurate (not fabricated) generic role/functionality for must-haves added as new rows.
ADDED_PROFILE = {
    "polymer producers": (
        "Manufacturer",
        "Polyolefin/polymer producer and offtaker of bio-based ethylene for bio-PE",
        "polyethylene, polymers",
    ),
    "recovered oil / base oil downstream offtake companies": (
        "Distributor",
        "Lubricant blender/marketer; downstream offtaker of recovered/re-refined base oil",
        "lubricants, base oils",
    ),
    "recovered oil / base oil utilization / downstream offtake companies": (
        "Distributor",
        "Lubricant blender/marketer; downstream offtaker of recovered/re-refined base oil",
        "lubricants, base oils",
    ),
    "core bio-ethylene & demonstration producers": (
        "Manufacturer",
        "Bio-based ethylene producer (commercial / demonstration scale)",
        "bio-ethylene, bio-ethanol",
    ),
    "technology / future supply enablers": (
        "Technology Provider",
        "Process technology / catalyst licensor enabling bio-ethylene supply",
        "process technology, catalysts",
    ),
}


def _match(k: str, pk: str) -> bool:
    if not k or not pk:
        return False
    return k == pk or (len(k) >= 5 and k in pk) or (len(pk) >= 5 and pk in k)


async def patch_file(jp: Path, settings) -> None:
    r = json.loads(jp.read_text(encoding="utf-8"))
    ctx = r.get("query_context") or {}
    market, country = str(ctx.get("industry") or ""), str(ctx.get("country") or "global")
    seed_pairs = [(n, s) for n, s in rq._auto_seed_names(market, country) if s]
    if not seed_pairs:
        print(f"{jp.name}: no sectioned seeds matched ({market}) - skipped")
        return

    relevant = r.get("relevant_companies") or []
    pool: dict[str, dict] = {}
    for c in relevant + (r.get("all_classified") or []) + (r.get("export_rejected") or []):
        key = ck(c.get("company") or c.get("brand"))
        if key and key not in pool:
            pool[key] = c
    rel_keys = {ck(c.get("company") or c.get("brand")) for c in relevant}

    sec_map: dict[str, str] = {}
    to_add: list[tuple[str, str]] = []
    reassigned = 0
    for name, section in seed_pairs:
        sec_map[name] = section
        k = ck(name)
        hit = next((c for pk, c in pool.items() if _match(k, pk)), None)
        if hit:
            hit["_forced_section"] = section
            hit["is_relevant"] = True
            mk = ck(hit.get("company") or hit.get("brand"))
            if mk not in rel_keys:
                relevant.append(hit)
                rel_keys.add(mk)
            reassigned += 1
        else:
            to_add.append((name, section))

    added = 0
    if to_add:
        resolved, _ = await resolve_user_seeds([n for n, _ in to_add], settings, country)
        dom_by = {ck(x["canonical_name"]): x["primary_domain"] for x in resolved}
        for name, section in to_add:
            dom = dom_by.get(ck(name), "")
            # if a company with this domain already exists, just force its section (no dup)
            existing = None
            if dom:
                dl = dom.lower().removeprefix("www.")
                existing = next(
                    (c for c in relevant + list(pool.values()) if dnorm(c) == dl), None
                )
            if existing is not None:
                existing["_forced_section"] = section
                existing["is_relevant"] = True
                mk = ck(existing.get("company") or existing.get("brand"))
                if mk not in rel_keys:
                    relevant.append(existing)
                    rel_keys.add(mk)
                reassigned += 1
                continue
            role, desc, prod = ADDED_PROFILE.get(section.strip().lower(), ("Manufacturer", "", ""))
            relevant.append(
                {
                    "company": name,
                    "brand": name,
                    "domain": dom,
                    "website": dom,
                    "role": role,
                    "role_description": desc,
                    "key_products": prod,
                    "is_relevant": True,
                    "confidence": 0.7,
                    "quality_score": 0.7,
                    "is_seed": True,
                    "_forced_section": section,
                    "company_summary": "",
                    "data_sources": "curated (analyst must-have)",
                }
            )
            added += 1

    r["relevant_companies"] = relevant
    ctx["seed_sections"] = sec_map
    r["query_context"] = ctx
    jp.write_text(json.dumps(r, indent=2, default=str), encoding="utf-8")
    save_pipeline_csv(r, str(jp.with_suffix(".csv")))
    save_pipeline_docx(r, str(jp.with_suffix(".docx")))
    print(f"{jp.name}: reassigned {reassigned}, added {added} must-haves -> regenerated CSV + DOCX")


async def main() -> None:
    settings = Settings.load()
    pats = sys.argv[1:] or ["bio_based_ethylene*.json", "waste_oil*.json"]
    files: list[Path] = []
    for pat in pats:
        files += [p for p in sorted(Path("output/demo").glob(pat)) if p.suffix == ".json"]
    if not files:
        print("no matching result JSONs found")
        return
    for jp in files:
        await patch_file(jp, settings)


if __name__ == "__main__":
    asyncio.run(main())
