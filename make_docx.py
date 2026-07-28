#!/usr/bin/env python3
"""Generate the CEO Word doc from saved pipeline result JSON(s) — no pipeline re-run needed.

Usage:
  python make_docx.py                      # all output/demo/*.json
  python make_docx.py output/demo/foo.json # one file
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from vendor_intel.pipeline.orchestrator import save_pipeline_docx


def _gen(json_path: Path) -> None:
    result = json.loads(json_path.read_text(encoding="utf-8"))
    out = save_pipeline_docx(result, str(json_path.with_suffix(".docx")))
    n = len([r for r in (result.get("relevant_companies") or []) if r.get("is_relevant")])
    print(f"  {json_path.name} -> {out}  ({n} companies)")


def main() -> None:
    args = [a for a in sys.argv[1:] if a.strip()]
    if args:
        targets = [Path(a) for a in args]
    else:
        demo = ROOT / "output" / "demo"
        targets = [p for p in sorted(demo.glob("*.json")) if p.name != "session_log.json"]
    if not targets:
        print("No result JSONs found. Pass one: python make_docx.py output/demo/<slug>.json")
        return
    for t in targets:
        try:
            _gen(t)
        except Exception as exc:
            print(f"  skip {t.name}: {exc}")


if __name__ == "__main__":
    main()
