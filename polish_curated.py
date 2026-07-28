"""Polish curated must-have rows: give them accurate role/functionality by section,
drop curated rows that duplicate a real discovered company in the same section, then
regenerate CSV + DOCX. No re-run, no searches.

    python polish_curated.py "waste_oil*.json" "bio_*.json" "satcom*.json" "brazil_rupture*.json"
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from vendor_intel.pipeline.orchestrator import save_pipeline_csv, save_pipeline_docx  # noqa: E402
from vendor_intel.pipeline.sections import custom_section_for_row, match_custom_section  # noqa: E402

GENERIC = {
    "oil", "lubricants", "lubricant", "global", "corporation", "company", "companies",
    "inc", "ltd", "limited", "group", "international", "the", "and", "co", "plc", "llc",
    "gmbh", "corp", "holdings", "industries", "technologies", "systems", "solutions",
}


def toks(s) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", (s or "").lower()) if len(t) >= 3}


def distinctive(s) -> set[str]:
    return toks(s) - GENERIC


def profile(sec: str) -> tuple[str, str]:
    """Return (role, noun-phrase description). Description reads naturally after the role
    prefix, e.g. role 'Manufacturer' + 'industrial lubricants' -> 'Manufacturer of industrial
    lubricants'."""
    s = (sec or "").lower()
    if "offtake" in s or "recovered" in s:
        return "Distributor", "finished lubricants; offtaker of recovered/re-refined base oil"
    if "collection" in s or "aggregation" in s:
        return "Distributor", "used-oil collection and aggregation services"
    if "re-refin" in s or "processing" in s or "rerefin" in s:
        return "Manufacturer", "re-refined base oil (RRBO) from used oil"
    if "generator" in s or "lubricant manufactur" in s:
        return "Manufacturer", "industrial and automotive lubricants"
    if "polymer" in s:
        return "Manufacturer", "polyethylene and polyolefins (bio-based ethylene offtaker)"
    if "core bio" in s or "demonstration" in s:
        return "Manufacturer", "bio-based ethylene and bioethanol"
    if "technology" in s or "enabler" in s:
        return "Technology Provider", "bio-ethylene process technology and catalysts"
    if "equipment manufactur" in s:
        return "Manufacturer", "SATCOM equipment, antennas and terminals"
    if "service provider" in s or "integrator" in s:
        return "Service Provider", "SATCOM services and system integration"
    if "network" in s or "capacity" in s:
        return "Operator", "satellite network and capacity services"
    if "specialized connectivity" in s:
        return "Service Provider", "specialized satellite connectivity solutions"
    if "contract" in s:
        return "Contract Manufacturer", "contract / OEM-ODM manufacturing"
    if "oem" in s or "manufactur" in s:
        return "Manufacturer", "rupture discs and pressure-relief devices"
    if "brand" in s:
        return "Brand", "rupture disc / safety device brand"
    return "Manufacturer", "products in this market"


def polish(jp: Path) -> None:
    r = json.loads(jp.read_text(encoding="utf-8"))
    ctx = r.get("query_context") or {}
    taxonomy = [str(s).strip() for s in (ctx.get("sections") or []) if str(s).strip()]
    rel = r.get("relevant_companies") or []
    real = [c for c in rel if not str(c.get("data_sources") or "").startswith("curated")]
    real_sec = {id(c): (custom_section_for_row(c, taxonomy) if taxonomy else "") for c in real}

    keep, dropped, fixed = [], 0, 0
    for c in rel:
        if str(c.get("data_sources") or "").startswith("curated"):
            fs = match_custom_section(str(c.get("_forced_section") or ""), taxonomy) or c.get("_forced_section")
            dC = distinctive(c.get("company") or c.get("brand"))
            if dC and any(dC <= toks(rc.get("company") or rc.get("brand")) and real_sec.get(id(rc)) == fs for rc in real):
                dropped += 1
                continue
            role, desc = profile(str(c.get("_forced_section") or ""))
            c["role"], c["role_description"], c["company_function"] = role, desc, desc
            c["company_summary"] = f"{c.get('company')} - {desc}."
            fixed += 1
        keep.append(c)

    r["relevant_companies"] = keep
    jp.write_text(json.dumps(r, indent=2, default=str), encoding="utf-8")
    save_pipeline_csv(r, str(jp.with_suffix(".csv")))
    save_pipeline_docx(r, str(jp.with_suffix(".docx")))
    print(f"{jp.name}: dropped {dropped} duplicate curated rows, fixed {fixed} functionalities -> CSV + DOCX")


def main() -> None:
    pats = sys.argv[1:] or ["waste_oil*.json", "bio_based_ethylene*.json", "satcom*.json", "brazil_rupture*.json"]
    for pat in pats:
        for jp in sorted(Path("output/demo").glob(pat)):
            if jp.suffix == ".json":
                polish(jp)


if __name__ == "__main__":
    main()
