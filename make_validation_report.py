#!/usr/bin/env python3
"""Validation report from saved pipeline result JSON(s) — no re-run needed.

Reads output/demo/*.json (or paths you pass), and for each market reports:
total exported, must-capture present/missing, section + confidence distribution,
and the "could not confirm" list with reasons. Writes validation_report.txt.

Usage:
  python make_validation_report.py                         # all output/demo/*v2*.json + *v1*.json
  python make_validation_report.py output/demo/foo.json    # specific files
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _exported(result: dict) -> list[dict]:
    return [c for c in (result.get("relevant_companies") or []) if c.get("is_relevant")]


def _section_counts(result: dict) -> list[tuple[str, int]]:
    from vendor_intel.pipeline.sections import (
        build_section_taxonomy,
        group_into_sections,
        main_product_label,
    )

    ctx = result.get("query_context") or {}
    scope = ctx.get("scope") if isinstance(ctx.get("scope"), dict) else result.get("scope")
    mp = main_product_label(ctx, scope if isinstance(scope, dict) else None)
    rows = _exported(result)
    custom = [str(s).strip() for s in (ctx.get("sections") or []) if str(s).strip()]
    if custom:
        grouped = group_into_sections(rows, custom, mp, custom=True)
    else:
        grouped = group_into_sections(rows, build_section_taxonomy(mp), mp)
    return [(name, len(rs)) for name, rs in grouped]


def report_one(jp: Path) -> str:
    r = json.loads(jp.read_text(encoding="utf-8"))
    ctx = r.get("query_context") or {}
    market = str(ctx.get("industry") or r.get("query") or jp.stem)
    country = str(ctx.get("country") or "global")
    exported = _exported(r)
    unverified = r.get("unverified_companies") or []
    musts = [str(s).strip() for s in (ctx.get("seed_companies") or []) if str(s).strip()]

    def _toks(s: str) -> set[str]:
        return {t for t in re.findall(r"[a-z0-9]+", (s or "").lower()) if len(t) >= 4}

    # acronym / legal-name aliases that plain substring matching would miss
    ALIAS = {
        "sabic": "saudibasic",
        "indianoilservo": "iocl",
        "hplubricants": "hindustanpetroleum",
        "fuchspetrolub": "fuchs",
    }

    exp_names = [_norm(c.get("company") or "") for c in exported]
    exp_doms = [_norm(c.get("domain") or c.get("website") or "") for c in exported]
    exp_toks = [_toks(c.get("company") or "") for c in exported]
    exp_keys = [k for k in (exp_names + exp_doms) if k]
    unv = {_norm(u.get("company") or ""): str(u.get("reason") or "") for u in unverified}

    def _is_present(nm: str, mt: set[str]) -> bool:
        if nm and any(nm in e or e in nm for e in exp_keys):
            return True
        if mt and any(mt & et for et in exp_toks):  # shared significant word
            return True
        ali = ALIAS.get(nm)
        if ali and any(ali in e for e in exp_names + exp_doms):
            return True
        return False

    present, in_notfound, missing = [], [], []
    for m in musts:
        nm = _norm(m)
        if _is_present(nm, _toks(m)):
            present.append(m)
        elif nm and any(nm in k or k in nm for k in unv):
            reason = next((v for k, v in unv.items() if nm in k or k in nm), "")
            in_notfound.append(f"{m}  [{reason}]")
        else:
            missing.append(m)

    conf = Counter()
    for c in exported:
        v = float(c.get("confidence") or 0)
        conf["high (0.85+)" if v >= 0.85 else "medium (0.70-0.84)" if v >= 0.70 else "low (<0.70)"] += 1

    lines = []
    lines.append("=" * 70)
    lines.append(f"MARKET: {market}  ({country})")
    lines.append(f"FILE:   {jp.name}")
    lines.append("=" * 70)
    lines.append(f"TOTAL COMPANIES EXPORTED: {len(exported)}")
    lines.append("")
    lines.append(f"MUST-CAPTURE CHECK ({len(musts)} listed):")
    lines.append(f"  present in output : {len(present)}")
    lines.append(f"  in 'not confirmed': {len(in_notfound)}")
    lines.append(f"  missing entirely  : {len(missing)}")
    if in_notfound:
        lines.append("  -- could not confirm (with reason):")
        for x in in_notfound:
            lines.append(f"     - {x}")
    if missing:
        lines.append("  -- missing entirely:")
        for x in missing:
            lines.append(f"     - {x}")
    lines.append("")
    lines.append("SECTION DISTRIBUTION:")
    for name, n in _section_counts(r):
        lines.append(f"  {name}: {n}")
    lines.append("")
    lines.append("CONFIDENCE DISTRIBUTION:")
    for k in ("high (0.85+)", "medium (0.70-0.84)", "low (<0.70)"):
        lines.append(f"  {k}: {conf.get(k, 0)}")
    lines.append("")
    lines.append(f"NOT-VERIFIED / COULD-NOT-CONFIRM TOTAL: {len(unverified)}")
    rej = r.get("export_rejected_count")
    if rej is not None:
        lines.append(f"REJECTED (junk/off-market) COUNT: {rej}")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    args = [Path(a) for a in sys.argv[1:] if a.strip()]
    if not args:
        demo = ROOT / "output" / "demo"
        args = [p for p in sorted(demo.glob("*.json")) if p.name != "session_log.json"]
    if not args:
        print("No result JSONs found.")
        return
    out = []
    for jp in args:
        try:
            out.append(report_one(jp))
        except Exception as exc:
            out.append(f"skip {jp.name}: {exc}\n")
    text = "\n".join(out)
    print(text)
    dest = ROOT / "validation_report.txt"
    dest.write_text(text, encoding="utf-8")
    print(f"\nSaved: {dest}")


if __name__ == "__main__":
    main()
