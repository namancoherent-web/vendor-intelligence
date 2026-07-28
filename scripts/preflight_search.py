#!/usr/bin/env python3
"""
Network preflight for Vendor Intelligence (Phase 1/2/3).

Production-safe design:
- Jittered delays between every probe (no fixed machine intervals)
- DDGS text search via context manager; prefers bing/brave backends (not duckduckgo.com)
- Rate limits / 403 / 429 never crash the process (exit 0 unless --strict-exit)
- Optional direct duckduckgo.com TCP probe (off by default — reduces firewall trips)

Run:
  .venv\\Scripts\\python.exe scripts\\preflight_search.py
"""
from __future__ import annotations

import argparse
import asyncio
import os
import random
import socket
import sys
import time
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vendor_intel.clients.ddgs_engines import ENGINE_TCP_HOSTS, ddgs_client_kwargs
from vendor_intel.clients.duckduckgo import configured_ddgs_backends
from vendor_intel.clients.searxng import searxng_ping_any, searxng_urls
from vendor_intel.config import Settings

# ---------------------------------------------------------------------------
# Timing & headers (human-like footprint)
# ---------------------------------------------------------------------------

JITTER_MIN = float(os.getenv("PREFLIGHT_JITTER_MIN", "3.0"))
JITTER_MAX = float(os.getenv("PREFLIGHT_JITTER_MAX", "6.0"))
PROBE_TIMEOUT = float(os.getenv("PREFLIGHT_TCP_TIMEOUT", "4.0"))
DDGS_TIMEOUT = int(os.getenv("DDGS_TIMEOUT", "15"))
SMOKE_QUERY = os.getenv(
    "PREFLIGHT_SMOKE_QUERY", "Sun Pharma India pharmaceutical company"
)
SMOKE_MAX_RESULTS = int(os.getenv("PREFLIGHT_MAX_RESULTS", "2"))

_BROWSER_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.bing.com/",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

_ROTATING_USER_AGENTS = [
    _BROWSER_HEADERS["User-Agent"],
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) "
        "Gecko/20100101 Firefox/125.0"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.4 Safari/605.1.15"
    ),
]


def _jitter(label: str = "") -> None:
    delay = random.uniform(JITTER_MIN, JITTER_MAX)
    if label:
        print(f"  [preflight] pause {delay:.1f}s ({label})", flush=True)
    time.sleep(delay)


def _log(msg: str) -> None:
    print(f"  [search] {msg}", flush=True)


# ---------------------------------------------------------------------------
# ddgs loader (deedy5/ddgs only — https://github.com/deedy5/ddgs)
# ---------------------------------------------------------------------------

_DDGS_CLASS: Any = None
_RATE_LIMIT_EXC: tuple[type[BaseException], ...] = (Exception,)
_DDG_EXC: tuple[type[BaseException], ...] = (Exception,)


def _load_ddgs() -> Any | None:
    global _DDGS_CLASS, _RATE_LIMIT_EXC, _DDG_EXC
    if _DDGS_CLASS is not None:
        return _DDGS_CLASS
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        try:
            from ddgs import DDGS as cls
            from ddgs.exceptions import DDGSException, RatelimitException

            _DDGS_CLASS = cls
            _RATE_LIMIT_EXC = (RatelimitException,)
            _DDG_EXC = (DDGSException, RatelimitException)
            return cls
        except ImportError:
            return None


def _backend_list() -> list[str]:
    """Per-project safe backends (same as vendor_intel.clients.duckduckgo)."""
    names = configured_ddgs_backends()
    return names or ["bing", "brave"]


def _is_rate_limited(exc: BaseException) -> bool:
    if isinstance(exc, _RATE_LIMIT_EXC):
        return True
    text = str(exc).lower()
    return any(
        x in text
        for x in (
            "ratelimit",
            "rate limit",
            "429",
            "403",
            "too many requests",
            "blocked",
            "captcha",
        )
    )


@dataclass
class SmokeResult:
    ok: bool
    backend: str = ""
    package: str = ""
    hits: int = 0
    sample_title: str = ""
    rate_limited: bool = False
    error: str = ""
    backends_tried: list[str] = field(default_factory=list)


def _parse_ddgs_item(item: dict) -> dict[str, str] | None:
    if not isinstance(item, dict):
        return None
    href = item.get("href") or item.get("link") or ""
    if not href:
        return None
    return {
        "title": (item.get("title") or "")[:120],
        "link": href,
        "snippet": (item.get("body") or item.get("snippet") or "")[:200],
    }


