#!/usr/bin/env python3
"""Run Google Alerts backend scraper (collect articles into data/alerts/articles.json)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vendor_intel.alerts.scraper import scrape_alerts_sync
from vendor_intel.config import Settings


def main() -> int:
    parser = argparse.ArgumentParser(description="Google Alerts backend worker")
    parser.add_argument("--headless", action="store_true", default=None)
    parser.add_argument("--no-browser", action="store_true", help="RSS only; skip Selenium")
    parser.add_argument("--profile", type=str, default=None)
    args = parser.parse_args()

    settings = Settings.load()
    profile = Path(args.profile) if args.profile else Path(settings.google_alerts_profile_path)
    if not profile.is_absolute():
        profile = ROOT / profile

    headless = settings.google_alerts_headless if args.headless is None else args.headless
    store = Path(settings.google_alerts_store_path)
    if not store.is_absolute():
        store = ROOT / store

    rss = settings.google_alerts_rss_urls
    print(f"Profile: {profile}")
    print(f"Store: {store}")
    if rss:
        print(f"RSS feeds: {len([u for u in rss.split(',') if u.strip()])} configured")
    if args.no_browser:
        print("Mode: RSS only (no browser)")
    articles = scrape_alerts_sync(
        profile_path=profile,
        headless=headless,
        store_path=store,
        rss_urls=rss,
        use_selenium=not args.no_browser,
    )
    print(f"Stored {len(articles)} articles total.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
