"""Pipeline and data services for the Streamlit UI."""
from __future__ import annotations

import io
import json
import re
import sys
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from ui.bootstrap import ROOT, init_env, output_dir, phase1_debug_dir


def slug(query: str, country: str) -> str:
    text = f"{query}_{country}".lower()
    return "".join(c if c.isalnum() else "_" for c in text).strip("_")[:80]


def parse_query_line(raw: str) -> tuple[str, str]:
    if "|" in raw:
        parts = raw.split("|", 1)
        return parts[0].strip(), (parts[1].strip() or "global")
    return raw.strip(), "global"


def load_queries_file(path: Path) -> list[tuple[str, str]]:
    if not path.exists():
        return []
    rows: list[tuple[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        rows.append(parse_query_line(line))
    return rows


def list_result_csvs() -> list[Path]:
    out = output_dir()
    files = sorted(out.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [p for p in files if p.name != "session_log.json"]


def _merge_session_logs(local: list[dict], remote: list[dict]) -> list[dict]:
    """Union by run_id (prefer newer ran_at); fall back to full entry identity."""
    by_key: dict[str, dict] = {}

    def _key(entry: dict) -> str:
        rid = str(entry.get("run_id") or "").strip()
        if rid:
            return f"run:{rid}"
        return (
            f"fb:{entry.get('owner_email')}|{entry.get('query')}|{entry.get('ran_at')}|"
            f"{entry.get('csv_file')}"
        )

    for entry in list(remote) + list(local):
        if not isinstance(entry, dict):
            continue
        k = _key(entry)
        prev = by_key.get(k)
        if not prev:
            by_key[k] = entry
            continue
        # Keep the richer / later entry
        prev_t = str(prev.get("ran_at") or "")
        cur_t = str(entry.get("ran_at") or "")
        if cur_t >= prev_t:
            merged = dict(prev)
            merged.update({kk: vv for kk, vv in entry.items() if vv not in (None, "", [], {})})
            by_key[k] = merged
    return sorted(
        by_key.values(),
        key=lambda e: str(e.get("ran_at") or ""),
    )


def load_session_log() -> list[dict]:
    log_path = output_dir() / "session_log.json"
    local: list[dict] = []
    if log_path.exists():
        try:
            raw = json.loads(log_path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                local = raw
        except Exception:
            local = []
    remote: list[dict] = []
    try:
        from vendor_intel.storage.gcs_export import gcs_enabled, pull_session_log

        if gcs_enabled():
            remote = pull_session_log()
    except Exception:
        remote = []
    merged = _merge_session_logs(local, remote)
    # Refresh local cache so subsequent reads are fast / offline-tolerant
    if merged and merged != local:
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(json.dumps(merged, indent=2, default=str), encoding="utf-8")
        except Exception:
            pass
    return merged


def append_session_log(entry: dict) -> None:
    log = load_session_log()
    log.append(entry)
    out = output_dir()
    out.mkdir(parents=True, exist_ok=True)
    (out / "session_log.json").write_text(
        json.dumps(log, indent=2, default=str), encoding="utf-8"
    )
    try:
        from vendor_intel.storage.gcs_export import gcs_enabled, push_session_log

        if gcs_enabled():
            push_session_log(log)
    except Exception as exc:
        print(f"  [gcs] could not sync session_log: {exc}", flush=True)


def list_result_csvs_for_owner(owner_email: str) -> list[Path]:
    """Only the CSVs from runs this user actually kicked off.

    session_log.json records owner_email per run (added alongside job_registry);
    older entries logged before that change have no owner and are excluded —
    they predate per-user scoping, so there's no safe way to attribute them.
    """
    owned_names: set[str] = set()
    for entry in load_session_log():
        if entry.get("owner_email") == owner_email:
            csv_file = entry.get("csv_file") or ""
            if csv_file:
                owned_names.add(Path(csv_file).name)
    return [p for p in list_result_csvs() if p.name in owned_names]


def list_owned_runs(owner_email: str) -> list[dict]:
    """Newest-first finished runs for Search history / Saved landscapes.

    Includes:
    - session_log rows owned by this user (status=ok)
    - any finished run folders already in GCS (team shared history) — older
      deploys uploaded Excel/Word without writing session_log entries
    """
    email = (owner_email or "").strip().lower()
    rows = [
        e
        for e in load_session_log()
        if str(e.get("status") or "") == "ok"
        and (e.get("csv_file") or e.get("xlsx_file") or e.get("docx_file") or e.get("slug"))
        and (
            not str(e.get("owner_email") or "").strip()
            or str(e.get("owner_email") or "").strip().lower() == email
        )
    ]

    known_slugs = {run_slug_from_entry(e) for e in rows if run_slug_from_entry(e)}
    try:
        from vendor_intel.storage.gcs_export import gcs_enabled, list_gcs_run_entries

        if gcs_enabled():
            for entry in list_gcs_run_entries():
                slug = run_slug_from_entry(entry)
                if slug and slug in known_slugs:
                    continue
                rows.append(entry)
                if slug:
                    known_slugs.add(slug)
    except Exception as exc:
        print(f"  [gcs] history list failed: {exc}", flush=True)

    rows.sort(key=lambda e: str(e.get("ran_at") or ""), reverse=True)
    return rows


def run_slug_from_entry(entry: dict) -> str:
    for key in ("csv_file", "xlsx_file", "docx_file"):
        path = entry.get(key) or ""
        if path:
            return Path(path).stem
    return str(entry.get("slug") or "").strip()


def _safe_stdout_write(stream: Any, data: str) -> None:
    """Windows consoles often use cp1252 — avoid crashing on ≤, →, etc."""
    try:
        stream.write(data)
    except UnicodeEncodeError:
        enc = getattr(stream, "encoding", None) or "utf-8"
        stream.write(data.encode(enc, errors="replace").decode(enc, errors="replace"))


@contextmanager
def capture_stdout(callback: Callable[[str], None]):
    buffer = io.StringIO()
    old_stdout = sys.stdout

    class Tee:
        def write(self, data: str) -> int:
            _safe_stdout_write(old_stdout, data)
            buffer.write(data)
            callback(data)
            return len(data)

        def flush(self) -> None:
            old_stdout.flush()

    sys.stdout = Tee()
    try:
        yield buffer
    finally:
        sys.stdout = old_stdout


def run_full_pipeline(
    query: str,
    country: str,
    profile: str,
    *,
    cap: str | None = None,
    brief: str = "",
    scope: dict[str, Any] | None = None,
    log_callback: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    from run_query import run_one_query, _parse_input

    from ui.bootstrap import load_settings, pipeline_caps

    init_env()
    settings = load_settings(profile)
    if cap:
        from vendor_intel.pipeline.cap_profiles import apply_cap

        settings = apply_cap(settings, cap)

    exclude: list[str] = []
    definition = ""
    if scope:
        # Pre-interpreted (and possibly user-edited) scope from the confirmation step.
        market = str(scope.get("market") or "")
        use_country = str(scope.get("geography") or country or "global")
        sections = list(scope.get("sections") or [])
        exclude = list(scope.get("exclude") or [])
        definition = str(scope.get("definition") or "")
    elif brief and brief.strip():
        # Detailed-brief mode: let the AI interpret what to include / exclude.
        from vendor_intel.funnel.brief_interpreter import interpret_brief

        spec = interpret_brief(brief, settings)
        market = spec["market"]
        use_country = (
            country.strip() if country and country.strip().lower() != "global" else spec["geography"]
        )
        sections = spec["sections"]
        exclude = spec["exclude"]
        definition = spec["definition"]
    else:
        # Let users type "Market | Country | Section A; Section B" in the query box.
        market, q_country, sections = _parse_input(query)
        use_country = (
            country.strip()
            if country and country.strip() and country.strip().lower() != "global"
            else q_country
        )
    classify_cap, enrich_cap = pipeline_caps(settings, country=use_country)

    def _noop(_: str) -> None:
        pass

    cb = log_callback or _noop
    with capture_stdout(cb):
        result = run_one_query(
            market,
            use_country,
            settings,
            enrich_limit=enrich_cap,
            classify_limit=classify_cap,
            sections=sections,
            exclude_segments=exclude,
            market_definition=definition,
        )
    return result


def run_phase1_preview(
    query: str,
    country: str,
    *,
    with_search: bool = False,
    log_callback: Callable[[str], None] | None = None,
) -> tuple[dict, str]:
    from test_phase1 import _full_query, build_report

    from vendor_intel.phase1.runner import run_phase1_sync, print_phase1_summary

    from ui.bootstrap import load_settings

    init_env()
    settings = load_settings("quality")
    full_query = _full_query(query, country)

    if not with_search:
        import vendor_intel.pipeline.geo_limits as geo_limits

        original = geo_limits.pipeline_limits

        def plan_only_limits(s, *, recall, country):
            lim = original(s, recall=recall, country=country)
            return {**lim, "smoke_prompts": 0}

        geo_limits.pipeline_limits = plan_only_limits

    def _noop(_: str) -> None:
        pass

    cb = log_callback or _noop
    with capture_stdout(cb):
        manifest = run_phase1_sync(full_query, settings)
        try:
            print_phase1_summary(manifest)
        except UnicodeEncodeError:
            pass

    report_md = build_report(query, country, manifest)
    debug = phase1_debug_dir()
    s = slug(query, country)
    (debug / f"{s}.md").write_text(report_md, encoding="utf-8")
    (debug / f"{s}.json").write_text(
        json.dumps(manifest, indent=2, default=str), encoding="utf-8"
    )
    return manifest, report_md


def shutdown_search_pool() -> None:
    try:
        from vendor_intel.clients.ddg_worker_pool import shutdown_ddg_pool

        shutdown_ddg_pool(wait=True)
    except Exception:
        pass


# Up to N pipelines per instance. Each user may only run one at a time so
# User A never blocks User B (unless the instance is at capacity).
_MAX_PIPELINES_PER_INSTANCE = 2
_pipeline_slots = threading.BoundedSemaphore(_MAX_PIPELINES_PER_INSTANCE)


def pipeline_is_busy(owner_email: str | None = None) -> bool:
    """True if this user cannot start a new run right now.

    - Same user already has a running job → busy
    - Instance already has ``_MAX_PIPELINES_PER_INSTANCE`` runs → busy
    """
    from ui.job_registry import count_running_jobs, owner_has_running_job

    if owner_email and owner_has_running_job(owner_email):
        return True
    return count_running_jobs() >= _MAX_PIPELINES_PER_INSTANCE


def pipeline_busy_reason(owner_email: str | None = None) -> str | None:
    """Human message when Start should be blocked, else None."""
    from ui.job_registry import count_running_jobs, jobs_for_owner, owner_has_running_job

    if owner_email and owner_has_running_job(owner_email):
        mine = next(
            (
                j
                for j in jobs_for_owner(owner_email)
                if j.get("running") and not j.get("cancelled")
            ),
            None,
        )
        label = ""
        if mine:
            label = str(mine.get("query") or "").strip() or str(mine.get("run_id") or "")
        if label:
            return (
                f"You already have a landscape running on this server ({label}). "
                "Open Current run for progress, or Stop it before starting another."
            )
        return (
            "You already have a landscape running on this server — open Current run "
            "for progress, or Stop it before starting another."
        )
    if count_running_jobs() >= _MAX_PIPELINES_PER_INSTANCE:
        return (
            "This server is at capacity right now (other people's landscapes are running). "
            "Wait a few minutes for a run to finish, then try Start again."
        )
    return None


def _other_pipelines_running(except_run_id: str | None = None) -> bool:
    from ui.job_registry import running_jobs

    for j in running_jobs():
        if except_run_id and str(j.get("run_id")) == str(except_run_id):
            continue
        return True
    return False


class JobRunner:
    """Background thread runner. Job state lives in ui.job_registry (a plain
    process-wide dict keyed by run_id), not st.session_state — so a page
    reload or a fresh tab can still find and display the same running job,
    as long as it carries the same run_id (see app.py's ?run= query param).
    """

    def __init__(self, state_key: str = "active_job"):
        self.state_key = state_key  # kept only for call-site compatibility

    def request_stop(self, job: dict | None) -> None:
        """User clicked Stop — signal the worker and mark the job stopped in durable
        status so a refresh does **not** reconnect as a live run.

        (Deploy/crash reconnect still works for jobs that were never cancelled.)
        """
        from vendor_intel.pipeline.cancel import request_cancel

        job = job or {}
        if not job.get("running") and job.get("cancelled"):
            return
        run_id = str(job.get("run_id") or "")
        job["cancel_requested"] = True
        job["cancel_requested_at"] = time.time()
        job["cancelled"] = True
        job["running"] = False
        job["error"] = None
        request_cancel(run_id or None)
        # Only tear down the shared search pool if nobody else is running.
        if not _other_pipelines_running(except_run_id=run_id):
            try:
                from vendor_intel.clients.ddg_worker_pool import shutdown_ddg_pool

                shutdown_ddg_pool(wait=False)
            except Exception:
                pass
        try:
            from vendor_intel.storage.gcs_export import push_job_status

            push_job_status(job)
        except Exception:
            pass

    def force_finish_cancelled(self, job: dict | None) -> None:
        """UI failsafe when the worker does not exit quickly after Stop."""
        from vendor_intel.pipeline.cancel import request_cancel

        job = job or {}
        if not job.get("running"):
            return
        run_id = str(job.get("run_id") or "")
        request_cancel(run_id or None)
        job["cancel_requested"] = True
        job["cancelled"] = True
        job["running"] = False
        job["error"] = None
        if not _other_pipelines_running(except_run_id=run_id):
            try:
                from vendor_intel.clients.ddg_worker_pool import shutdown_ddg_pool

                shutdown_ddg_pool(wait=False)
            except Exception:
                pass
        try:
            from vendor_intel.storage.gcs_export import push_job_status

            push_job_status(job)
        except Exception:
            pass

    def start(
        self,
        *,
        owner_email: str,
        job_type: str,
        query: str,
        country: str,
        profile: str = "quality",
        cap: str | None = None,
        with_search: bool = False,
        brief: str = "",
        scope: dict[str, Any] | None = None,
    ) -> str | None:
        """Returns the new run_id on success, or None if this user/instance cannot start."""
        if pipeline_is_busy(owner_email):
            return None

        from vendor_intel.pipeline.cancel import (
            PipelineCancelled,
            bind_run,
            clear_cancel,
            is_cancelled,
            unbind_run,
        )
        from ui.job_registry import create_job, new_run_id

        run_id = new_run_id()
        job = create_job(
            run_id,
            owner_email=owner_email,
            job_type=job_type,
            query=query,
            country=country,
            profile=profile,
            cap=cap,
        )
        # Durable progress snapshot (local + GCS) so reconnect works across instances.
        try:
            from vendor_intel.storage.gcs_export import push_job_status

            push_job_status(job)
        except Exception as exc:
            print(f"  [job-status] initial push failed: {exc}", flush=True)

        def worker() -> None:
            if not _pipeline_slots.acquire(blocking=False):
                job["running"] = False
                job["error"] = (
                    "This server is at capacity right now. Wait a few minutes and try again."
                )
                try:
                    from vendor_intel.storage.gcs_export import push_job_status

                    push_job_status(job)
                except Exception:
                    pass
                return

            slot_held = True
            bind_run(run_id)
            clear_cancel()
            _last_status_push = [0.0]

            def _sync_status(force: bool = False) -> None:
                now = time.time()
                if not force and (now - _last_status_push[0]) < 12.0:
                    return
                _last_status_push[0] = now
                try:
                    from vendor_intel.storage.gcs_export import pull_job_status, push_job_status

                    # Cross-instance Stop: another replica may have written cancel.
                    remote = pull_job_status(run_id)
                    if remote and (remote.get("cancelled") or remote.get("cancel_requested")):
                        job["cancel_requested"] = True
                        request_cancel(run_id)
                        if remote.get("cancelled"):
                            # User Stop is final — do not push running=true over it.
                            job["cancelled"] = True
                            job["running"] = False
                            push_job_status(job)
                            return
                    # Local Stop already finalized this job.
                    if job.get("cancelled") or not job.get("running"):
                        push_job_status(job)
                        return
                    # Keep phase high-water mark for cross-instance UI polls.
                    try:
                        from vendor_intel.storage.gcs_export import _phase_from_log as _pfl

                        job["phase"] = max(
                            int(job.get("phase") or 0),
                            int(_pfl(str(job.get("log") or ""))),
                        )
                    except Exception:
                        pass
                    push_job_status(job)
                except Exception as exc:
                    print(f"  [job-status] push failed: {exc}", flush=True)

            def on_log(chunk: str) -> None:
                job["log"] = (job.get("log") or "") + chunk
                if len(job["log"]) > 120_000:
                    job["log"] = job["log"][-100_000:]
                _sync_status(force=False)
                if is_cancelled() or job.get("cancel_requested"):
                    raise PipelineCancelled("Stopped by user.")

            market_label = query or (str((scope or {}).get("market") or "").strip())
            try:
                if job_type == "pipeline":
                    result = run_full_pipeline(
                        query, country, profile, cap=cap, brief=brief, scope=scope, log_callback=on_log
                    )
                    if is_cancelled() or job.get("cancel_requested"):
                        raise PipelineCancelled("Stopped by user.")
                    job["result"] = result
                    llm = result.get("llm_usage") or {}
                    elapsed = time.time() - job["started_at"]
                    append_session_log(
                        {
                            "run_id": run_id,
                            "owner_email": owner_email,
                            "query": market_label,
                            "country": country,
                            "status": "ok",
                            "companies_exported": len(result.get("relevant_companies") or []),
                            "elapsed_seconds": round(elapsed, 1),
                            "elapsed_minutes": round(elapsed / 60, 2),
                            "llm_calls": llm.get("llm_calls_total"),
                            "estimated_cost_usd": llm.get("estimated_cost_usd"),
                            "csv_file": result.get("_csv_path", ""),
                            "xlsx_file": result.get("_xlsx_path", ""),
                            "docx_file": result.get("_docx_path", ""),
                            "slug": Path(str(result.get("_csv_path") or "run")).stem,
                            "gcs_xlsx": result.get("_xlsx_gcs_url", ""),
                            "gcs_docx": result.get("_docx_gcs_url", ""),
                            "gcs_csv": result.get("_csv_gcs_url", ""),
                            "ran_at": datetime.now(timezone.utc).isoformat(),
                        }
                    )
                else:
                    manifest, report_md = run_phase1_preview(
                        query,
                        country,
                        with_search=with_search,
                        log_callback=on_log,
                    )
                    job["result"] = {"manifest": manifest, "report_md": report_md}
            except PipelineCancelled:
                job["cancelled"] = True
                job["error"] = None
                append_session_log(
                    {
                        "run_id": run_id,
                        "owner_email": owner_email,
                        "query": market_label,
                        "country": country,
                        "status": "cancelled",
                        "elapsed_seconds": round(time.time() - job["started_at"], 1),
                        "ran_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
            except Exception as exc:
                if is_cancelled() or job.get("cancel_requested"):
                    job["cancelled"] = True
                    job["error"] = None
                    append_session_log(
                        {
                            "run_id": run_id,
                            "owner_email": owner_email,
                            "query": market_label,
                            "country": country,
                            "status": "cancelled",
                            "elapsed_seconds": round(time.time() - job["started_at"], 1),
                            "ran_at": datetime.now(timezone.utc).isoformat(),
                        }
                    )
                else:
                    job["error"] = str(exc)
                    if job_type == "pipeline":
                        append_session_log(
                            {
                                "run_id": run_id,
                                "owner_email": owner_email,
                                "query": market_label,
                                "country": country,
                                "status": "error",
                                "error": str(exc),
                                "elapsed_seconds": round(time.time() - job["started_at"], 1),
                                "ran_at": datetime.now(timezone.utc).isoformat(),
                            }
                        )
            finally:
                job["running"] = False
                clear_cancel()
                unbind_run(run_id)
                if not _other_pipelines_running(except_run_id=run_id):
                    shutdown_search_pool()
                _sync_status(force=True)
                if slot_held:
                    try:
                        _pipeline_slots.release()
                    except ValueError:
                        pass

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        return run_id

    @staticmethod
    def verdict_badge(manifest: dict) -> tuple[str, list[str]]:
        from test_phase1 import _verdict

        scope = manifest.get("scope") or {}
        return _verdict(scope, manifest)


def markdown_to_plain_preview(md: str, max_lines: int = 40) -> str:
    lines = md.splitlines()[:max_lines]
    text = "\n".join(lines)
    return re.sub(r"\*\*", "", text)
