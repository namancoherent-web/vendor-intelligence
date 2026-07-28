#!/usr/bin/env python3
"""
Proxy pipeline: fetch → verify → utilize (for ddgs search).

Sources:
  - Proxifly  https://github.com/proxifly/free-proxy-list
  - ProxyScrape
  - Geonode

Run once before live Phase 1/2 (or set DDGS_AUTO_PROXY=true):

  .venv\\Scripts\\python.exe scripts\\check_proxies.py

Then in .env:
  DDGS_USE_PROXY_POOL=true
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

from vendor_intel.clients.proxy_pool import (
    default_cache_path,
    load_verified_pool,
    run_proxy_pipeline,
)


def _log(msg: str) -> None:
    print(f"  [proxy] {msg}", flush=True)


def main() -> int:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(
        description="Fetch proxies, verify, cache, set DDGS_PROXY"
    )
    parser.add_argument(
        "--max-check",
        type=int,
        default=int(os.getenv("PROXY_MAX_CHECK", "40")),
    )
    parser.add_argument(
        "--no-ddgs-test",
        action="store_true",
        help="Skip ddgs.text verification (HTTPS only)",
    )
    parser.add_argument("--cache", type=Path, default=None)
    parser.add_argument(
        "--show",
        action="store_true",
        help="Print cached pool only",
    )
    parser.add_argument(
        "--no-env",
        action="store_true",
        help="Do not set DDGS_PROXY in this process",
    )
    args = parser.parse_args()

    cache = args.cache or default_cache_path()
    print("\n=== Proxy pipeline (fetch → verify → utilize) ===\n", flush=True)

    if args.show:
        entries = load_verified_pool(cache)
        _log(f"Cache: {cache} ({len(entries)} proxies)")
        for e in entries[:25]:
            tag = "ddgs+https" if e.ddgs_ok else "https"
            _log(f"  [{tag}] {e.url}  ({e.source})")
        return 0 if entries else 1

    result = run_proxy_pipeline(
        max_check=args.max_check,
        test_ddgs=not args.no_ddgs_test,
        cache_path=cache,
        apply_to_env=not args.no_env,
        log_print=_log,
    )

    if not result.entries:
        print(
            "\n  Failed — try: --max-check 60  or run again in a few minutes.\n",
            flush=True,
        )
        return 1

    best = result.best
    print(
        f"\n  Done: {result.fetched_total} fetched → "
        f"{result.https_verified} HTTPS OK → "
        f"{result.ddgs_verified} ddgs OK\n"
        f"  Cache: {result.cache_path}\n"
        f"  .env:\n"
        f"    DDGS_USE_PROXY_POOL=true\n"
        + (f"    DDGS_PROXY={best.url}\n" if best else "")
        + "\n  Phase 1/2 will rotate through the cache automatically.\n",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
