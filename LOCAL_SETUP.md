# Vendor Intelligence — run on your laptop (no Cloud Run deploy)

Both UIs use the **same current project code** (pipeline + auth):

| File | UI | Needs |
|------|-----|--------|
| **`START_STREAMLIT.bat`** | Streamlit (classic) | Python 3.11+ only |
| **`START_WEB.bat`** | Next.js + FastAPI (same as prod look) | Python 3.11+ **and** Node 20+ once |

**No GCP deploy is required** to use these. Runs stay on the laptop unless you intentionally turn cloud storage on (see below).

---

## Before you give this to the team (you test first)

### 1) One-time on your PC
1. Install **Python 3.11+** (tick **Add to PATH**).
2. Install **Chrome** (recommended).
3. Optional for Web UI: **Node.js 20+** from https://nodejs.org  
4. Open folder: `C:\project-main` (or wherever the repo lives).

### 2) Local env (important)
If you already have a prod-style `.env` with `GCS_BUCKET=...`, either:

- **Option A (recommended for team handoff):**  
  `copy /Y .env.local.example .env`  
  then paste your LLM API key into `.env`

- **Option B:** keep your `.env` but **comment out / delete** the `GCS_BUCKET=...` line so the laptop stays fully local.

### 3) Test Streamlit (no Node)
1. Double-click **`START_STREAMLIT.bat`**
2. Wait for packages (first run only).
3. Open **http://127.0.0.1:8501**
4. Login: `yourname@coherentmarketinsights.com`
5. Start a small **Focused** run, confirm progress + download files under `output/`
6. Stop with **Ctrl+C** in the black window

### 4) Test Web UI (optional, needs Node)
1. Double-click **`START_WEB.bat`**
2. First run builds frontend (`npm install` + `npm run build`) — can take several minutes
3. Open **http://127.0.0.1:8080**
4. Same login + a short Focused run
5. Stop with **Ctrl+C**

If Node is missing, the script tells you to use Streamlit instead — that’s expected.

---

## Cloud storage (GCS) — what happens on local PCs?

| Mode | What teammates see |
|------|---------------------|
| **Default (recommended)** — `GCS_BUCKET` **not set** | **Cloud files does not pull from Google Cloud.** Each laptop keeps its own runs in the local `output/` folder. No GCP account needed. No shared cloud bill. |
| **Optional** — set `GCS_BUCKET=vendor-intel-runs-488586803367` **and** Google credentials (`gcloud auth application-default login`) | Laptop **can** list/fetch the **same** Cloud files as production. Needs GCP access; not for “leave the cloud” handoff. |

So for normal team local use: **they will NOT automatically see production Cloud Storage.**  
Prod Cloud Run keeps using GCS; laptops are separate unless someone opts in.

---

## Prerequisites (remind the team)

**Required for Streamlit bat**
- Windows
- Python 3.11+
- Internet
- One LLM API key

**Recommended**
- Google Chrome

**Not required**
- Node.js (Streamlit path)
- Postgres / SQL Server
- Docker
- Google Cloud / gcloud

**Only for `START_WEB.bat`**
- Node.js 20+

---

## What stays local vs cloud (default)

| Production (Cloud Run) | Laptop (these bats) |
|------------------------|---------------------|
| Cloud Run instances | Your PC |
| Cloud SQL | SQLite `data/vendor_intel_auth.db` |
| GCS bucket | Local folder `output/` |
| Shared Cloud files | Per-laptop files only |

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Python not found | Reinstall 3.11+ with PATH checked |
| Still says PASTE_YOUR_KEY | Edit `.env`, put real key |
| Login domain error | Email must end with `@coherentmarketinsights.com` |
| Cloud files empty locally | Expected if `GCS_BUCKET` unset |
| Port 8501 / 8080 busy | Close other app window |
| No Node | Use `START_STREAMLIT.bat` |

---

## Files

| File | Purpose |
|------|---------|
| `LOCAL_SETUP.md` | This guide |
| `.env.local.example` | Laptop defaults (SQLite, **no GCS**) |
| `setup_local.bat` | venv + pip + auth DB |
| `START_STREAMLIT.bat` | Streamlit UI |
| `START_WEB.bat` | Web UI (prod-style) |
| `scripts/start_streamlit.sh` | Mac/Linux Streamlit |
