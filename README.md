# Vendor Intelligence Pipeline

Turn one natural-language market question into a **validated company list**, **parent group list**, and **spreadsheet exports** — with evidence for why each company appears.

**Project folder:** `c:\Users\anish\Desktop\project`

> **Python package:** [`src/vendor_intel/`](src/vendor_intel/) — entry points at project root: `run_cli.py`, `run_phase1.py`.

---

## Documentation map

| Document | Purpose |
|----------|---------|
| **[LOCAL_SETUP.md](LOCAL_SETUP.md)** | **Share on GitHub / run on a laptop** — Streamlit (no Node) or Web UI; no GCP |
| **[PLANNING_HLD_LLD.md](PLANNING_HLD_LLD.md)** | **Master plan** — scope, phases 1–5, requirements R0–R3, **detailed implementation status**, architecture |
| **[PROJECT_HANDOFF.md](PROJECT_HANDOFF.md)** | Handoff — Phase 1 JSON field guide, fixes log, next steps |
| **[LIVE_SETUP.md](LIVE_SETUP.md)** | API keys, SearXNG, Google Alerts, live vs mock |
| **This README** | Quick start, commands, what works today |

---

## What this project does

You ask in plain English, for example:

> *"Leading pharmaceutical companies in India"*

The system can:

| Stage | What happens |
|-------|----------------|
| **Understand** | One LLM call (or regex fallback) → market, geography, `search_topic`, competitor intent |
| **Plan searches** | Funnel L0–L2 + up to 9 discovery prompts (including **competitor** angles) |
| **Discover** | DuckDuckGo (+ optional SearXNG) → company names and URLs |
| **Validate** | Five gates using search, website text, news/Alerts |
| **Classify** | Company type (manufacturer, distributor, …) + parent-brand rules |
| **Explain** | `inclusion_reason`, `inclusion_sources`, `funnel_levels_seen` |
| **Export** | Four CSV files per full run |

### Final outputs (full pipeline — `run_cli.py`)

```text
output/{run_id}_{query_slug}/
├── company_list.csv
├── parent_group_list.csv
├── suppressed_brands.csv
└── run_summary.csv
```

### Phase 1 only (`run_phase1.py`)

Produces a **JSON plan** — no company CSV yet:

```text
output/phase1/phase1_plan_<slug>.json
```

Use Phase 1 to verify geography, prompts, and search quality **before** spending time on a full live run.

---

## What is done vs what remains

| Area | Status | Notes |
|------|--------|-------|
| **Phase 1** — query plan + search smoke test | **Done** | Generic geo/prompts; competitors; adaptive filters |
| **Phase 2** — discovery | **Done** | Funnel + discovery + widen; uses `search_topic` |
| **Phase 3** — validation gates | **Done** | `run_phase3.py --from-discovery` (no re-discovery) |
| **Phase 4** — type, attribution, CSV | **Done** | R2/R3 columns in export |
| **Phase 5** — formal test (Days 4–5) | **Not started** | Checklist in [PLANNING_HLD_LLD.md](PLANNING_HLD_LLD.md) |
| **Google Alerts worker** | **Done** | Needs manual setup + periodic run |
| **SearXNG backup** | **Optional** | Docker; often not running |
| **Unit tests** | **Partial** | `tests/test_query_intent.py` (10 tests) |

**Full detail:** [PLANNING_HLD_LLD.md §7–8](PLANNING_HLD_LLD.md) (implementation tables + changelog).

---

## 5-day plan (summary)

| Period | Days | Work |
|--------|------|------|
| **Build** | **1 · 2 · 3** | Phases 1–4 — all development |
| **Test** | **4 · 5** | Phase 5 only — no new features |

| Phase | Name | CLI |
|-------|------|-----|
| 1 | Foundation & free search (plan + smoke test) | `run_phase1.py` |
| 2 | Discovery | `run_phase2.py` or `run_cli.py` |
| 3 | Validation + enrichment + Alerts | `run_phase3.py --from-discovery` or `run_cli.py` |
| 4 | Type, sources, export | `run_cli.py` (stages + CSV) |
| 5 | Test & sign-off | Manual QA |

---

## End-to-end flow

```text
User query
  → Query compile (1 LLM call or regex fallback)
  → Funnel L0–L2 + discovery P1–P9 (competitor prompts included)
  → Discovery search (DDG / SearXNG)
  → Entity graph (dedupe, domains)
  → Validation (5 gates)
  → Company type + attribution
  → Brand classifier (parent groups)
  → CSV export + quality warnings
```

### Funnel levels (R1)

| Level | Purpose |
|-------|---------|
| **L0** | Broad universe — companies in market |
| **L1** | Manufacturers / suppliers / OEM angle |
| **L2** | Competitors / leaders |
| **L3** | Per-company proof — site scrape + news/Alerts in validation |

### Export columns (R2 + R3 — implemented)

| Column | Meaning |
|--------|---------|
| `company_type` | Manufacturer, distributor, retailer, … |
| `inclusion_reason` | Plain-language why it qualified |
| `inclusion_sources` | Discovery + validation + scrape URLs |
| `funnel_levels_seen` | Which L0–L2 prompts surfaced the name |
| `evidence_urls` | Gate proof links |