def run_ddgs_smoke(
    query: str,
    backends: list[str],
    *,
    max_results: int = 2,
    region: str = "in-en",
) -> SmokeResult:
    """
    One backend at a time via DDGS context manager (ddgs.text).
    Never raises on rate limit — returns SmokeResult with rate_limited=True.
    """
    DDGS = _load_ddgs()
    if DDGS is None:
        return SmokeResult(
            ok=False,
            error="ddgs not installed (pip install -U ddgs)",
            backends_tried=backends,
        )

    last_err = ""
    rate_hit = False

    for backend in backends:
        _jitter(f"before {backend}")
        rows: list[dict[str, str]] = []
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                with DDGS(**ddgs_client_kwargs()) as ddgs:
                    iterator = ddgs.text(
                        query,
                        region=region,
                        max_results=max_results,
                        backend=backend,
                        safesearch="moderate",
                    )
                    for item in iterator:
                        parsed = _parse_ddgs_item(item)
                        if parsed:
                            rows.append(parsed)
                        if len(rows) >= max_results:
                            break
        except _RATE_LIMIT_EXC as exc:
            rate_hit = True
            last_err = str(exc)[:200]
            _log(
                f"Rate-limited on backend {backend!r} — backing off "
                f"(not fatal). Detail: {last_err[:80]}"
            )
            continue
        except _DDG_EXC as exc:
            if _is_rate_limited(exc):
                rate_hit = True
                last_err = str(exc)[:200]
                _log(f"DDG search blocked on {backend!r}: {last_err[:80]}")
                continue
            last_err = str(exc)[:200]
            _log(f"Backend {backend!r} error: {last_err[:80]}")
            continue
        except Exception as exc:
            if _is_rate_limited(exc):
                rate_hit = True
                last_err = str(exc)[:200]
                _log(f"Network rate-limit on {backend!r}: {last_err[:80]}")
                continue
            last_err = str(exc)[:200]
            _log(f"Backend {backend!r} failed: {type(exc).__name__}: {last_err[:80]}")
            continue

        if rows:
            return SmokeResult(
                ok=True,
                backend=backend,
                package="ddgs",
                hits=len(rows),
                sample_title=rows[0]["title"],
                backends_tried=backends[: backends.index(backend) + 1],
            )

    return SmokeResult(
        ok=False,
        rate_limited=rate_hit,
        error=last_err or "no results from any backend",
        backends_tried=backends,
        package="ddgs",
    )


# ---------------------------------------------------------------------------
# TCP host probes (lightweight; DDG host optional)
# ---------------------------------------------------------------------------

_HOST_PROBES: dict[str, tuple[str, int]] = {
    **ENGINE_TCP_HOSTS,
    "ddg_html": ("html.duckduckgo.com", 443),
    "searxng_local": ("127.0.0.1", 8080),
}


def _tcp_probe(name: str, host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=PROBE_TIMEOUT):
            return True
    except OSError:
        return False


def run_tcp_probes(
    backends: list[str],
    *,
    probe_ddg_host: bool,
    probe_searxng: bool,
) -> dict[str, bool]:
    """Jittered TCP checks — skips duckduckgo.com unless explicitly enabled."""
    results: dict[str, bool] = {}
    to_probe: list[tuple[str, str, int]] = []

    for b in backends:
        if b in _HOST_PROBES:
            h, p = _HOST_PROBES[b]
            to_probe.append((b, h, p))

    if probe_ddg_host:
        to_probe.append(("duckduckgo", *_HOST_PROBES["duckduckgo"]))
        to_probe.append(("ddg_html", *_HOST_PROBES["ddg_html"]))
    if probe_searxng:
        to_probe.append(("searxng_local", *_HOST_PROBES["searxng_local"]))

    _log("Network probe (jittered TCP, one host at a time):")
    for name, host, port in to_probe:
        _jitter(f"TCP {name}")
        ok = _tcp_probe(name, host, port)
        results[name] = ok
        status = "OK" if ok else "BLOCKED"
        print(f"    {name}: {status}", flush=True)

    if not probe_ddg_host:
        print(
            "    duckduckgo: skipped (set PREFLIGHT_PROBE_DDG_HOST=true to probe — "
            "avoids DDG firewall trips)",
            flush=True,
        )
        print(
            "    ddg_html: skipped (same — use DDGS backends bing/brave instead)",
            flush=True,
        )

    return results


# ---------------------------------------------------------------------------
# SearXNG ping with browser-like headers
# ---------------------------------------------------------------------------


