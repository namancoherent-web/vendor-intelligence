# Live mode setup

Mock mode uses hardcoded demo data in `src/vendor_intel/mock/`.  
**Live mode** uses real search, scraping, Claude, and optional Google Alerts.

---

## Step 1 — Create `.env` (API keys)

```powershell
cd c:\Users\anish\Desktop\project
copy .env.example .env
notepad .env
```

### Required for live mode

| Variable | Where to get it | Paste in `.env` |
|----------|-----------------|-----------------|
| `USE_MOCK_DATA` | — | Set to **`false`** |
| `LLM_PROVIDER` | — | `anthropic`, `gemini`, `groq`, or `opencode` |
| API key | Provider console | `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `GROQ_API_KEY`, or `OPENCODE_API_KEY` |

Example:

```env
USE_MOCK_DATA=false
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-api03-xxxxxxxx
```

**Do not commit `.env`** — it stays on your machine only.

---

## Step 2 — Install Python packages (new machine)

```powershell
cd c:\Users\anish\Desktop\project
python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Everything needed for search, scrape, and news is in `requirements.txt` (including `duckduckgo-search`).

---

## Step 3 — Free search (no key)

Already configured:

```env
SEARCH_PRIMARY=duckduckgo
SEARCH_BACKUP=searxng
SEARXNG_BASE_URL=http://127.0.0.1:8080
# deedy5/ddgs — avoid backend=auto (uses Startpage). See https://github.com/deedy5/ddgs#engines
DDGS_BACKENDS=duckduckgo,bing,brave,mojeek,google,yahoo

# Free proxies (Proxifly + ProxyScrape + Geonode) — verify then funnel into ddgs:
#   .venv\Scripts\python.exe scripts\check_proxies.py --max-check 40 --test-ddgs
#   DDGS_USE_PROXY_POOL=true
```

| Service | API key? | Notes |
|---------|----------|--------|
| **ddgs multi-backend** | No | Bing/Brave/etc. — **not** Startpage/auto |
| **Wikipedia API** | No | Automatic fallback when web search returns few hits |
| **SearXNG** | No | **Strongly recommended** on Windows — run Docker (below) |

### If you see `startpage.com` / connection refused (10061)

The old default `backend=auto` in `ddgs` tried Startpage. This project forces explicit backends via `DDGS_BACKENDS`. Re-run Phase 1 after setting the line above.

### Start SearXNG (recommended if you have Docker)

```powershell
cd c:\Users\anish\Desktop\project
docker compose up -d
# or: scripts\start_searxng.bat
```

Test: http://127.0.0.1:8080 — Phase 1/2 use it when ddgs returns few results.

**Workers (5):** `docker-compose.yml` sets `GRANIAN_WORKERS=5` (current image uses Granian, not uWSGI). After `docker compose up -d`, verify:

```powershell
docker exec vendor-intel-searxng ps aux
```

You should see `searxng worker-1` through `worker-5` (plus the main process).

**No Docker?** Add a free **Brave Search API** key (best) or **Serper** key — see `env.live.template`.

### Preflight check

```powershell
.venv\Scripts\python.exe scripts\preflight_search.py
```

### Copy live `.env` template

```powershell
# Merge env.live.template into .env and fill PASTE_* lines
notepad env.live.template
```

---

## Step 4 — SearXNG backup (optional, recommended)

If DuckDuckGo returns few results, the pipeline tries SearXNG.

**Docker:**

```powershell
docker run -d -p 8080:8080 --name searxng searxng/searxng
```

Test: open http://127.0.0.1:8080 in a browser.

If you skip Docker, live mode still works with DuckDuckGo only.

---

## Step 5 — Website scraping (no key)

```env
WEB_FETCH_ENABLED=true
WIKIDATA_ENABLED=true
```

No login. The pipeline fetches company websites over HTTP.

---

## Step 6 — Google Alerts (optional, no API key)

Two ways to feed articles into the pipeline (both write `data/alerts/articles.json`).

### Option A — RSS feeds (recommended)

1. Open https://www.google.com/alerts and create alerts (e.g. `laptop companies India`, `HP India news`).
2. For each alert, click the **RSS** icon and copy the feed URL (`https://www.google.com/alerts/feeds/...`).
3. In `.env`:

```env
GOOGLE_ALERTS_ENABLED=true
GOOGLE_ALERTS_RSS_URLS=https://www.google.com/alerts/feeds/xxx/yyy,https://www.google.com/alerts/feeds/aaa/bbb
```

4. Refresh articles (no browser needed):

```powershell
.venv\Scripts\python.exe scripts\run_alerts_worker.py --no-browser
```

### Option B — Chrome + Selenium (auto-discover RSS)

Uses **your Google account** in a saved Chrome profile (one-time login).

```env
GOOGLE_ALERTS_ENABLED=true
GOOGLE_ALERTS_PROFILE_PATH=data/chrome-profile
GOOGLE_ALERTS_HEADLESS=false
```

**First time only** — browser opens; sign in and create alerts at https://www.google.com/alerts:

```powershell
.venv\Scripts\python.exe scripts\run_alerts_worker.py
```

**Before each pipeline run** (or daily):

```powershell
.venv\Scripts\python.exe scripts\run_alerts_worker.py
```

Set `GOOGLE_ALERTS_HEADLESS=true` after login works once.

You can combine **A + B**: set `GOOGLE_ALERTS_RSS_URLS` and run the worker without `--no-browser` so Selenium also discovers any new RSS links on your account.

---

## Step 6b — Test Phase 1 only

```powershell
.venv\Scripts\python.exe run_phase1.py --live "YOUR QUERY HERE"
```

Check `output/phase1/phase1_plan_*.json` — `geographies` must match your query (e.g. Canada, not a default country).

---

## Step 7 — Run live

```powershell
cd c:\Users\anish\Desktop\project
.venv\Scripts\python.exe run_cli.py --live "Give me the best laptop companies in India"
```

Or with `.env` already having `USE_MOCK_DATA=false`:

```powershell
.venv\Scripts\python.exe run_cli.py "Give me the best laptop companies in India"
```

**Expect:** 5–20+ minutes (many searches + page fetches per company).

---

## How to confirm it's really live

| Check | Live | Mock |
|-------|------|------|
| Banner says | `LIVE` | `MOCK (demo)` |
| `company_list.csv` URLs | Real sites (dell.com, hp.com, …) | `example-mock.com` |
| Summary | From Claude, not "Mock mode for:" | "Mock mode for: …" |
| `inclusion_sources` | Real news/search URLs | example.com URLs |

---

## Mock vs live flags

| Command / setting | Mode |
|-------------------|------|
| `USE_MOCK_DATA=true` in `.env` | Mock |
| `USE_MOCK_DATA=false` + API key | Live |
| `python run_cli.py --mock "..."` | Mock (forced) |
| `python run_cli.py --live "..."` | Live (forced) |

---

## What was moved out of live code

All hardcoded demo companies and fake URLs are in:

`src/vendor_intel/mock/fixtures.py`

Live pipeline never reads that file unless mock is enabled.

---

## Troubleshooting

| Error | Fix |
|-------|-----|
| `ANTHROPIC_API_KEY is missing` | Add key to `.env`, use `--live` |
| `duckduckgo-search not installed` | `pip install duckduckgo-search` |
| Very few companies | Start SearXNG; broaden query |
| Slow run | Normal for live; reduce `MAX_VALIDATION_ENTITIES` in `.env` |
| Google Alerts empty | Run `run_alerts_worker.py` after logging in |
