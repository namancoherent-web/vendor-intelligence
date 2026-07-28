"""Force a few alias-named must-haves into their correct section, then regenerate
CSV + DOCX. No re-run. Handles SABIC<->Saudi Basic Industries, Idemitsu Lubricants<->Kosan."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from vendor_intel.pipeline.orchestrator import save_pipeline_csv, save_pipeline_docx  # noqa: E402
from vendor_intel.pipeline.sections import match_custom_section  # noqa: E402

# filename-prefix -> [(name substring, target section text)]
TARGETS = {
    "bio_based_ethylene": [("saudi basic", "Polymer Producers"), ("sabic", "Polymer Producers")],
    "waste_oil": [
        ("idemitsu", "Recovered Oil / Base Oil Downstream Offtake"),
    ],
}


def main() -> None:
    for jp in sorted(Path("output/demo").glob("*.json")):
        targets = next((v for k, v in TARGETS.items() if jp.name.startswith(k)), None)
        if not targets:
            continue
        r = json.loads(jp.read_text(encoding="utf-8"))
        taxonomy = [str(s).strip() for s in ((r.get("query_context") or {}).get("sections") or []) if str(s).strip()]
        rel = r.get("relevant_companies") or []
        fixed = 0
        for sub, sec_text in targets:
            sec = match_custom_section(sec_text, taxonomy)
            if not sec:
                continue
            for c in rel:
                if sub in (str(c.get("company") or "") + " " + str(c.get("brand") or "")).lower():
                    if c.get("_forced_section") != sec:
                        c["_forced_section"] = sec
                        c["is_relevant"] = True
                        fixed += 1
        if fixed:
            jp.write_text(json.dumps(r, indent=2, default=str), encoding="utf-8")
            save_pipeline_csv(r, str(jp.with_suffix(".csv")))
            save_pipeline_docx(r, str(jp.with_suffix(".docx")))
            print(f"{jp.name}: forced {fixed} alias must-haves -> regenerated CSV + DOCX")


if __name__ == "__main__":
    main()
