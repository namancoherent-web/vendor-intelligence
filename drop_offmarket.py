"""Remove companies the role pass flagged as off-market / not-in-this-market (e.g. 'Manufactures
compressors, not rupture discs', 'Off-Market', 'no accessible company information'), then
regenerate CSV + DOCX with updated counts. No pipeline re-run. CURATED seed-file must-haves are
never dropped.

    python drop_offmarket.py "rupture_disc_brazil.json" "satcom.json"
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from vendor_intel.pipeline.orchestrator import save_pipeline_csv, save_pipeline_docx  # noqa: E402
from vendor_intel.pipeline.role_labels import is_offmarket  # noqa: E402


def _nk(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def _negation(text: str) -> bool:
    t = (text or "").lower()
    explicit = (
        "off-market", "no accessible company information", "no active presence", "not core ",
        "does not manufacture", "does not produce", "no documented", "not a participant",
        "insufficient evidence of", "not involved in",
    )
    if any(p in t for p in explicit):
        return True
    # ', not <market product>' — explicit product negation
    if ", not " in t:
        after = t.split(", not ", 1)[1][:60]
        if any(w in after for w in ("rupture", "pressure relief", "bursting", "satcom")):
            return True
    return False


def main() -> None:
    for pat in sys.argv[1:] or ["rupture_disc_brazil.json"]:
        for jp in sorted(Path("output/demo").glob(pat)):
            if jp.suffix != ".json":
                continue
            r = json.loads(jp.read_text(encoding="utf-8"))
            curated = {_nk(n) for n in ((r.get("query_context") or {}).get("seed_sections") or {})}

            def _curated(name: str) -> bool:
                k = _nk(name)
                return any(k and (k == c or (len(k) >= 5 and k in c) or (len(c) >= 5 and c in k)) for c in curated)

            dropped = []
            for c in r.get("relevant_companies") or []:
                if not c.get("is_relevant") or _curated(c.get("company") or c.get("brand")):
                    continue
                text = " ".join(str(c.get(k) or "") for k in ("market_role", "market_role_detail", "role_description"))
                if is_offmarket(c) or _negation(text):
                    c["is_relevant"] = False
                    dropped.append(c.get("company") or c.get("brand"))
            jp.write_text(json.dumps(r, indent=2, default=str), encoding="utf-8")
            save_pipeline_csv(r, str(jp.with_suffix(".csv")))
            save_pipeline_docx(r, str(jp.with_suffix(".docx")))
            print(f"{jp.name}: removed {len(dropped)} off-market companies", flush=True)
            for d in dropped:
                if d:
                    print(f"    - {d}", flush=True)


if __name__ == "__main__":
    main()
