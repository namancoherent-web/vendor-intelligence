"""Vendor Intelligence API (BFF for Next.js frontend).

Serves:
  - /api/*  JSON API (auth, jobs, runs)
  - /       static Next.js export (when FRONTEND_DIST is set)
  - /health and /_stcore/health for Cloud Run probes
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from vendor_intel.placeholders.load_keys import apply_env_overrides

apply_env_overrides()

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field

from vendor_intel.auth.db import init_db
from vendor_intel.auth.service import AuthError, login_without_otp, logout, validate_session
from ui.job_registry import get_job, jobs_for_owner
from ui.services import (
    JobRunner,
    list_owned_runs,
    pipeline_busy_reason,
    pipeline_is_busy,
)

AUTH_COOKIE = "vi_auth"
SESSION_HOURS = int(os.getenv("AUTH_SESSION_HOURS") or "24")

app = FastAPI(title="Vendor Intelligence API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ALLOW_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

JOB_RUNNER = JobRunner()

# Stable per-process id so the UI can tell whether a reload landed on a new box.
_INSTANCE_ID = (
    f"{os.environ.get('K_REVISION', 'local')}-{os.getpid()}-"
    f"{os.environ.get('K_CONFIGURATION', 'cfg')[:12]}"
)


@app.on_event("startup")
def _startup() -> None:
    init_db()


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def _token_from_request(request: Request) -> str | None:
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip() or None
    return request.cookies.get(AUTH_COOKIE)


def require_user(request: Request) -> dict[str, Any]:
    token = _token_from_request(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not signed in")
    try:
        user = validate_session(token, ip=_client_ip(request))
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=exc.message) from exc
    return {
        "token": token,
        "user_id": user.user_id,
        "email": user.email,
        "role": user.role,
        "expires_at": user.expires_at,
    }


def _set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=AUTH_COOKIE,
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=SESSION_HOURS * 3600,
        path="/",
    )


def _clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(key=AUTH_COOKIE, path="/")


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@app.get("/health")
@app.get("/_stcore/health")
def health() -> dict[str, Any]:
    from ui.services import _MAX_PIPELINES_PER_INSTANCE

    return {
        "status": "ok",
        "service": "vendor-intel-api",
        "instance_id": _INSTANCE_ID,
        "max_pipelines_per_instance": _MAX_PIPELINES_PER_INSTANCE,
    }


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
class LoginBody(BaseModel):
    email: EmailStr


@app.post("/api/auth/login")
def api_login(body: LoginBody, request: Request, response: Response) -> dict[str, Any]:
    try:
        info = login_without_otp(
            body.email,
            ip=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    _set_auth_cookie(response, info.token)
    return {
        "email": info.email,
        "role": info.role,
        "user_id": info.user_id,
        "expires_at": info.expires_at.isoformat(),
        "access_token": info.token,
    }


@app.post("/api/auth/logout")
def api_logout(request: Request, response: Response) -> dict[str, str]:
    token = _token_from_request(request)
    if token:
        try:
            logout(token)
        except Exception:
            pass
    _clear_auth_cookie(response)
    return {"status": "ok"}


@app.get("/api/auth/me")
def api_me(user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    return {
        "email": user["email"],
        "role": user["role"],
        "user_id": user["user_id"],
        "expires_at": user["expires_at"].isoformat()
        if hasattr(user["expires_at"], "isoformat")
        else str(user["expires_at"]),
    }


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------
class StartJobBody(BaseModel):
    market: str = Field(..., min_length=1)
    geography: str = "global"
    cap: str = "focused"
    brief: str = ""
    sections: list[str] = Field(default_factory=list)


def _phase_from_log(log: str) -> int:
    low = (log or "").lower()
    phase = 0
    if "[pipeline] phase 1" in low or "=== pipeline start ===" in low:
        phase = max(phase, 1)
    if "[pipeline] phase 2" in low:
        phase = max(phase, 2)
    if "[pipeline] phase 3" in low:
        phase = max(phase, 3)
    if "[pipeline] phase 4" in low or "[pipeline] classif" in low:
        phase = max(phase, 4)
    if "[pipeline] csv saved" in low or "[pipeline] xlsx saved" in low:
        phase = max(phase, 5)
    return phase


def _progress_pct(log: str, started_at: float, phase: int | None = None) -> float:
    elapsed = max(0.0, time.time() - float(started_at or time.time()))
    expected = 28 * 60
    time_pct = 1.0 - (2.71828 ** (-elapsed / (expected * 0.85)))
    time_pct = max(0.02, min(time_pct, 0.92))
    resolved = int(phase) if phase is not None else _phase_from_log(log)
    resolved = max(resolved, _phase_from_log(log))
    floors = {0: 0.02, 1: 0.04, 2: 0.12, 3: 0.45, 4: 0.68, 5: 0.90}
    ceilings = {0: 0.06, 1: 0.10, 2: 0.48, 3: 0.70, 4: 0.88, 5: 0.96}
    return min(0.96, max(floors.get(resolved, 0.02), min(time_pct, ceilings.get(resolved, 0.96))))


_PHASE_LABELS = {
    0: "Starting…",
    1: "Planning the market…",
    2: "Finding companies…",
    3: "Enriching profiles…",
    4: "Classifying companies…",
    5: "Saving Excel & Word…",
}


def _serialize_job(job: dict[str, Any]) -> dict[str, Any]:
    log = str(job.get("log") or job.get("log_tail") or "")
    started = float(job.get("started_at") or time.time())
    # Prefer stored phase (GCS) so short log tails on other instances don't reset UI.
    stored = int(job.get("phase") or 0)
    phase = max(stored, _phase_from_log(log))
    result = job.get("result") or {}
    slug = ""
    if isinstance(result, dict):
        csv_path = str(result.get("_csv_path") or "")
        if csv_path:
            slug = Path(csv_path).stem
    return {
        "run_id": job.get("run_id"),
        "owner_email": job.get("owner_email"),
        "query": job.get("query") or "",
        "country": job.get("country") or "global",
        "profile": job.get("profile") or "quality",
        "cap": job.get("cap") or "focused",
        "running": bool(job.get("running")),
        "cancelled": bool(job.get("cancelled")),
        "cancel_requested": bool(job.get("cancel_requested")),
        "cancel_requested_at": float(job["cancel_requested_at"])
        if job.get("cancel_requested_at")
        else None,
        "error": job.get("error"),
        "status": job.get("status")
        or (
            "running"
            if job.get("running")
            else ("cancelled" if job.get("cancelled") else ("error" if job.get("error") else ("ok" if job.get("result") else "idle")))
        ),
        "started_at": started,
        "elapsed_seconds": int(time.time() - started),
        "phase": phase,
        "phase_label": _PHASE_LABELS.get(phase, "Working…"),
        "progress_pct": round(_progress_pct(log, started, phase) * 100),
        "log_tail": log[-4000:],
        "has_result": bool(job.get("result") or job.get("has_result")),
        "slug": slug or job.get("slug") or "",
        "companies": len((result or {}).get("relevant_companies") or []) if isinstance(result, dict) else 0,
        "csv_path": (result or {}).get("_csv_path") if isinstance(result, dict) else None,
        "xlsx_path": (result or {}).get("_xlsx_path") if isinstance(result, dict) else None,
        "docx_path": (result or {}).get("_docx_path") if isinstance(result, dict) else None,
    }


@app.post("/api/jobs")
def api_start_job(body: StartJobBody, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    email = user["email"]
    reason = pipeline_busy_reason(email)
    if reason or pipeline_is_busy(email):
        raise HTTPException(status_code=409, detail=reason or "Cannot start right now")

    cap = (body.cap or "focused").strip().lower()
    if cap not in {"focused", "standard", "broad"}:
        cap = "focused"
    market = body.market.strip()
    geo = (body.geography or "global").strip() or "global"
    sections = [s.strip() for s in (body.sections or []) if str(s).strip()]
    brief = (body.brief or "").strip()

    scope = None
    query = market
    if sections or brief:
        scope = {
            "market": market,
            "geography": geo,
            "sections": sections,
            "exclude": [],
            "definition": brief,
        }
        query = ""

    run_id = JOB_RUNNER.start(
        owner_email=email,
        job_type="pipeline",
        query=query,
        country=geo,
        profile="quality",
        cap=cap,
        brief=brief,
        scope=scope,
    )
    if not run_id:
        raise HTTPException(
            status_code=409,
            detail=pipeline_busy_reason(email) or "Could not start run",
        )
    job = get_job(run_id) or {"run_id": run_id, "running": True, "started_at": time.time()}
    return _serialize_job(job)


@app.get("/api/capacity")
def api_capacity(user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    """Instance capacity for Step 1 banner (only when this server is full)."""
    from ui.job_registry import count_running_jobs

    _ = user
    running = count_running_jobs()
    from ui.services import _MAX_PIPELINES_PER_INSTANCE

    max_per_instance = int(_MAX_PIPELINES_PER_INSTANCE)
    instance_full = running >= max_per_instance
    reason = None
    if instance_full:
        reason = (
            "This server is at capacity right now (other landscapes are running). "
            "Wait a few minutes for a run to finish, then try again."
        )
    return {
        "instance_full": instance_full,
        "reason": reason,
        "running": running,
        "max_per_instance": max_per_instance,
        "instance_id": _INSTANCE_ID,
    }


@app.get("/api/jobs/{run_id}")
def api_get_job(run_id: str, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    job = get_job(run_id)
    durable = None
    try:
        from vendor_intel.storage.gcs_export import pull_job_status, status_to_registry_job
        from ui.job_registry import upsert_job

        durable = pull_job_status(run_id)
        if durable:
            owner = str(durable.get("owner_email") or "").strip().lower()
            if owner and owner != user["email"].strip().lower():
                raise HTTPException(status_code=404, detail="Job not found")
    except HTTPException:
        raise
    except Exception:
        durable = None

    if not job and durable:
        job = upsert_job(status_to_registry_job(durable))
    elif job and durable:
        # Merge so polls on non-worker instances don't wipe phase/progress backwards.
        try:
            job["phase"] = max(int(job.get("phase") or 0), int(durable.get("phase") or 0))
            dlog = str(durable.get("log_tail") or "")
            jlog = str(job.get("log") or "")
            if len(dlog) > len(jlog):
                job["log"] = dlog
            if durable.get("cancel_requested"):
                job["cancel_requested"] = True
            if durable.get("cancelled"):
                job["cancelled"] = True
                job["running"] = False
            if durable.get("has_result") and not job.get("result"):
                job["has_result"] = True
                job["slug"] = durable.get("slug") or job.get("slug") or ""
        except Exception:
            pass
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    owner = str(job.get("owner_email") or "").strip().lower()
    if owner and owner != user["email"].strip().lower():
        raise HTTPException(status_code=404, detail="Job not found")
    return _serialize_job(job)


@app.get("/api/jobs")
def api_my_active_job(user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    """Only a truly live run owned by this user (not user-stopped)."""
    from ui.job_registry import owner_has_running_job

    email = str(user["email"] or "").strip().lower()
    # Reconcile zombies before answering.
    owner_has_running_job(email)
    for job in jobs_for_owner(email):
        owner = str(job.get("owner_email") or "").strip().lower()
        if owner != email:
            continue
        if (
            job.get("running")
            and not job.get("cancelled")
            and not job.get("cancel_requested")
        ):
            return {"job": _serialize_job(job)}
    return {"job": None}


@app.post("/api/jobs/{run_id}/stop")
def api_stop_job(
    run_id: str,
    force: bool = False,
    user: dict[str, Any] = Depends(require_user),
) -> dict[str, Any]:
    job = get_job(run_id)
    if not job:
        try:
            from vendor_intel.storage.gcs_export import pull_job_status, status_to_registry_job
            from ui.job_registry import upsert_job

            status = pull_job_status(run_id)
            if status:
                owner = str(status.get("owner_email") or "").strip().lower()
                if owner and owner != user["email"].strip().lower():
                    raise HTTPException(status_code=404, detail="Job not found")
                job = upsert_job(status_to_registry_job(status))
        except HTTPException:
            raise
        except Exception:
            job = None
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    owner = str(job.get("owner_email") or "").strip().lower()
    if owner != user["email"].strip().lower():
        raise HTTPException(status_code=404, detail="Job not found")

    if force:
        JOB_RUNNER.force_finish_cancelled(job)
    else:
        JOB_RUNNER.request_stop(job)
    # Durable cancel so the worker instance (may be another Cloud Run replica) sees it.
    try:
        from vendor_intel.storage.gcs_export import push_job_status

        push_job_status(job)
    except Exception:
        pass
    return _serialize_job(job)


# ---------------------------------------------------------------------------
# Brief / sections (wizard Step 2)
# ---------------------------------------------------------------------------
class SectionsBody(BaseModel):
    market: str = Field(..., min_length=1)
    geography: str = "global"


@app.post("/api/brief/sections")
def api_generate_sections(
    body: SectionsBody,
    user: dict[str, Any] = Depends(require_user),
) -> dict[str, Any]:
    _ = user
    try:
        from ui.bootstrap import load_settings
        from vendor_intel.funnel.brief_interpreter import generate_market_section_cards

        settings = load_settings("quality")
        cards = generate_market_section_cards(
            body.market.strip(),
            (body.geography or "global").strip() or "global",
            settings,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not draft sections: {exc}") from exc
    cleaned = [
        {"name": str(c.get("name") or "").strip(), "content": str(c.get("content") or "").strip()}
        for c in (cards or [])
        if str(c.get("name") or "").strip()
    ]
    if not cleaned:
        raise HTTPException(
            status_code=502,
            detail="AI could not draft sections right now. Try again, or type section names yourself.",
        )
    return {
        "sections": cleaned,
        # Back-compat for older clients that expect string names only
        "names": [c["name"] for c in cleaned],
    }


class BriefBody(BaseModel):
    market: str = Field(..., min_length=1)
    geography: str = "global"


@app.post("/api/brief/generate")
def api_generate_brief(
    body: BriefBody,
    user: dict[str, Any] = Depends(require_user),
) -> dict[str, Any]:
    _ = user
    try:
        from ui.bootstrap import load_settings
        from vendor_intel.funnel.brief_interpreter import generate_market_brief

        settings = load_settings("quality")
        text = generate_market_brief(
            body.market.strip(),
            (body.geography or "global").strip() or "global",
            settings,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not draft brief: {exc}") from exc
    if not (text or "").strip():
        raise HTTPException(
            status_code=502,
            detail="Could not generate a draft. Switch to 'Write it myself'.",
        )
    return {"brief": text.strip()}


class InterpretBody(BaseModel):
    brief: str = Field(..., min_length=1)
    market: str = ""
    geography: str = "global"


@app.post("/api/brief/interpret")
def api_interpret_brief(
    body: InterpretBody,
    user: dict[str, Any] = Depends(require_user),
) -> dict[str, Any]:
    _ = user
    try:
        from ui.bootstrap import load_settings
        from vendor_intel.funnel.brief_interpreter import interpret_brief

        settings = load_settings("quality")
        spec = interpret_brief(body.brief.strip(), settings) or {}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not interpret brief: {exc}") from exc
    sections = [str(s).strip() for s in (spec.get("sections") or []) if str(s).strip()]
    return {
        "market": str(spec.get("market") or body.market or "").strip(),
        "geography": str(spec.get("geography") or body.geography or "global").strip() or "global",
        "sections": sections,
        "exclude": [str(s).strip() for s in (spec.get("exclude") or []) if str(s).strip()],
        "definition": str(spec.get("definition") or "").strip(),
        "mode": str(spec.get("mode") or ""),
    }


# ---------------------------------------------------------------------------
# Runs / downloads
# ---------------------------------------------------------------------------
@app.get("/api/runs")
def api_list_runs(user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    owned = list_owned_runs(user["email"])
    gcs_entries: list[dict[str, Any]] = []
    try:
        from vendor_intel.storage.gcs_export import gcs_enabled, list_gcs_run_entries

        if gcs_enabled():
            gcs_entries = list_gcs_run_entries()
    except Exception as exc:
        return {"owned": owned, "cloud": [], "error": str(exc)}
    return {"owned": owned[:50], "cloud": gcs_entries[:80]}


@app.get("/api/runs/{slug}/downloads")
def api_downloads(slug: str, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    _ = user
    slug = (slug or "").strip()
    if not slug or "/" in slug or "\\" in slug or ".." in slug:
        raise HTTPException(status_code=400, detail="Missing or invalid slug")
    # Same-origin proxy links (cookie auth) — more reliable than GCS signed URLs in-browser.
    urls = {
        "xlsx": f"/api/runs/{slug}/file/xlsx",
        "docx": f"/api/runs/{slug}/file/docx",
        "csv": f"/api/runs/{slug}/file/csv",
    }
    signed: dict[str, str] = {}
    try:
        from vendor_intel.storage.gcs_export import signed_urls_for_slug

        signed = signed_urls_for_slug(slug) or {}
    except Exception:
        signed = {}
    return {"slug": slug, "urls": urls, "signed": signed}


@app.get("/api/runs/{slug}/file/{kind}")
def api_run_file(
    slug: str,
    kind: str,
    user: dict[str, Any] = Depends(require_user),
):
    _ = user
    slug = (slug or "").strip()
    kind = (kind or "").strip().lower()
    if not slug or "/" in slug or "\\" in slug or ".." in slug:
        raise HTTPException(status_code=400, detail="Invalid slug")
    if kind not in {"xlsx", "docx", "csv"}:
        raise HTTPException(status_code=400, detail="kind must be xlsx, docx, or csv")

    filename = f"{slug}.{kind}"
    raw: bytes | None = None
    try:
        from vendor_intel.storage.gcs_export import download_run_file_bytes

        raw = download_run_file_bytes(slug, filename)
    except Exception:
        raw = None
    if not raw:
        local = ROOT / "output" / "demo" / filename
        if local.is_file() and local.stat().st_size > 0:
            raw = local.read_bytes()
    if not raw:
        raise HTTPException(status_code=404, detail=f"{filename} not found")

    media = {
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "csv": "text/csv; charset=utf-8",
    }[kind]
    from fastapi.responses import Response

    return Response(
        content=raw,
        media_type=media,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, max-age=60",
        },
    )


@app.get("/api/runs/{slug}/preview")
def api_run_preview(slug: str, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    _ = user
    slug = (slug or "").strip()
    if not slug or "/" in slug or "\\" in slug or ".." in slug:
        raise HTTPException(status_code=400, detail="Invalid slug")

    import csv
    import io

    from vendor_intel.storage.gcs_export import download_run_file_bytes, materialize_run_files

    out_dir = ROOT / "output" / "demo"
    csv_path = out_dir / f"{slug}.csv"
    try:
        if not csv_path.is_file() or csv_path.stat().st_size <= 0:
            materialize_run_files(slug, out_dir)
    except Exception:
        pass

    text = ""
    if csv_path.is_file() and csv_path.stat().st_size > 0:
        text = csv_path.read_text(encoding="utf-8", errors="replace")
    else:
        raw = download_run_file_bytes(slug, f"{slug}.csv")
        if raw:
            text = raw.decode("utf-8", errors="replace")
    if not text.strip():
        raise HTTPException(status_code=404, detail="Preview CSV not found")

    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return {"slug": slug, "headers": [], "sections": []}
    header = [str(h) for h in rows[0]]
    sections: list[dict[str, Any]] = []
    current_name = "Companies"
    current_rows: list[dict[str, str]] = []

    def flush() -> None:
        nonlocal current_rows
        if current_rows:
            sections.append({"name": current_name, "rows": current_rows})
            current_rows = []

    for r in rows[1:]:
        if not r or not any(str(c).strip() for c in r):
            continue
        first = str(r[0]).strip()
        if first.startswith("==="):
            flush()
            current_name = first.strip("= ").rsplit(" (", 1)[0].strip() or "Section"
            continue
        current_rows.append({header[i] if i < len(header) else f"c{i}": str(r[i]) if i < len(r) else "" for i in range(len(header))})
    flush()
    return {
        "slug": slug,
        "headers": header,
        "sections": sections,
        "company_count": sum(len(s["rows"]) for s in sections),
    }


# ---------------------------------------------------------------------------
# Static Next.js export
# ---------------------------------------------------------------------------
FRONTEND_DIST = Path(os.getenv("FRONTEND_DIST") or str(ROOT / "frontend" / "out"))


def _mount_frontend() -> None:
    if not FRONTEND_DIST.is_dir():
        return
    assets = FRONTEND_DIST / "_next"
    if assets.is_dir():
        app.mount("/_next", StaticFiles(directory=str(assets)), name="next_assets")

    index = FRONTEND_DIST / "index.html"

    @app.get("/")
    async def spa_root():
        if index.is_file():
            return FileResponse(index)
        raise HTTPException(status_code=404, detail="Frontend not built")

    @app.get("/{full_path:path}")
    async def spa(full_path: str):
        # Don't steal API/health
        if full_path.startswith("api/") or full_path in {"health", "_stcore/health"}:
            raise HTTPException(status_code=404)
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        # Static export pages often as path/index.html
        as_index = FRONTEND_DIST / full_path / "index.html"
        if as_index.is_file():
            return FileResponse(as_index)
        if index.is_file():
            return FileResponse(index)
        raise HTTPException(status_code=404, detail="Frontend not built")


_mount_frontend()


def main() -> None:
    import uvicorn

    port = int(os.getenv("PORT") or "8080")
    uvicorn.run("api.main:app", host="0.0.0.0", port=port, reload=False)


if __name__ == "__main__":
    main()