---

## Prerequisites

1. **Python 3.11+** — https://www.python.org/downloads/ (check **Add Python to PATH**)
2. Verify: `python --version`

---

## Run on a laptop (recommended for teammates)

No GCP deploy needed. Same app code, files under `output/` on the PC.

1. Copy `.env.local.example` → `.env` and paste an LLM API key  
2. Double-click **`START_STREAMLIT.bat`** → http://127.0.0.1:8501  

Optional newer UI (needs Node once): **`START_WEB.bat`** → http://127.0.0.1:8080  

**Cloud files on laptops:** by default they do **not** see production GCS — each PC is local-only. Details + how you should test before sharing: **[LOCAL_SETUP.md](LOCAL_SETUP.md)**.

---

## Quick start (mock — no API keys)

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
```

Or double-click `setup.bat` / `setup_local.bat`.

**Run mock pipeline:**

```powershell
.venv\Scripts\python.exe run_cli.py --mock "Give me the best laptop companies in India"
```

---

## Phase 1 — query plan + search smoke test (recommended first)

Validates scope, prompts, and DuckDuckGo before a full run.

```powershell
cd c:\Users\anish\Desktop\project
.venv\Scripts\python.exe run_phase1.py --live "leading pet food brands in USA"
```

**Output:** `output/phase1/phase1_plan_*.json`

| JSON section | Meaning |
|--------------|---------|
| `scope.market` | Full interpreted market phrase |
| `scope.search_topic` | Short phrase for search + filters |
| `scope.geographies` | e.g. `["Kenya"]`, `["Assam, India"]` |
| `scope.anchor_company` | If query names a competitor anchor |
| `scope_source` | `llm` or `regex_fallback` |
| `funnel_prompts` | L0, L1, L2 |
| `discovery_prompts` | P1–P9 (competitor prompts first) |
| `search_smoke_test` | Per-prompt `result_count` + 3 sample URLs |

**Checks:**

- Terminal: `Scope source: llm` (best) or `regex_fallback` (LLM failed — still usable).
- Smoke test: non-zero `result_count` and relevant samples (not dictionaries/social junk).
- If all counts are 0 → network/DNS issue, not always a logic bug.

**Unit tests:**

```powershell
.venv\Scripts\python.exe -m unittest tests.test_query_intent -v
```

---

## Phase 2 — discovery + website scrape

Runs all funnel + discovery searches, dedupes candidates, tags `funnel_levels_seen`, and optionally scrapes top company sites.

```powershell
# Recommended: reuse your Phase 1 plan (no extra LLM call)
.venv\Scripts\python.exe run_phase2.py --live --from-plan output\phase1\phase1_plan_pharmaceutical_companies_india.json

# Or compile fresh from query
.venv\Scripts\python.exe run_phase2.py --live "top pharmaceutical companies in India"

