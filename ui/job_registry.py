"""Module-level job registry — survives a page reload, unlike st.session_state.

st.session_state is per-browser-session in Streamlit's own bookkeeping; a hard
reload (or opening the link in a new tab) gets a fresh session_state with no
memory of a job that's still running in a background thread. Jobs here live
in a plain process-wide dict instead, keyed by a run_id that travels in the
URL (?run=<id>) — any reload that carries the same run_id finds the same job.

Not persisted across container restarts (in-memory only) — same durability
tier as the old session_state approach, just no longer tied to one browser tab.
"""
from __future__ import annotations

import time
import uuid
from typing import Any

_jobs: dict[str, dict[str, Any]] = {}
_MAX_JOBS = 200  # small in-memory cap so a busy server doesn't leak forever


def new_run_id() -> str:
    return uuid.uuid4().hex[:12]


def create_job(run_id: str, *, owner_email: str, job_type: str, query: str, country: str,
               profile: str, cap: str | None) -> dict[str, Any]:
    job: dict[str, Any] = {
        "run_id": run_id,
        "owner_email": (owner_email or "").strip().lower(),
        "running": True,
        "job_type": job_type,
        "query": query,
        "country": country,
        "profile": profile,
        "cap": cap,
        "log": "",
        "result": None,
        "error": None,
        "cancelled": False,
        "cancel_requested": False,
        "started_at": time.time(),
    }
    _jobs[run_id] = job
    if len(_jobs) > _MAX_JOBS:
        oldest = min(_jobs.values(), key=lambda j: j["started_at"])
        _jobs.pop(oldest["run_id"], None)
    return job


def get_job(run_id: str | None) -> dict[str, Any] | None:
    if not run_id:
        return None
    return _jobs.get(run_id)


def upsert_job(job: dict[str, Any]) -> dict[str, Any]:
    """Insert or replace a job in the process registry (e.g. hydrated from GCS)."""
    run_id = str(job.get("run_id") or "").strip()
    if not run_id:
        raise ValueError("upsert_job requires run_id")
    job = dict(job)
    job["run_id"] = run_id
    _jobs[run_id] = job
    if len(_jobs) > _MAX_JOBS:
        oldest = min(_jobs.values(), key=lambda j: float(j.get("started_at") or 0))
        _jobs.pop(str(oldest.get("run_id")), None)
    return job


def jobs_for_owner(owner_email: str) -> list[dict[str, Any]]:
    email = (owner_email or "").strip().lower()
    if not email:
        return []
    return sorted(
        (
            j
            for j in _jobs.values()
            if str(j.get("owner_email") or "").strip().lower() == email
        ),
        key=lambda j: float(j.get("started_at") or 0),
        reverse=True,
    )


def running_jobs() -> list[dict[str, Any]]:
    return [j for j in _jobs.values() if j.get("running")]


def owner_has_running_job(owner_email: str) -> bool:
    email = (owner_email or "").strip().lower()
    if not email:
        return False
    _reconcile_owner_with_gcs(email)
    return any(
        j.get("running")
        and not j.get("cancelled")
        and not j.get("cancel_requested")
        and str(j.get("owner_email") or "").strip().lower() == email
        for j in _jobs.values()
    )


def count_running_jobs() -> int:
    return sum(1 for j in _jobs.values() if j.get("running") and not j.get("cancelled"))


def _reconcile_owner_with_gcs(owner_email: str) -> None:
    """Clear local 'running' if GCS says this user's job was stopped/finished.

    Stops false 'You already have a run' after Stop or deploy when memory is stale.
    """
    email = (owner_email or "").strip().lower()
    if not email:
        return
    try:
        from vendor_intel.storage.gcs_export import pull_job_status
    except Exception:
        return
    now = time.time()
    for job in list(_jobs.values()):
        if str(job.get("owner_email") or "").strip().lower() != email:
            continue
        if not job.get("running"):
            continue
        run_id = str(job.get("run_id") or "")
        if not run_id:
            continue
        try:
            remote = pull_job_status(run_id)
        except Exception:
            remote = None
        if remote is not None:
            if remote.get("cancelled") or remote.get("cancel_requested") or not remote.get("running"):
                job["running"] = False
                job["cancelled"] = bool(remote.get("cancelled") or remote.get("cancel_requested"))
                continue
        # Local zombie with no GCS updates for > 90 minutes
        started = float(job.get("started_at") or 0)
        if started and (now - started) > 90 * 60:
            job["running"] = False
            job["cancelled"] = True
            job["error"] = "Stale run cleared (no longer active)."
