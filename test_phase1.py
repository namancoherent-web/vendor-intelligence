#!/usr/bin/env python3
"""
TEMPORARY — Phase 1 market-understanding inspector.

Run ONLY Phase 1 (no discovery/crawl/classify). Shows what the LLM understood
about your market and which search queries it generated.

Delete this file when you finish validating Phase 1.

Usage:
  .venv\\Scripts\\python.exe test_phase1.py --query "Digital Signage System Market"
  .venv\\Scripts\\python.exe test_phase1.py -q "Aluminium Cladding Europe" --country Europe
  .venv\\Scripts\\python.exe test_phase1.py -q "Atomic Clock Market" --with-search

Output:
  Console report (detailed)
  output/phase1_debug/<slug>.md
  output/phase1_debug/<slug>.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
DEBUG_DIR = ROOT / "output" / "phase1_debug"


def _slug(query: str, country: str) -> str:
    text = f"{query}_{country}".lower()
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")[:72] or "phase1_test"


def _load_settings():
    from vendor_intel.placeholders.load_keys import apply_env_overrides
    from vendor_intel.config import Settings

    apply_env_overrides()
    return Settings.load()


def _verdict(scope: dict, manifest: dict) -> tuple[str, list[str]]:
    """Quick health check — is Phase 1 LLM understanding good?"""
    notes: list[str] = []
    source = str(scope.get("scope_source") or manifest.get("scope_source") or "?")
    map_src = str(scope.get("market_map_source") or "?")

    if map_src == "offline" or "offline" in source.lower():
        notes.append("Market map used OFFLINE fallback — LLM response was thin or API failed.")
    if not scope.get("market_definition"):
        notes.append("Missing market_definition.")
    layers = scope.get("value_chain_layers") or []
    if len(layers) < 2:
        notes.append(f"Only {len(layers)} value-chain layer(s) — expected 3–5.")
    include_kw = scope.get("include_keywords") or []
    if len(include_kw) < 3:
        notes.append(f"Only {len(include_kw)} include_keywords — weak market filter.")
    prompts = manifest.get("discovery_prompts") or []
    disc_count = len([p for p in prompts if p.get("id") not in {"L0", "L1", "L2"}])
    if disc_count < 8:
        notes.append(f"Only {disc_count} discovery prompts — expected 12–18.")
    seeds = scope.get("seed_companies") or []
    if len(seeds) < 4:
        notes.append(f"Only {len(seeds)} seed companies.")

    if not notes:
        return "GOOD", ["LLM market map looks complete — layers, keywords, prompts, and seeds present."]
    if map_src == "offline":
        return "FAIL", notes
    if len(notes) <= 2:
        return "PARTIAL", notes
    return "WARN", notes


def _section(title: str, lines: list[str]) -> str:
    body = "\n".join(lines) if lines else "  (none)"
    return f"\n## {title}\n\n{body}\n"


def _format_layers(layers: list) -> list[str]:
    out: list[str] = []
    for layer in layers:
        if not isinstance(layer, dict):
            continue
        lid = layer.get("layer_id") or "?"
        lname = layer.get("layer_name") or ""
        desc = str(layer.get("description") or "")[:200]
        out.append(f"### {lid}: {lname}")
        if desc:
            out.append(f"  {desc}")
        for seg in layer.get("segments") or []:
            if not isinstance(seg, dict):
                continue
            sname = seg.get("segment_name") or "?"
            subs = seg.get("sub_segments") or []
            parts = seg.get("participant_types") or []
            intents = seg.get("search_intents") or []
            out.append(f"  - **{sname}**")
            if subs:
                out.append(f"    sub_segments: {', '.join(str(x) for x in subs)}")
            if parts:
                out.append(f"    participant_types: {', '.join(str(x) for x in parts)}")
            if intents:
                for i, intent in enumerate(intents, 1):
                    out.append(f"    search_intent_{i}: {intent}")
    return out


def build_report(query: str, country: str, manifest: dict) -> str:
    scope = manifest.get("scope") or {}
    status, notes = _verdict(scope, manifest)
    boundary = scope.get("market_boundary") if isinstance(scope.get("market_boundary"), dict) else {}

    lines: list[str] = [
        f"# Phase 1 Debug Report",
        f"",
        f"**Query:** {query}",
        f"**Geography:** {country}",
        f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"**Verdict:** {status}",
        f"",
        f"### Health notes",
    ]
    for n in notes:
        lines.append(f"- {n}")

    meta = [
        f"- scope_source: `{scope.get('scope_source', manifest.get('scope_source', '?'))}`",
        f"- market_map_source: `{scope.get('market_map_source', '?')}`",
        f"- market: `{scope.get('market', '?')}`",
        f"- search_topic: `{scope.get('search_topic', '?')}`",
        f"- industry_vertical: `{scope.get('industry_vertical') or manifest.get('industry_vertical') or '—'}`",
        f"- LLM provider: `{manifest.get('llm_provider', '?')}`",
    ]
    lines.append(_section("Pipeline metadata", meta))

    defn = str(scope.get("market_definition") or "").strip()
    lines.append(_section("Market definition (LLM)", [defn] if defn else ["(empty)"]))

    in_scope = boundary.get("in_scope") or []
    out_scope = boundary.get("out_of_scope") or []
    boundary_lines = []
    if in_scope:
        boundary_lines.append("**In scope:**")
        boundary_lines.extend(f"  - {x}" for x in in_scope)
    if out_scope:
        boundary_lines.append("**Out of scope:**")
        boundary_lines.extend(f"  - {x}" for x in out_scope)
    lines.append(_section("Market boundary", boundary_lines))

    for label, key in (
        ("Include keywords (market fit)", "include_keywords"),
        ("Exclude keywords (reject junk)", "exclude_keywords"),
        ("Industry terms", "industry_terms"),
        ("Ecosystem functions", "ecosystem_functions"),
        ("Relevance keywords", "relevance_keywords"),
        ("Negative keywords", "negative_keywords"),
    ):
        vals = scope.get(key) or []
        lines.append(_section(label, [f"  - {v}" for v in vals] if vals else []))

    layers = scope.get("value_chain_layers") or []
    lines.append(_section("Value chain layers", _format_layers(layers)))

    lines.append(_section("Funnel prompts (L0–L2)", [
        f"  [{p.get('id', '?')}] {p.get('text', '')}"
        for p in (manifest.get("funnel_prompts") or [])
    ]))

    disc = manifest.get("discovery_prompts") or []
    disc_lines = []
    for p in disc:
        pid = p.get("id", "?")
        if pid in {"L0", "L1", "L2"}:
            continue
        seg = p.get("segment") or p.get("sub_sector") or ""
        tag = f" [{seg}]" if seg else ""
        disc_lines.append(f"  [{pid}]{tag} {p.get('text', '')}")
    lines.append(_section(f"Discovery prompts ({len(disc_lines)} searches)", disc_lines))

    seeds = scope.get("seed_companies") or []
    seed_lines = []
    for s in seeds:
        if isinstance(s, dict):
            seed_lines.append(
                f"  - {s.get('canonical_name', '?')} | {s.get('primary_domain', '—')} "
                f"| {s.get('company_function', '')} | segment: {s.get('segment', '')}"
            )
        else:
            seed_lines.append(f"  - {s}")
    lines.append(_section(f"Seed companies ({len(seeds)})", seed_lines))

    smoke = manifest.get("search_smoke_test") or {}
    if smoke:
        smoke_lines = []
        for pid, info in smoke.items():
            smoke_lines.append(
                f"  [{pid}] {info.get('result_count', 0)} results — {info.get('query', '')[:70]}"
            )
        lines.append(_section("Search smoke test", smoke_lines))

    for w in manifest.get("warnings") or []:
        lines.append(f"\n> Warning: {w}\n")

    lines.append(f"\n---\nFull JSON: `output/phase1_debug/{_slug(query, country)}.json`\n")
    return "\n".join(lines)


def print_console_report(report_md: str) -> None:
    """Strip markdown bold for terminal."""
    plain = report_md.replace("**", "")
    print(plain)


def _parse_line(raw: str) -> tuple[str, str]:
    if "|" in raw:
        parts = raw.split("|", 1)
        return parts[0].strip(), (parts[1].strip() or "global")
    return raw.strip(), "global"


def _full_query(query: str, country: str) -> str:
    if country.lower() in ("global", "worldwide"):
        return query
    return f"{query} in {country}"


def _run_one_phase1(query: str, country: str, settings, *, with_search: bool) -> str:
    from vendor_intel.phase1.runner import run_phase1_sync, print_phase1_summary

    full_query = _full_query(query, country)
    print("=" * 60)
    print("  PHASE 1 TEST (temporary inspector)")
    print(f"  Query: {full_query}")
    print("=" * 60)

    manifest = run_phase1_sync(full_query, settings)
    try:
        print_phase1_summary(manifest)
    except UnicodeEncodeError:
        print("  (Summary skipped — Windows console encoding; see .md report below)\n")

    report = build_report(query, country, manifest)
    print_console_report(report)

    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    slug = _slug(query, country)
    md_path = DEBUG_DIR / f"{slug}.md"
    json_path = DEBUG_DIR / f"{slug}.json"
    md_path.write_text(report, encoding="utf-8")
    json_path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")

    print(f"\n  Saved report : {md_path}")
    print(f"  Saved JSON   : {json_path}")
    print(
        f"\n  Google Alerts: .venv\\Scripts\\python.exe suggest_google_alerts.py "
        f"--from {json_path}"
    )
    return str(json_path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="TEMPORARY Phase 1 inspector — delete when validation is done."
    )
    parser.add_argument("--query", "-q", help="Market query to test")
    parser.add_argument("--country", "-c", default="global", help="Geography (default: global)")
    parser.add_argument("--file", "-f", help="Batch file: one 'query | country' per line")
    parser.add_argument(
        "--with-search",
        action="store_true",
        help="Run search smoke test too (slower; default is plan-only)",
    )
    args = parser.parse_args()

    if not args.query and not args.file:
        parser.error("Provide --query or --file")

    settings = _load_settings()
    if not args.with_search:
        import vendor_intel.pipeline.geo_limits as _geo_limits

        _orig_limits = _geo_limits.pipeline_limits

        def _plan_only_limits(settings, *, recall, country):
            lim = _orig_limits(settings, recall=recall, country=country)
            return {**lim, "smoke_prompts": 0}

        _geo_limits.pipeline_limits = _plan_only_limits
        print("  [test_phase1] Search smoke test OFF (plan only). Use --with-search to test search.\n")

    jobs: list[tuple[str, str]] = []
    if args.file:
        path = Path(args.file)
        if not path.is_absolute():
            path = ROOT / path
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            jobs.append(_parse_line(line))
    else:
        jobs.append((args.query.strip(), (args.country or "global").strip()))

    for i, (query, country) in enumerate(jobs, 1):
        if len(jobs) > 1:
            print(f"\n>>> Batch {i}/{len(jobs)}: {query} ({country})\n")
        _run_one_phase1(query, country, settings, with_search=args.with_search)

    if len(jobs) > 1:
        print("\n  Batch complete. Check output/phase1_debug/ for all reports.")
    print("\n  When done validating, delete test_phase1.py and output/phase1_debug/\n")


if __name__ == "__main__":
    main()