async def _searxng_ping_with_headers(urls: list[str]) -> tuple[bool, str]:
    import httpx

    from vendor_intel.clients.http_proxy import httpx_async_client

    if not urls:
        return False, ""
    headers = dict(_BROWSER_HEADERS)
    headers["User-Agent"] = random.choice(_ROTATING_USER_AGENTS)
    _jitter("before SearXNG HTTP")
    try:
        async with httpx_async_client(timeout=12.0, headers=headers) as client:
            for base in urls:
                ping_url = f"{base.rstrip('/')}/config"
                try:
                    r = await client.get(ping_url)
                    if r.status_code < 500:
                        return True, base
                except httpx.HTTPError:
                    continue
    except Exception:
        pass
    return False, ""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> int:
    parser = argparse.ArgumentParser(description="Search stack preflight (safe)")
    parser.add_argument(
        "--probe-ddg-host",
        action="store_true",
        help="Also TCP-probe duckduckgo.com (can trigger firewall; off by default)",
    )
    parser.add_argument(
        "--strict-exit",
        action="store_true",
        help="Exit 1 when smoke test fails (default: always exit 0 on rate limits)",
    )
    parser.add_argument(
        "--query",
        default=SMOKE_QUERY,
        help="Smoke-test search query",
    )
    args = parser.parse_args()

    probe_ddg = args.probe_ddg_host or os.getenv(
        "PREFLIGHT_PROBE_DDG_HOST", ""
    ).strip().lower() in ("1", "true", "yes")

    settings = Settings.load()
    backends = _backend_list()

    print("\n=== Vendor Intelligence — search preflight ===\n", flush=True)
    _log(f"Jitter between steps: {JITTER_MIN:.1f}–{JITTER_MAX:.1f}s")
    _log(f"DDGS backends for smoke test: {', '.join(backends)}")
    if not probe_ddg:
        _log(
            "duckduckgo.com direct probe: OFF (recommended). "
            "Smoke test uses DDGS library via bing/brave — not the DDG website."
        )

    _jitter("startup")

    # 1) TCP probes
    tcp = run_tcp_probes(
        backends,
        probe_ddg_host=probe_ddg,
        probe_searxng=bool(settings.searxng_base_url),
    )

    # 2) DDGS text smoke (core)
    _log(f"DDGS smoke query: {args.query[:60]!r} …")
    smoke = run_ddgs_smoke(
        args.query,
        backends,
        max_results=SMOKE_MAX_RESULTS,
        region="in-en",
    )

    if smoke.ok:
        _log(
            f"DDGS smoke OK — package={smoke.package} backend={smoke.backend} "
            f"hits={smoke.hits} sample={smoke.sample_title!r}"
        )
    elif smoke.rate_limited:
        _log(
            "DDGS smoke: rate-limited / blocked on all tried backends. "
            "Wait 15–60 min before retrying. Pipeline can still use cached Phase JSON. "
            "Add BRAVE_API_KEY or SERPER_API_KEY, or start SearXNG."
        )
    else:
        _log(f"DDGS smoke: no results ({smoke.error[:100]})")

    # 3) SearXNG
    urls = searxng_urls(settings.searxng_base_url)
    if urls:
        ok, used = await _searxng_ping_with_headers(urls)
        if not ok:
            ok, used = await searxng_ping_any(urls)
        _log(f"SearXNG ping: {'OK ' + used if ok else 'FAILED'}")
    else:
        _log("SearXNG: no URL configured")

    # 4) Optional API keys
    if getattr(settings, "brave_api_key", None):
        _log("BRAVE_API_KEY: set (Brave Search API enabled)")
    else:
        _log("BRAVE_API_KEY: not set (optional — https://api.search.brave.com/)")

    if getattr(settings, "serper_api_key", None):
        _log("SERPER_API_KEY: set (Serper enabled)")
    else:
        _log("SERPER_API_KEY: not set (optional — https://serper.dev/)")

    # 5) Recommendations
    reachable = [b for b in backends if tcp.get(b, True)]
    if not smoke.ok and not reachable:
        print(
            "\n  Recommendation: check internet/DNS, wait if rate-limited, "
            "set DDGS_BACKENDS=bing,brave in .env\n",
            flush=True,
        )
    elif not smoke.ok and smoke.rate_limited:
        print(
            "\n  Recommendation: you are rate-limited. Do NOT re-run preflight in a loop. "
            "Wait, use only bing/brave backends, add BRAVE_API_KEY, or docker compose up -d\n",
            flush=True,
        )
    elif not tcp.get("searxng_local") and not settings.brave_api_key:
        serper = getattr(settings, "serper_api_key", None)
        if not serper:
            print(
                "\n  Recommendation: docker compose up -d  OR  add BRAVE_API_KEY to .env\n",
                flush=True,
            )

    print("\n=== Preflight complete (safe exit) ===\n", flush=True)

    if args.strict_exit and not smoke.ok:
        return 1
    return 0


if __name__ == "__main__":
    try:
        code = asyncio.run(main())
    except KeyboardInterrupt:
        print("\n  [preflight] interrupted — exit 0\n", flush=True)
        code = 0
    except Exception as exc:
        if _is_rate_limited(exc):
            print(
                f"\n  [search] Rate-limited at top level: {exc}\n"
                "  Not fatal — wait before retrying. exit 0\n",
                flush=True,
            )
            code = 0
        else:
            print(f"\n  [preflight] unexpected error: {exc}\n", flush=True)
            code = 0
    sys.exit(code)