# Skip website fetch (search only)
.venv\Scripts\python.exe run_phase2.py --live --from-plan output\phase1\phase1_plan_pharmaceutical_companies_india.json --no-scrape
```

**Output:** `output/phase2/phase2_discovery_<slug>.json` (candidates + stats; full hits file if &gt;250 raw hits).

---

## Phase 3 — validation gates (from Phase 2)

Runs **5 gates** (operational, geography, product, activity, M&A) on Phase 2 candidates. Does **not** re-run discovery.

```powershell
.venv\Scripts\python.exe run_phase3.py --live --from-discovery output\phase2\phase2_discovery_pharmaceutical_india.json
```

**Output:** `output/phase3/phase3_validation_<slug>.json` — tiers A/B/C, gate pass/fail, evidence URLs.

**Note:** Validates up to `MAX_VALIDATION_ENTITIES` (default 35) companies per run; uses extra search + news per entity.

---

## Full pipeline (live)

See **[LIVE_SETUP.md](LIVE_SETUP.md)** for `.env` keys (OpenCode, Anthropic, SearXNG, Alerts).

```powershell
copy .env.example .env
# Edit: USE_MOCK_DATA=false, LLM_PROVIDER, API keys
.venv\Scripts\python.exe run_cli.py --live "Give me the best laptop companies in India"
```

**Cost model (live):** 1 LLM call per run + free search/scrape. No paid SerpAPI/Firecrawl in design.

---

## Example queries

| Goal | Command |
|------|---------|
| Phase 1 plan only | `run_phase1.py --live "Eri silk weavers suppliers in Assam, India"` |
| Phase 3 validation | `run_phase3.py --live --from-discovery output\phase2\phase2_discovery_pharmaceutical_india.json` |
| Full live run | `run_cli.py --live "pharmaceutical companies in India"` |
| Competitors of a brand | `run_cli.py --live "competitors of Xiaomi in India smartphone market"` |
| Mock demo | `run_cli.py --mock "..."` |
| Full JSON to stdout | add `--json` |

**Niche queries tested in Phase 1** (see `output/phase1/`): wasabi Shizuoka, Eri silk Assam, Kenya TVWS broadband, Iceland data center cooling, kelp harvesting Nova Scotia, pet food USA, pharma India.

---

## Live stack (free-first)

| Service | Role |
|---------|------|
| DuckDuckGo (`ddgs`) | Primary search |
| SearXNG | Backup (Docker `8080`) |
| LLM (OpenCode / Anthropic / Gemini / Groq) | Query understanding — **1 call/run** |
| Wikidata + web fetch | Parents + site text |
| Google Alerts worker | Article freshness (optional) |

**`.env` essentials (live):**

```env
USE_MOCK_DATA=false
LLM_PROVIDER=opencode
OPENCODE_API_KEY=your_key
SEARCH_PRIMARY=duckduckgo
SEARCH_BACKUP=searxng
SEARXNG_BASE_URL=http://127.0.0.1:8080
WIKIDATA_ENABLED=true
WEB_FETCH_ENABLED=true
CSV_OUTPUT_ENABLED=true
```

Paid search APIs are **not** part of this project’s design.

---

## API server (optional)

```powershell
cd c:\Users\anish\Desktop\project
.venv\Scripts\activate
uvicorn vendor_intel.api:app --reload --app-dir src
```

- Health: http://127.0.0.1:8000/health  
- Docs: http://127.0.0.1:8000/docs  

**POST /v1/runs** body: `{ "query": "your question" }`

---

## Pipeline stages (implemented)

| Stage | Name | Role |
|-------|------|------|
| A | Query compiler | LLM or regex → scope + themes |
| B | Discovery | Funnel + discovery search |
| C | Entity graph | Dedupe; domains; funnel levels |
| D | Validation | Five gates; tiers A/B/C |
| — | Type + attribution | `company_type`, reason, sources |
| F | Brand classifier | Parent/sibling collapse |
| G | Output | Lists + CSV |
| I | Quality | Duplicates; min-count warnings |

---

## Project structure

```text
project/
├── README.md                 ← This file
├── PLANNING_HLD_LLD.md       ← Master plan + implementation status
├── PROJECT_HANDOFF.md        ← Handoff + Phase 1 JSON guide
├── LIVE_SETUP.md             ← Keys, Docker, Alerts
├── run_phase1.py             ← Phase 1 only
├── run_phase2.py             ← Phase 2 only
├── run_phase3.py             ← Phase 3 only (from Phase 2 JSON)
├── run_cli.py                ← Full pipeline (Phases 2–4)
├── setup.bat
├── requirements.txt
├── config/
│   ├── default.yaml
│   └── export_columns.yaml
├── output/
│   └── phase1/               ← phase1_plan_*.json
├── scripts/
│   └── run_alerts_worker.py
├── tests/
│   └── test_query_intent.py
└── src/vendor_intel/
    ├── orchestrator.py
    ├── phase1/runner.py
    ├── phase2/runner.py
    ├── stages/               ← A, B, C, D, F, G, I
    ├── funnel/               ← query_intent, prompt_builder
    ├── clients/              ← search, LLM, wikidata
    ├── classification/
    ├── attribution/
    └── export_csv.py
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `'python' is not recognized` | Reinstall Python with **Add to PATH**, or use `py -3.11` |
| `No module named vendor_intel` | Run from project root; use `run_cli.py` / `run_phase1.py` |
| LLM key missing despite `.env` | Ensure `USE_MOCK_DATA=false`; keys not `YOUR_*` placeholders |
| Phase 1 all `result_count: 0` | Check internet/DNS; see `search_status` in JSON |
| `DuckDuckGoSearchException` / DNS | Retries added; try again or start SearXNG |
| `scope_source: regex_fallback` | LLM failed — plan still works; check OpenCode model/rate limits |
| Fewer than 25 companies | Broaden query; enable live search; check Phase 1 smoke test |
| SearXNG warning | `docker run -d -p 8080:8080 searxng/searxng` or ignore if DDG enough |

---

## What you can still do (not blocked)

| Task | How |
|------|-----|
| Improve thin-market recall | Tune `search_relevance.py` or add auto-relax when global hits &lt; N |
| Run Phase 5 test matrix | [PLANNING_HLD_LLD.md §6 Phase 5](PLANNING_HLD_LLD.md) |
| Enable Alerts for activity gate | [LIVE_SETUP.md](LIVE_SETUP.md) + `run_alerts_worker.py` |
| Add more unit/e2e tests | `tests/` |
| REST integration | `vendor_intel.api` |

---

## Success criteria

1. **End of Day 3 (build):** Phases 1–4 runnable; CSV includes type, reason, sources, funnel levels.  
2. **End of Day 5 (test):** Phase 5 checklist passed; demo pack ready.

Details: [PLANNING_HLD_LLD.md](PLANNING_HLD_LLD.md)

---

## Quick reference

```powershell
# Setup (once)
cd c:\Users\anish\Desktop\project
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env

# Phase 1 plan
.venv\Scripts\python.exe run_phase1.py --live "YOUR QUERY"

# Full pipeline
.venv\Scripts\python.exe run_cli.py --live "YOUR QUERY"
```
