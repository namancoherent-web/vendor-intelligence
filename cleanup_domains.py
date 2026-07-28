"""Fix must-have company websites in existing outputs (replace junk/directory domains
with correct official ones) and regenerate CSV + DOCX. No pipeline re-run, no searches.

    python cleanup_domains.py "bio_based_ethylene*.json" "waste_oil*.json"
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from vendor_intel.pipeline.orchestrator import save_pipeline_csv, save_pipeline_docx  # noqa: E402


def ck(s) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


# Correct official domains for the curated must-haves ("" = no confident site -> blank).
CURATED = {
    # waste oil
    "castrol": "castrol.com", "bp": "bp.com", "shelllubricants": "shell.com",
    "exxonmobillubricants": "mobil.com", "chevronlubricants": "chevronlubricants.com",
    "totalenergieslubricants": "totalenergies.com", "fuchspetrolub": "fuchs.com",
    "valvolineglobal": "valvolineglobal.com", "petronaslubricants": "pli-petronas.com",
    "safetykleensystems": "safety-kleen.com", "lorcopetroleumservices": "lorcopetroleum.com",
    "slickerrecycling": "slickerrecycling.com", "goinswasteoil": "goinswasteoilcompany.com",
    "solwayrecycling": "solwayrecycling.co.uk", "jjrichardsandsons": "jjrichards.com.au",
    "terrapureenvironmental": "terrapureenv.com", "orrcorecycles": "orrco.net",
    "heritagecrystalclean": "crystal-clean.com", "vertexenergy": "vertexenergy.com",
    "gflenvironmental": "gflenv.com", "avistaoilag": "avista-oil.group",
    "puraglobe": "puraglobe.com", "itelyumregeneration": "itelyum.com",
    "southernoilrefining": "southernoilrefining.com.au", "oilrerefiningcompanyinc": "",
    "phillips66lubricants": "phillips66lubricants.com", "indianoilservo": "iocl.com",
    "hplubricants": "hplubricants.in", "gulfoillubricants": "gulfoilltd.com",
    "motul": "motul.com", "skenmove": "skenmove.com", "repsollubricants": "repsol.com",
    "idemitsulubricants": "idemitsu.com",
    # bio-based ethylene
    "braskem": "braskem.com", "sekab": "sekab.com", "dow": "dow.com",
    "lyondellbasell": "lyondellbasell.com", "basf": "basf.com", "sabic": "sabic.com",
    "totalenergies": "totalenergies.com", "ineos": "ineos.com", "axens": "axens.net",
    "technipenergies": "technipenergies.com", "lanzatech": "lanzatech.com",
}

# Directory / junk domains to blank wherever they appear.
BAD = (
    "cbinsights.com", "oilmonster.com", "zaubacorp.com", "zoominfo.com", "leadiq.com",
    "tomdwyer.com", "simplybook.me", "azureedge.net", "industry-plaza.com",
    "crunchbase.com", "dnb.com", "mercadopago", "slideserve", "zauba",
)


def fix_dom(c: dict) -> int:
    name = ck(c.get("company") or c.get("brand"))
    cur = str(c.get("domain") or c.get("website") or "").lower().removeprefix("www.")
    new = None
    # curated override for must-haves (exact, or name contains the curated key)
    for key, dom in CURATED.items():
        if name == key or (len(key) >= 5 and key in name):
            new = dom
            break
    if new is None and any(b in cur for b in BAD):
        new = ""  # blank junk for non-curated rows
    if new is None:
        return 0
    if new == cur:
        return 0
    c["domain"] = new
    c["website"] = new
    return 1


def main() -> None:
    pats = sys.argv[1:] or ["bio_based_ethylene*.json", "waste_oil*.json"]
    files: list[Path] = []
    for pat in pats:
        files += [p for p in sorted(Path("output/demo").glob(pat)) if p.suffix == ".json"]
    for jp in files:
        r = json.loads(jp.read_text(encoding="utf-8"))
        fixed = sum(fix_dom(c) for c in (r.get("relevant_companies") or []))
        jp.write_text(json.dumps(r, indent=2, default=str), encoding="utf-8")
        save_pipeline_csv(r, str(jp.with_suffix(".csv")))
        save_pipeline_docx(r, str(jp.with_suffix(".docx")))
        print(f"{jp.name}: fixed {fixed} websites -> regenerated CSV + DOCX")


if __name__ == "__main__":
    main()
