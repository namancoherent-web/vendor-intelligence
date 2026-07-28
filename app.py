#!/usr/bin/env python3
"""
Vendor Intelligence — Streamlit UI (single clean flow)

Run:
  .venv\\Scripts\\python.exe -m streamlit run app.py
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

import pandas as pd
import streamlit as st

logging.getLogger("streamlit").setLevel(logging.ERROR)

from ui.bootstrap import env_warnings, init_env, load_settings, output_dir
from ui.services import (
    JobRunner,
    list_owned_runs,
    list_result_csvs_for_owner,
    pipeline_busy_reason,
    pipeline_is_busy,
    run_slug_from_entry,
)
from ui.job_registry import get_job, jobs_for_owner, upsert_job
from ui.styles import CUSTOM_CSS
from ui.auth_gate import require_login

st.set_page_config(
    page_title="Vendor Intelligence",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="collapsed",
)

init_env()

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# --- Auth gate (email OTP + 24h session) ---
_auth_user = require_login()
if not _auth_user:
    st.stop()


def _set_query_params(**updates: str) -> None:
    """Update URL query params while always preserving the auth token (?s=)."""
    params = dict(st.query_params)
    for k, v in updates.items():
        if v is None or v == "":
            params.pop(k, None)
        else:
            params[k] = v
    token = st.session_state.get("auth_token")
    if token:
        params["s"] = token
    st.query_params.from_dict(params)


def _hydrate_job_from_durable_store(run_id: str | None, owner_email: str) -> dict | None:
    """Load job status from GCS/local when this instance has no in-memory job.

    With an explicit ``run_id`` (from ``?run=``), load that job (any status).
    Without one, only auto-attach a **still-running** job — never cancelled /
    finished leftovers that would trap a fresh login on empty Step 3.
    """
    try:
        from vendor_intel.storage.gcs_export import (
            list_job_statuses_for_owner,
            pull_job_status,
            status_to_registry_job,
        )
    except Exception:
        return None

    status = None
    if run_id:
        status = pull_job_status(run_id)
        owner = (owner_email or "").strip().lower()
        status_owner = str((status or {}).get("owner_email") or "").strip().lower()
        if status and status_owner and status_owner != owner:
            status = None
    else:
        # Fresh login / no ?run= — only reconnect to a live pipeline.
        for cand in list_job_statuses_for_owner(owner_email):
            if cand.get("running") or cand.get("status") == "running":
                status = cand
                break
    if not status:
        return None
    job = status_to_registry_job(status)
    return upsert_job(job)


# Job state lives in ui.job_registry (process-wide, keyed by run_id), not
# st.session_state — the run_id below travels in the URL so a reload finds
# the same job instead of losing track of it (session_state resets on reload).
_run_id = st.query_params.get("run")
_active = get_job(_run_id)

# After a WebSocket drop / auto-reload, ?run= is sometimes lost even though the
# worker is still running on this instance. Re-attach **running** jobs only
# (do not steal the wizard for old cancelled/finished runs).
if not _active:
    for _cand in jobs_for_owner(_auth_user["email"]):
        age_h = (time.time() - float(_cand.get("started_at") or 0)) / 3600.0
        if age_h > 8:
            continue
        if _cand.get("running"):
            _active = _cand
            _rid = str(_cand.get("run_id") or "")
            if _rid and st.query_params.get("run") != _rid:
                _set_query_params(run=_rid)
            break

# Cross-instance reconnect: durable job status in GCS / local job_status/
if not _active:
    _active = _hydrate_job_from_durable_store(_run_id, _auth_user["email"])
    if _active and _active.get("running"):
        _rid = str(_active.get("run_id") or "")
        if _rid and st.query_params.get("run") != _rid:
            _set_query_params(run=_rid)

st.session_state.active_job = _active or {"running": False}

# If we reattached a live run, stay on Step 3 after hard refresh.
if _active and _active.get("running"):
    st.session_state["_wiz_leave_step3"] = False
    wiz0 = st.session_state.setdefault(
        "wiz",
        {"market": "", "geography": "global", "profile": "quality", "cap": "focused"},
    )
    q = str(_active.get("query") or "").strip()
    if q and not str(wiz0.get("market") or "").strip():
        wiz0["market"] = q
    ctry = str(_active.get("country") or "").strip()
    if ctry:
        wiz0["geography"] = ctry

# Stale ?run= (cancelled / empty) should not pin the wizard on Step 3 forever.
if (
    _run_id
    and _active
    and not _active.get("running")
    and not _active.get("result")
    and not _active.get("has_result")
    and _active.get("status") in ("cancelled", "error", "interrupted", None, "")
):
    _set_query_params(run="")
    st.session_state.active_job = {"running": False}
    _active = None
    _run_id = None

# Reconnect banners only when we intentionally have a job (running, or ?run=).
if _active and (
    _active.get("running")
    or _run_id
) and (
    _active.get("running")
    or _active.get("result")
    or _active.get("has_result")
    or _active.get("status") in ("ok", "interrupted", "error", "cancelled")
):
    if not st.session_state.get("_reconnected_job_notice"):
        st.session_state["_reconnected_job_notice"] = True
        if _active.get("running"):
            st.info(
                "Reconnected to your **still-running** landscape. "
                "The browser refreshed, but the pipeline kept going on the server."
            )
        elif _active.get("status") == "interrupted":
            st.warning(
                "Your last run looks **interrupted** (no live progress for a while). "
                "Check **Cloud storage files** — it may still have finished. "
                "Do not start a duplicate unless you’re sure."
            )
        elif _active.get("result") or _active.get("has_result") or _active.get("status") == "ok":
            st.success(
                "Reconnected — your landscape **finished** while the live view was disconnected. "
                "Open **Cloud storage files** / Search history if the preview isn’t below."
            )
        elif _active.get("error") or _active.get("status") == "error":
            st.error("Reconnected to your last run — it ended with an error. See details below.")

JOB_RUNNER = JobRunner()

DEFAULT_PROFILE = "quality"
# Focused ≈ 40–50 companies (what most users need). Quality profile stays the same.
DEFAULT_CAP = "focused"
_CAP_CHOICES = ("focused", "standard", "broad")
_WIZARD_STEPS = ["Market & Geography", "Market Structure", "Review & Run"]
GEO_HINT = "global · United States · Europe · North America · Latin America · APAC · MENA · India · Germany"


def _cap_option_label(key: str) -> str:
    from vendor_intel.pipeline.cap_profiles import CAP_TIERS

    t = CAP_TIERS.get(key) or {}
    labels = {
        "focused": "Focused — ~40–50 companies (faster)",
        "standard": "Standard — ~50–90 companies",
        "broad": "Broad — ~90–160 companies (deeper / slower)",
    }
    return labels.get(key) or f"{t.get('label', key)} — {t.get('approx', '')}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def format_hint(text: str) -> None:
    st.markdown(
        f'<div class="format-hint"><strong>Recommended format:</strong> {text}</div>',
        unsafe_allow_html=True,
    )


def render_hero(title: str, subtitle: str) -> None:
    st.markdown(
        f'<div class="hero"><h1>{title}</h1><p>{subtitle}</p></div>',
        unsafe_allow_html=True,
    )


def metric_card(label: str, value: str) -> None:
    st.markdown(
        f'<div class="metric-card"><div class="label">{label}</div>'
        f'<div class="value">{value}</div></div>',
        unsafe_allow_html=True,
    )


def geography_input(label: str = "Geography", *, key: str | None = None) -> str:
    if key and key not in st.session_state:
        st.session_state[key] = "global"
    kwargs: dict = {
        "label": label,
        "placeholder": "e.g. Global, United States, Europe",
    }
    if key:
        kwargs["key"] = key
    raw = st.text_input(**kwargs)
    format_hint(
        f'Country or region name, or type <code>global</code> for worldwide. Examples: {GEO_HINT}'
    )
    return (raw or "").strip() or "global"


def _parse_sectioned_csv(path: Path) -> tuple[list[tuple[str, list[dict]]], list[str]]:
    import csv

    rows = list(csv.reader(path.open(encoding="utf-8")))
    if not rows:
        return [], []
    header = rows[0]
    sections: list[tuple[str, list[dict]]] = []
    current: list[dict] | None = None
    for r in rows[1:]:
        if not r or not any(str(c).strip() for c in r):
            continue
        first = str(r[0]).strip()
        if first.startswith("==="):
            name = first.strip("= ").rsplit(" (", 1)[0].strip()
            current = []
            sections.append((name, current))
            continue
        if current is None:
            current = []
            sections.append(("Companies", current))
        current.append(dict(zip(header, r)))
    return sections, header


def _gcs_urls_for(base: Path) -> dict[str, str]:
    """Durable download links, if this run was uploaded to Cloud Storage.

    Always tries a fresh signed URL (sidecar may be missing/stale on Cloud Run).
    """
    urls: dict[str, str] = {}
    sidecar = base.with_suffix(".gcs_urls.json")
    if sidecar.exists():
        try:
            import json

            raw = json.loads(sidecar.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                urls = {k: str(v) for k, v in raw.items() if v}
        except Exception:
            urls = {}
    try:
        from vendor_intel.storage.gcs_export import gcs_enabled, signed_urls_for_slug

        if gcs_enabled():
            fresh = signed_urls_for_slug(base.stem)
            # Fresh signed URLs win (sidecar links expire).
            for k, v in fresh.items():
                if v:
                    urls[k] = v
    except Exception:
        pass
    return urls


def _inline_file_download(path: Path, *, label: str, mime: str) -> bool:
    """Browser download via data-URI — avoids Streamlit /media (broken on Cloud Run)."""
    if not path.exists() or path.stat().st_size <= 0:
        return False
    # Keep page HTML reasonable (our Excel/Word are typically < 200 KB).
    if path.stat().st_size > 12_000_000:
        return False
    import base64
    import html as html_lib

    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    name = html_lib.escape(path.name, quote=True)
    text = html_lib.escape(label)
    st.markdown(
        f'<a download="{name}" href="data:{mime};base64,{b64}" '
        f'style="display:block;width:100%;box-sizing:border-box;text-align:center;'
        f'padding:0.55rem 1rem;margin:0.15rem 0;background:#ff4b4b;color:#fff;'
        f'border-radius:0.5rem;text-decoration:none;font-weight:600;">{text}</a>',
        unsafe_allow_html=True,
    )
    return True


def _download_exports(base: Path, *, key_prefix: str = "dl") -> None:
    """Offer Excel/Word downloads for finished runs (history + live results).

    Priority:
    1) GCS signed URL (opens real .xlsx/.docx from the bucket)
    2) Local file via data-URI (works after materialize / same-instance run)
    Never use st.download_button — it serves /media/<hash>.txt and fails on Cloud Run
    with "File wasn't available on site".
    """
    _ = key_prefix
    xlsx = base.with_suffix(".xlsx")
    docx = base.with_suffix(".docx")
    csv_path = base.with_suffix(".csv") if base.suffix.lower() != ".csv" else base
    gcs_urls = _gcs_urls_for(base)

    d1, d2 = st.columns(2)
    with d1:
        if gcs_urls.get("xlsx"):
            st.link_button("⬇ Download Excel", gcs_urls["xlsx"], width="stretch")
        elif _inline_file_download(
            xlsx,
            label="⬇ Download Excel",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ):
            pass
        elif gcs_urls.get("csv"):
            st.link_button("⬇ Download Excel (CSV)", gcs_urls["csv"], width="stretch")
        elif _inline_file_download(csv_path, label="⬇ Download Excel (CSV)", mime="text/csv"):
            pass
        else:
            st.caption("Excel file not ready yet.")
    with d2:
        if gcs_urls.get("docx"):
            st.link_button("⬇ Download Word", gcs_urls["docx"], width="stretch")
        elif _inline_file_download(
            docx,
            label="⬇ Download Word",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ):
            pass
        else:
            st.caption("Word file not ready yet.")


def _render_presentation(path: Path, *, key_prefix: str = "pres") -> None:
    sections, _ = _parse_sectioned_csv(path)
    if not sections:
        st.error("Could not read this result file.")
        return

    company_sections = [(n, rows) for n, rows in sections if "not verified" not in n.lower()]
    total = sum(len(rows) for _, rows in company_sections)
    market = (
        (company_sections[0][1][0].get("Industry") if company_sections and company_sections[0][1] else "")
        or path.stem.replace("_", " ").title()
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        metric_card("Market", market)
    with c2:
        metric_card("Companies", str(total))
    with c3:
        metric_card("Segments", str(len(company_sections)))

    _download_exports(path, key_prefix=key_prefix)

    search = st.text_input(
        "Search company",
        "",
        placeholder="Filter by company name…",
        key=f"{key_prefix}_search",
    )
    format_hint("Optional — type part of a company or brand name to filter the tables below.")

    PRES_COLS = ["Company", "Brand", "Functionality", "Summary", "Website"]

    def _section_df(rows: list[dict]) -> pd.DataFrame:
        df = pd.DataFrame(rows)
        if search and not df.empty:
            mask = pd.Series(False, index=df.index)
            for col in ("Company", "Brand", "Functionality", "Summary"):
                if col in df.columns:
                    mask |= df[col].astype(str).str.contains(search, case=False, na=False)
            df = df[mask]
        return df

    for name, rows in sections:
        df = _section_df(rows)
        if df.empty:
            continue
        is_nv = "not verified" in name.lower()
        st.markdown(
            f'<div class="section-head">{name} <span class="count">({len(df)})</span></div>',
            unsafe_allow_html=True,
        )
        if is_nv:
            cols = [c for c in ("Company", "Summary", "Website") if c in df.columns]
            show = df[cols].rename(columns={"Summary": "Why it could not be confirmed"})
        else:
            cols = [c for c in PRES_COLS if c in df.columns]
            show = df[cols] if cols else df
        st.dataframe(
            show,
            width="stretch",
            hide_index=True,
            column_config={
                "Website": st.column_config.LinkColumn(
                    "Website", display_text=r"https?://(?:www\.)?([^/]+)"
                )
            },
        )


def _notice_time_optimization() -> None:
    st.markdown(
        '<div class="notice-banner">'
        "<strong>Time optimization is in progress.</strong> "
        "We’re actively working on making landscape runs faster. "
        "A full market can still take a while today — you can stop a run anytime with "
        "<strong>Stop run</strong>."
        "</div>",
        unsafe_allow_html=True,
    )


# Typical broad run length used only to pace the bar (not a hard cutoff).
_EXPECTED_RUN_SECONDS = 28 * 60  # ~28 minutes


def _pipeline_phase(log: str) -> int:
    """Detect completed/started phase from official pipeline markers only (no false jumps)."""
    low = (log or "").lower()
    phase = 0
    # Match the exact stage lines printed by orchestrator — avoid words like
    # "discovery focused" during Phase 1 that used to jump the bar past 40%.
    if "[pipeline] phase 1" in low or "=== pipeline start ===" in low:
        phase = max(phase, 1)
    if "[pipeline] phase 2" in low:
        phase = max(phase, 2)
    if "[pipeline] phase 3" in low:
        phase = max(phase, 3)
    if "[pipeline] phase 4" in low or "[pipeline] classif" in low:
        phase = max(phase, 4)
    if "[pipeline] csv saved" in low or "[pipeline] xlsx saved" in low or "[pipeline] docx saved" in low:
        phase = max(phase, 5)
    if "[pipeline] total time" in low or "\ndone:" in low:
        phase = max(phase, 5)
    return phase


def _progress_pct(log: str, elapsed: int) -> float:
    """
    Steady progress for a long run:
    - Mostly driven by elapsed / expected duration (smooth, no early leap)
    - Phase markers only nudge within band, never skip to 50%+ in seconds
    """
    # Pure time curve: ~3% after 1 min, ~50% at ~14 min, ~90% near expected end
    time_pct = 1.0 - (2.71828 ** (-elapsed / (_EXPECTED_RUN_SECONDS * 0.85)))
    time_pct = max(0.02, min(time_pct, 0.92))

    phase = _pipeline_phase(log)
    # Soft floors once a real phase starts (small — keeps bar honest early)
    floors = {0: 0.02, 1: 0.04, 2: 0.12, 3: 0.45, 4: 0.68, 5: 0.90}
    # Hard ceilings until later phases — Phase 1/2 can't show as "halfway done"
    ceilings = {0: 0.06, 1: 0.10, 2: 0.48, 3: 0.70, 4: 0.88, 5: 0.96}

    floor = floors.get(phase, 0.02)
    ceiling = ceilings.get(phase, 0.96)
    pct = max(floor, min(time_pct, ceiling))
    return min(pct, 0.96)


def _phase_label(log: str) -> str:
    return {
        0: "Starting…",
        1: "Planning the market…",
        2: "Finding companies…",
        3: "Enriching profiles…",
        4: "Classifying companies…",
        5: "Saving Excel & Word…",
    }.get(_pipeline_phase(log), "Working…")


@st.fragment(run_every=2)
def _live_job_status() -> None:
    # Re-fetch from the registry each tick (not st.session_state) — the
    # background worker thread mutates the registry's dict directly, so this
    # is what actually picks up live log/progress updates as they happen.
    job = get_job(st.query_params.get("run")) or st.session_state.get("active_job") or {}
    if not (
        job.get("running")
        or job.get("result")
        or job.get("error")
        or job.get("cancelled")
        or job.get("status") == "interrupted"
    ):
        return

    # If stop was pressed but the worker is stuck in network I/O, finalize UI after a short wait
    # so the user is not stuck on "Stopping…".
    if (
        job.get("running")
        and job.get("cancel_requested")
        and job.get("cancel_requested_at")
    ):
        waited = time.time() - float(job["cancel_requested_at"])
        if waited >= 8:
            JOB_RUNNER.force_finish_cancelled(job)
            st.rerun()

    st.markdown("---")
    if job.get("running"):
        st.markdown("### Building your landscape")
        elapsed = int(time.time() - job.get("started_at", time.time()))
        log = job.get("log") or ""
        pct = _progress_pct(log, elapsed)
        label = _phase_label(log)
        left_m = max(0, (_EXPECTED_RUN_SECONDS - elapsed) // 60)
        st.progress(
            pct,
            text=f"{label}  ·  {elapsed // 60}m {elapsed % 60}s elapsed"
            + (f"  ·  ~{left_m}m typically remaining" if left_m > 0 and pct < 0.9 else ""),
        )
        st.caption(f"About {int(pct * 100)}% complete (estimate — time optimization in progress)")
        st.markdown(
            '<div class="notice-banner">'
            "<strong>Keep this browser tab open</strong> while the landscape builds "
            "(often 20–55+ minutes). If the page auto-refreshes, do <em>not</em> start a new run — "
            "the pipeline usually keeps going on the server and this page will reconnect. "
            "Finished files always land in <em>Cloud storage files</em> and "
            "<em>Search history</em> below even if the live view drops."
            "</div>",
            unsafe_allow_html=True,
        )
        if job.get("cancel_requested"):
            st.warning("Stopping the run…")
        elif st.button("⏹ Stop run", type="secondary", key="stop_pipeline_run", width="stretch"):
            JOB_RUNNER.request_stop(job)
            st.rerun()
    elif job.get("cancelled"):
        st.markdown("### Results")
        st.info("Run stopped. You can start a new market whenever you’re ready.")
    elif job.get("status") == "interrupted":
        st.markdown("### Results")
        st.warning(
            str(job.get("error") or "This run looks interrupted.")
            + " Check Cloud storage files below before starting again."
        )
    elif job.get("error"):
        st.markdown("### Results")
        st.error(
            "Something went wrong while building this landscape. "
            "Please try again, or contact your admin if it keeps failing."
        )
        st.caption("Technical detail (for support): " + str(job.get("error") or "")[:400])
    elif job.get("result"):
        st.markdown("### Results")
        result = job["result"]
        companies = len(result.get("relevant_companies") or [])
        c1, c2 = st.columns(2)
        with c1:
            metric_card("Companies in landscape", str(companies))
        with c2:
            metric_card("Classified", str(len(result.get("all_classified") or [])))

        csv_path = result.get("_csv_path") or ""
        if csv_path and Path(csv_path).exists():
            st.success("Your landscape is ready — download Excel + Word below.")
            _render_presentation(Path(csv_path), key_prefix="live_pres")
        else:
            st.warning("Run finished but no result file was returned.")
    elif job.get("has_result") or job.get("status") == "ok":
        st.markdown("### Results")
        st.success(
            "This run finished. Open **Cloud storage files** or **Search history** below "
            "to download Excel / Word"
            + (f" (slug: `{job.get('slug')}`)." if job.get("slug") else ".")
        )

    if not job.get("running") and (job.get("result") or job.get("error") or job.get("cancelled")):
        if st.button("Clear status & start another market", key="clear_job_status"):
            st.session_state.active_job = {
                "running": False,
                "cancelled": False,
                "cancel_requested": False,
            }
            st.session_state.wiz_step = 1
            st.session_state.wiz = {
                "market": "",
                "geography": "global",
                "profile": DEFAULT_PROFILE,
                "cap": DEFAULT_CAP,
            }
            for k in (
                "_wiz_spec",
                "_wiz_spec_for",
                "wiz_brief_text",
                "wiz_brief_edit_box",
                "wiz_sections",
                "wiz_brief_editing",
            ):
                st.session_state.pop(k, None)
            for i in range(16):
                st.session_state.pop(f"wiz_secname_{i}", None)
                st.session_state.pop(f"wiz_seccontent_{i}", None)
            _set_query_params(run="")
            st.rerun()


# ---------------------------------------------------------------------------
# Wizard
# ---------------------------------------------------------------------------
def _wizard_progress(step: int) -> None:
    pills = []
    for i, lbl in enumerate(_WIZARD_STEPS, 1):
        icon = "🔵" if i == step else ("✅" if i < step else "⚪")
        label = f"**Step {i} · {lbl}**" if i == step else f"Step {i} · {lbl}"
        pills.append(f"{icon} {label}")
    st.markdown(" &nbsp;&nbsp; ".join(pills))
    st.divider()


def _wiz_step1_market_geo() -> None:
    st.markdown("### Step 1 — Market & Geography")
    wiz = st.session_state.wiz
    col1, col2 = st.columns([2, 1])
    with col1:
        market = st.text_input(
            "Market",
            value=wiz.get("market", ""),
            placeholder='e.g. "Remote Elderly Health Monitoring Market"',
            key="wiz_market_input",
        )
        format_hint(
            'Plain market title — e.g. <code>Satcom Market</code>, '
            '<code>Waste Oil Market</code>, <code>Bio-based Ethylene Market</code>'
        )
    with col2:
        geo = geography_input("Geography", key="wiz_geo_input")

    if st.button("Next →", type="primary", width="stretch"):
        if not market.strip():
            st.error("Enter a market to continue.")
        else:
            wiz["market"] = market.strip()
            wiz["geography"] = geo
            wiz["profile"] = DEFAULT_PROFILE
            if str(wiz.get("cap") or "").strip().lower() not in _CAP_CHOICES:
                wiz["cap"] = DEFAULT_CAP
            st.session_state.wiz_step = 2
            st.rerun()


_BRIEF_PLACEHOLDER = (
    "FUNCTIONAL ENTITIES IN THE VALUE CHAIN:\n"
    "1. Upstream: … (Function / Core entities / Business model / Market sizing)\n"
    "2. Midstream: …\n"
    "3. Downstream: …\n\n"
    "WHICH ENTITIES TO INCLUDE IN MARKET SIZING: …"
)


def _wiz_back_to_step1() -> None:
    if st.button("← Back", key="wiz_back_1", width="stretch"):
        st.session_state.wiz_step = 1
        st.rerun()


def _wiz_continue_to_review(brief_text: str) -> None:
    st.session_state.wiz["brief"] = (brief_text or "").strip()
    st.session_state.wiz_step = 3
    st.rerun()


def _wiz_step2_brief() -> None:
    wiz = st.session_state.wiz
    st.markdown("### Step 2 — Market structure")
    st.caption(f"Market: **{wiz.get('market', '')}**  ·  {wiz.get('geography', 'global')}")
    st.markdown(
        "What are the different entities in the value chain based on functionality, and which "
        "should be considered for the **market-sizing** activity?"
    )
    st.session_state.setdefault("wiz_brief_text", wiz.get("brief", ""))
    st.session_state.setdefault("wiz_brief_editing", False)

    mode = st.radio(
        "How do you want to provide the market structure?",
        [
            "Write it myself (default)",
            "Generate with AI, then review",
            "Describe it in your own words",
        ],
        key="wiz_brief_mode",
    )
    format_hint(
        "Pick one path: fill section cards yourself, let AI draft a full brief to review, "
        "or paste a free-form overview."
    )

    if mode.startswith("Write"):
        st.session_state.setdefault("wiz_sections", None)
        if st.session_state["wiz_sections"] is None:
            with st.spinner("Drafting the value-chain sections for this market…"):
                from vendor_intel.funnel.brief_interpreter import generate_market_sections

                secs = generate_market_sections(
                    wiz.get("market", ""),
                    wiz.get("geography", "global"),
                    load_settings(DEFAULT_PROFILE),
                )
            st.session_state["wiz_sections"] = secs or [""]
        secs = st.session_state["wiz_sections"]

        st.caption("Edit section names and describe what to profile under each.")
        names: list[str] = []
        contents: list[str] = []
        for i in range(len(secs)):
            nm = st.text_input(f"Section {i + 1} name", value=secs[i], key=f"wiz_secname_{i}")
            format_hint(
                "Value-chain segment name — e.g. <code>Device-Agnostic Platform Providers</code>"
            )
            cont = st.text_area(
                f"What to profile under section {i + 1}",
                key=f"wiz_seccontent_{i}",
                height=110,
                label_visibility="collapsed",
                placeholder=(
                    "Function · core entities (example companies) · business model · "
                    "market-sizing note (include / exclude)…"
                ),
            )
            format_hint(
                "Short bullets: what this segment does, example companies, and "
                "<code>INCLUDE</code> / <code>EXCLUDE</code> for sizing."
            )
            names.append(nm)
            contents.append(cont)

        if st.button("➕ Add a section", key="wiz_sec_add"):
            st.session_state["wiz_sections"] = list(secs) + [""]
            st.rerun()
        if st.button("↻ Re-draft sections with AI", key="wiz_sec_redraft"):
            st.session_state["wiz_sections"] = None
            for i in range(len(secs)):
                st.session_state.pop(f"wiz_secname_{i}", None)
                st.session_state.pop(f"wiz_seccontent_{i}", None)
            st.rerun()

        c1, c2 = st.columns(2)
        with c1:
            _wiz_back_to_step1()
        if c2.button("Next →", type="primary", key="wiz2_next_write", width="stretch"):
            clean = [(n.strip(), c.strip()) for n, c in zip(names, contents) if n.strip()]
            if not clean:
                st.error("Add at least one section name.")
            else:
                lines: list[str] = []
                for n, c in clean:
                    lines.append(n)
                    if c:
                        lines.append(c)
                    lines.append("")
                wiz["brief"] = "\n".join(lines).strip()
                wiz["sections"] = [n for n, _ in clean]
                st.session_state.wiz_step = 3
                st.rerun()
        return

    if mode.startswith("Describe"):
        st.session_state.wiz.pop("sections", None)
        summary = st.text_area(
            "Market overview",
            height=320,
            key="wiz_brief_text",
            placeholder=(
                "e.g. This market covers … Participants range from … through … to …. "
                "For sizing, focus on … while … are counted separately."
            ),
        )
        format_hint(
            "1–3 short paragraphs covering scope, participant types, and sizing include/exclude rules."
        )
        c1, c2 = st.columns(2)
        with c1:
            _wiz_back_to_step1()
        if c2.button("Next →", type="primary", key="wiz2_next_desc", width="stretch"):
            if not (summary or "").strip():
                st.error("Write a short overview to continue.")
            else:
                _wiz_continue_to_review(summary)
        return

    st.session_state.wiz.pop("sections", None)

    if st.button("✨ Generate structure with AI", key="wiz_gen_brief"):
        with st.spinner("Drafting the value-chain structure with AI…"):
            from vendor_intel.funnel.brief_interpreter import generate_market_brief

            txt = generate_market_brief(
                wiz.get("market", ""),
                wiz.get("geography", "global"),
                load_settings(DEFAULT_PROFILE),
            )
        if txt:
            st.session_state["wiz_brief_text"] = txt
            st.session_state["wiz_brief_editing"] = False
            st.rerun()
        else:
            st.warning("Could not generate a draft. Switch to 'Write it myself'.")

    draft = st.session_state.get("wiz_brief_text", "")
    if not draft:
        st.info("Click **✨ Generate structure with AI** to draft the value chain.")
        _wiz_back_to_step1()
        return

    if st.session_state["wiz_brief_editing"]:
        st.session_state.setdefault("wiz_brief_edit_box", draft)
        edited = st.text_area(
            "Market structure brief",
            height=380,
            key="wiz_brief_edit_box",
            placeholder=_BRIEF_PLACEHOLDER,
        )
        format_hint(
            "Numbered functional entities with Function / Core entities / Business model / "
            "Include-exclude sizing notes."
        )
        c1, c2 = st.columns(2)
        with c1:
            _wiz_back_to_step1()
        if c2.button("Save & continue →", type="primary", key="wiz2_save", width="stretch"):
            _wiz_continue_to_review(edited)
    else:
        st.markdown("**AI-generated market structure — review it:**")
        st.text_area(
            "AI draft (read-only)",
            value=draft,
            height=340,
            disabled=True,
            label_visibility="collapsed",
        )
        format_hint("Review the draft, then Edit or Use as-is.")
        c1, c2, c3 = st.columns(3)
        with c1:
            _wiz_back_to_step1()
        if c2.button("✏️ Edit it", key="wiz2_edit", width="stretch"):
            st.session_state["wiz_brief_editing"] = True
            st.session_state["wiz_brief_edit_box"] = draft
            st.rerun()
        if c3.button("✅ Use as-is → continue", type="primary", key="wiz2_useasis", width="stretch"):
            _wiz_continue_to_review(draft)


def _wiz_step3_review_run() -> None:
    wiz = st.session_state.wiz
    job = st.session_state.active_job
    st.markdown("### Step 3 — Review & run")

    c1, c2 = st.columns(2)
    c1.metric("Market", wiz.get("market", "—"))
    c2.metric("Geography", wiz.get("geography", "global"))
    st.caption(
        "Results save as Excel + Word. Coverage only changes how many companies we search for — "
        "quality settings stay the same."
    )

    # Coverage = company count only (cap). Profile remains quality.
    current_cap = str(wiz.get("cap") or DEFAULT_CAP).strip().lower()
    if current_cap not in _CAP_CHOICES:
        current_cap = DEFAULT_CAP
    cap_labels = [_cap_option_label(k) for k in _CAP_CHOICES]
    chosen_label = st.radio(
        "How many companies?",
        options=cap_labels,
        index=_CAP_CHOICES.index(current_cap),
        key="wiz_cap_radio",
        help="Fewer companies = faster run. Excel/Word quality rules are unchanged.",
    )
    wiz["cap"] = _CAP_CHOICES[cap_labels.index(chosen_label)]
    wiz["profile"] = DEFAULT_PROFILE

    explicit = [s for s in (wiz.get("sections") or []) if str(s).strip()]
    brief = (wiz.get("brief") or "").strip()
    spec: dict | None = None
    if explicit:
        spec = {
            "market": wiz.get("market", ""),
            "geography": wiz.get("geography", "global"),
            "sections": explicit,
            "exclude": [],
            "definition": "",
        }
        st.markdown("**Sections to profile:**")
        for s in explicit:
            st.markdown(f"- {s}")
    elif brief:
        if st.session_state.get("_wiz_spec_for") != brief:
            with st.spinner("Interpreting your market structure…"):
                from vendor_intel.funnel.brief_interpreter import interpret_brief

                st.session_state["_wiz_spec"] = interpret_brief(
                    brief, load_settings(DEFAULT_PROFILE)
                )
                st.session_state["_wiz_spec_for"] = brief
        spec = st.session_state.get("_wiz_spec") or {}
        secs = spec.get("sections") or []
        st.markdown("**Sections to profile:**")
        if secs:
            for s in secs:
                st.markdown(f"- {s}")
        else:
            st.caption("No explicit sections detected — profiling the market generally.")
        defn = str(spec.get("definition") or "").strip()
        if defn:
            st.info(defn)
    else:
        st.caption("No structure brief — running as a plain market query.")

    st.divider()
    b1, b2 = st.columns(2)
    if b1.button("← Back", key="wiz3_back", width="stretch"):
        # Allow leaving Step 3 even when ?run= / finished job would otherwise force it.
        st.session_state["_wiz_leave_step3"] = True
        st.session_state.wiz_step = 2
        st.rerun()
    if b2.button("Start run", type="primary", key="wiz3_run", width="stretch"):
        st.session_state.pop("_wiz_leave_step3", None)
        if not wiz.get("market"):
            st.error("Market is missing — go back to Step 1.")
        elif job.get("running"):
            st.warning(
                "This landscape is already running — scroll up for progress. "
                "Do not click Start again."
            )
        else:
            busy_msg = pipeline_busy_reason(_auth_user["email"])
            if busy_msg:
                st.warning(busy_msg)
            else:
                if spec:
                    scope = {
                        "market": wiz.get("market") or spec.get("market", ""),
                        "geography": wiz.get("geography", "global"),
                        "sections": spec.get("sections") or [],
                        "exclude": spec.get("exclude") or [],
                        "definition": spec.get("definition", "") or (brief if explicit else ""),
                    }
                    run_cap = str(wiz.get("cap") or DEFAULT_CAP).strip().lower()
                    if run_cap not in _CAP_CHOICES:
                        run_cap = DEFAULT_CAP
                    new_run_id = JOB_RUNNER.start(
                        owner_email=_auth_user["email"],
                        job_type="pipeline",
                        query="",
                        country=scope["geography"],
                        profile=DEFAULT_PROFILE,
                        cap=run_cap,
                        scope=scope,
                    )
                else:
                    run_cap = str(wiz.get("cap") or DEFAULT_CAP).strip().lower()
                    if run_cap not in _CAP_CHOICES:
                        run_cap = DEFAULT_CAP
                    new_run_id = JOB_RUNNER.start(
                        owner_email=_auth_user["email"],
                        job_type="pipeline",
                        query=wiz.get("market", ""),
                        country=wiz.get("geography", "global"),
                        profile=DEFAULT_PROFILE,
                        cap=run_cap,
                    )
                if new_run_id:
                    st.session_state["_reconnected_job_notice"] = False
                    _set_query_params(run=new_run_id)
                    st.success("Run started — building your landscape…")
                    st.rerun()
                else:
                    st.warning(
                        pipeline_busy_reason(_auth_user["email"])
                        or "Could not start right now. Wait a minute and try Start again."
                    )


def _past_results_panel() -> None:
    """Search history — reopen finished landscapes and re-download Excel/Word."""
    runs = list_owned_runs(_auth_user["email"])
    # Also surface any local CSVs owned by this user that might predate rich log rows
    csvs = list_result_csvs_for_owner(_auth_user["email"])
    if not runs and not csvs:
        with st.expander("Search history", expanded=False):
            st.caption(
                "No saved landscapes yet. After a successful run, it will appear here "
                "so you can reopen and download Excel / Word again."
            )
        return

    with st.expander("Search history — reopen past landscapes", expanded=False):
        format_hint(
            "Pick a previous market run to preview companies and download Excel / Word again."
        )
        labels: list[str] = []
        label_to_entry: dict[str, dict | Path] = {}

        for entry in runs:
            query = str(entry.get("query") or "Untitled").strip() or "Untitled"
            country = str(entry.get("country") or "global")
            n = entry.get("companies_exported")
            when = str(entry.get("ran_at") or "")[:16].replace("T", " ")
            n_txt = f"{n} companies" if n is not None else "done"
            label = f"{query} · {country} · {n_txt} · {when} UTC"
            # De-dupe labels if same second
            base_label = label
            i = 2
            while label in label_to_entry:
                label = f"{base_label} ({i})"
                i += 1
            labels.append(label)
            label_to_entry[label] = entry

        # Local-only CSVs not already covered by a log row
        known_stems = {
            run_slug_from_entry(e) for e in runs if isinstance(e, dict)
        }
        for p in csvs:
            if p.stem in known_stems:
                continue
            label = f"{p.stem.replace('_', ' ')} · local file"
            labels.append(label)
            label_to_entry[label] = p

        if not labels:
            st.caption("No reopenable results found yet.")
            return

        selected = st.selectbox(
            "Your previous searches",
            labels,
            key="past_result_pick",
        )
        chosen = label_to_entry.get(selected)
        if isinstance(chosen, Path):
            _render_presentation(chosen, key_prefix="past_pres")
            return
        if not isinstance(chosen, dict):
            return

        slug = run_slug_from_entry(chosen)
        out = output_dir()
        csv_local = out / f"{slug}.csv" if slug else None

        # Always sync missing Excel/Word/CSV from GCS onto this instance so
        # preview + downloads work after recycle / new revision.
        if slug:
            try:
                from vendor_intel.storage.gcs_export import gcs_enabled, materialize_run_files

                if gcs_enabled():
                    need = not (
                        csv_local
                        and csv_local.exists()
                        and (out / f"{slug}.xlsx").exists()
                        and (out / f"{slug}.docx").exists()
                    )
                    if need:
                        with st.spinner("Loading saved landscape from cloud storage…"):
                            csv_local = materialize_run_files(slug, out) or csv_local
            except Exception as exc:
                st.caption(f"Could not load from cloud storage: {exc}")

        if csv_local and Path(csv_local).exists():
            _render_presentation(Path(csv_local), key_prefix="past_pres")
            return

        st.warning(
            f"Could not open **{chosen.get('query') or slug}** — files missing locally and in cloud storage."
        )


def _cloud_storage_panel() -> None:
    """Always-on list of finished Excel/Word/CSV in the GCS bucket.

    Independent of live job UI / session_state — so after a page reload the user
    can still download every completed run without waiting for Search history.
    """
    try:
        from vendor_intel.storage.gcs_export import (
            gcs_enabled,
            list_gcs_run_entries,
            materialize_run_files,
            signed_urls_for_slug,
        )
    except Exception:
        return
    if not gcs_enabled():
        return

    with st.expander("Cloud storage files — all finished Excel / Word", expanded=False):
        st.caption(
            "Every completed landscape uploaded to cloud storage appears here. "
            "Use this if Search history or the live run view is empty after a page reload."
        )
        c1, c2 = st.columns([1, 3])
        with c1:
            refresh = st.button("Refresh list", key="gcs_files_refresh", width="stretch")
        if refresh:
            st.session_state.pop("_gcs_files_cache", None)

        entries = st.session_state.get("_gcs_files_cache")
        if entries is None:
            with st.spinner("Loading files from cloud storage…"):
                try:
                    entries = list_gcs_run_entries()
                except Exception as exc:
                    st.error(f"Could not list cloud storage: {exc}")
                    return
            st.session_state["_gcs_files_cache"] = entries

        if not entries:
            st.caption("No finished files in cloud storage yet.")
            return

        labels = []
        by_label: dict[str, dict] = {}
        for e in entries:
            slug = str(e.get("slug") or "")
            query = str(e.get("query") or slug).strip() or slug
            country = str(e.get("country") or "global")
            when = str(e.get("ran_at") or "")[:16].replace("T", " ")
            bits = []
            if e.get("xlsx_file"):
                bits.append("Excel")
            if e.get("docx_file"):
                bits.append("Word")
            if e.get("csv_file"):
                bits.append("CSV")
            label = f"{query} · {country} · {', '.join(bits) or 'files'} · {when} UTC"
            base = label
            i = 2
            while label in by_label:
                label = f"{base} ({i})"
                i += 1
            labels.append(label)
            by_label[label] = e

        picked = st.selectbox("Cloud files", labels, key="gcs_files_pick")
        entry = by_label.get(picked) or {}
        slug = str(entry.get("slug") or "")
        if not slug:
            return

        urls = signed_urls_for_slug(slug)
        # Ensure local copies exist for inline download fallback + optional preview
        out = output_dir()
        xlsx = out / f"{slug}.xlsx"
        docx = out / f"{slug}.docx"
        csv_p = out / f"{slug}.csv"
        if not (xlsx.exists() and docx.exists() and csv_p.exists()):
            try:
                materialize_run_files(slug, out)
            except Exception:
                pass

        d1, d2, d3 = st.columns(3)
        with d1:
            if urls.get("xlsx"):
                st.link_button("⬇ Excel", urls["xlsx"], width="stretch")
            elif not _inline_file_download(
                xlsx,
                label="⬇ Excel",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ):
                st.caption("Excel missing")
        with d2:
            if urls.get("docx"):
                st.link_button("⬇ Word", urls["docx"], width="stretch")
            elif not _inline_file_download(
                docx,
                label="⬇ Word",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ):
                st.caption("Word missing")
        with d3:
            if urls.get("csv"):
                st.link_button("⬇ CSV", urls["csv"], width="stretch")
            elif not _inline_file_download(csv_p, label="⬇ CSV", mime="text/csv"):
                st.caption("CSV missing")

        if st.button("Open preview tables", key=f"gcs_preview_{slug}", width="stretch"):
            st.session_state["gcs_preview_slug"] = slug

        preview_slug = st.session_state.get("gcs_preview_slug")
        if preview_slug == slug and csv_p.exists():
            _render_presentation(csv_p, key_prefix=f"gcs_pres_{slug[:24]}")


# ---------------------------------------------------------------------------
# Single page (authenticated)
# ---------------------------------------------------------------------------
# CSS already injected above the auth gate.

render_hero(
    "Vendor Intelligence",
    "Enter a market, define its structure, and get a presentation-ready company landscape "
    "(Excel + Word).",
)
_notice_time_optimization()

for w in env_warnings():
    st.warning(w)

# If the browser cached a broken JS chunk (Metric.*.js / Rate exceeded), Streamlit
# buttons stop working. Surface a one-line recovery tip at the top.
st.caption(
    "If Start run does nothing or you see a red TypeError, hard-refresh with Ctrl+Shift+R "
    "(or open the link in a new Incognito window), then try again."
)

st.session_state.setdefault("wiz_step", 1)
st.session_state.setdefault(
    "wiz",
    {
        "market": "",
        "geography": "global",
        "profile": DEFAULT_PROFILE,
        "cap": DEFAULT_CAP,
    },
)
if not st.session_state.get("_wiz_v2"):
    old = int(st.session_state.get("wiz_step") or 1)
    if old == 3:
        st.session_state.wiz_step = 2
    elif old >= 4:
        st.session_state.wiz_step = 3
    st.session_state["_wiz_v2"] = True

step = max(1, min(3, int(st.session_state.wiz_step)))
# Only jump to Step 3 for a **live** run, or when the URL has ?run= (explicit).
# Old cancelled/finished jobs must not trap a fresh login on empty Step 3.
# Skip the force after ← Back (progress can still show below).
_job = st.session_state.active_job or {}
_force_step3 = bool(_job.get("running") or st.query_params.get("run"))
if _force_step3 and not st.session_state.get("_wiz_leave_step3"):
    step = 3
st.session_state.wiz_step = step
st.session_state.wiz["profile"] = DEFAULT_PROFILE
# Keep user's coverage choice; only default if missing/invalid.
_wiz_cap = str(st.session_state.wiz.get("cap") or "").strip().lower()
if _wiz_cap not in _CAP_CHOICES:
    st.session_state.wiz["cap"] = DEFAULT_CAP

_wizard_progress(step)
if step == 1:
    _wiz_step1_market_geo()
elif step == 2:
    _wiz_step2_brief()
else:
    _wiz_step3_review_run()

_live_job_status()
_cloud_storage_panel()
_past_results_panel()

st.caption(
    f"Outputs save to cloud storage + `{output_dir().name}/` · Time optimization in progress"
)
