"""Regenerate CSV + DOCX from an already-saved result JSON (no LLM, no re-run).
Use after closing the file in Excel/Word so it writes back to the clean filename.

    python resave.py "satcom.json" "rupture_disc_brazil.json"
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from vendor_intel.pipeline.orchestrator import save_pipeline_csv, save_pipeline_docx  # noqa: E402

for pat in sys.argv[1:] or ["*.json"]:
    for jp in sorted(Path("output/demo").glob(pat)):
        if jp.suffix != ".json":
            continue
        r = json.loads(jp.read_text(encoding="utf-8"))
        save_pipeline_csv(r, str(jp.with_suffix(".csv")))
        save_pipeline_docx(r, str(jp.with_suffix(".docx")))
        print(f"{jp.name}: resaved CSV + DOCX", flush=True)
