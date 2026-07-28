"""Smoke-test live Vendor Intelligence UI: login, console errors, Cloud storage downloads."""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

URL = "https://vendor-intel-6zevitkldq-uc.a.run.app/"
EMAIL = "naman@coherentmarketinsights.com"
OUT = Path(__file__).resolve().parents[1] / "output" / "ui_smoke"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1400,1000")
    opts.add_argument("--disable-gpu")
    opts.set_capability("goog:loggingPrefs", {"browser": "ALL", "performance": "ALL"})

    driver = webdriver.Chrome(options=opts)
    wait = WebDriverWait(driver, 45)
    report: dict = {"url": URL, "ok": True, "steps": [], "console_errors": [], "download_links": []}

    try:
        driver.get(URL)
        time.sleep(3)
        report["steps"].append(f"loaded title={driver.title!r}")

        # Login: email field + Continue (AUTH_SKIP_OTP)
        email_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='email'], input[type='text']")
        if not email_inputs:
            # Streamlit may nest inputs
            email_inputs = driver.find_elements(By.CSS_SELECTOR, "input")
        assert email_inputs, "No login input found"
        email_inputs[0].clear()
        email_inputs[0].send_keys(EMAIL)
        report["steps"].append("typed email")

        buttons = driver.find_elements(By.CSS_SELECTOR, "button")
        clicked = False
        for b in buttons:
            label = (b.text or "").strip().lower()
            if label in {"continue", "log in", "login", "sign in"}:
                b.click()
                clicked = True
                break
        if not clicked and buttons:
            buttons[0].click()
            clicked = True
        report["steps"].append(f"clicked login button={clicked}")
        time.sleep(5)

        body = driver.find_element(By.TAG_NAME, "body").text
        report["body_snippet"] = body[:800]
        if "Signed in" in body or "Vendor Intelligence" in body:
            report["steps"].append("post-login UI visible")
        else:
            report["ok"] = False
            report["steps"].append("login may have failed — Signed in not found")

        # Expand Cloud storage if present
        expanders = driver.find_elements(By.CSS_SELECTOR, "[data-testid='stExpander']")
        for exp in expanders:
            txt = exp.text
            if "Cloud storage" in txt or "Search history" in txt:
                try:
                    summary = exp.find_element(By.CSS_SELECTOR, "summary, [role='button']")
                    summary.click()
                    time.sleep(1.5)
                    report["steps"].append(f"opened expander: {txt.splitlines()[0][:60]}")
                except Exception as exc:
                    report["steps"].append(f"expander click fail: {exc}")

        time.sleep(2)
        # Collect download-ish links
        for a in driver.find_elements(By.CSS_SELECTOR, "a"):
            href = a.get_attribute("href") or ""
            label = (a.text or "").strip()
            if any(k in (label + href).lower() for k in ("download", "excel", "word", "csv", "xlsx", "docx", "storage.googleapis")):
                report["download_links"].append({"label": label[:80], "href_prefix": href[:120]})

        # Also look for Streamlit link buttons
        for el in driver.find_elements(By.CSS_SELECTOR, "a, button"):
            t = (el.text or "").strip()
            if re.search(r"(Excel|Word|CSV|Download)", t, re.I):
                href = el.get_attribute("href") or ""
                report["download_links"].append({"label": t[:80], "href_prefix": href[:120], "tag": el.tag_name})

        # Console errors
        for entry in driver.get_log("browser"):
            msg = entry.get("message", "")
            level = entry.get("level", "")
            if level in ("SEVERE", "ERROR") or "Failed to load" in msg or "TypeError" in msg:
                # Ignore noisy favicon / extension
                if "favicon" in msg.lower():
                    continue
                report["console_errors"].append({"level": level, "message": msg[:300]})

        driver.save_screenshot(str(OUT / "after_login.png"))
        report["screenshot"] = str(OUT / "after_login.png")

        # Red flags in page text
        low = body.lower()
        for bad in ("traceback", "typeerror", "filenotfound", "rate exceeded", "failed to fetch"):
            if bad in low:
                report["ok"] = False
                report["steps"].append(f"UI text contains: {bad}")

    except Exception as exc:
        report["ok"] = False
        report["error"] = str(exc)
        try:
            driver.save_screenshot(str(OUT / "error.png"))
        except Exception:
            pass
    finally:
        driver.quit()

    (OUT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
