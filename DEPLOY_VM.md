# Deploy on a Linux VM (same quality as local)

Use this when you need the research team to use a Streamlit URL **without** dropping scrape / search / long-run quality.  
Do **not** use free Streamlit Community Cloud for this path.

Prefer **Google Cloud Run** with the Docker image? See `CLOUD_RUN.md` + `Dockerfile` (Cloud SQL for Postgres; Compose for local full stack).

Researchers only open the URL. They do not need the repo or this doc.

---

## What you will run on the VM

| Piece | How |
|--------|-----|
| App | `streamlit run app.py` |
| Postgres + SearXNG | `docker compose up -d` |
| Chrome | system package (for `WEB_FETCH_ENABLED=true`) |
| Config | same `.env` flags as your laptop |
| OTP email | Resend or SMTP (not `console`) |

Suggested VM size: **4 GB RAM / 2 vCPU** minimum; **8 GB** preferred for broad + scrape.

Pick any always-on host: DigitalOcean Droplet, AWS EC2/Lightsail, Azure VM, GCP, or an internal CMI server. Ubuntu 22.04/24.04 works well.

---

## 1) Create the VM

1. Create an Ubuntu 22.04 or 24.04 VM (4–8 GB RAM).
2. Open inbound ports (security group / firewall):
   - **22** — SSH (your IP only if possible)
   - **8501** — Streamlit (team access; later put behind HTTPS/VPN if required)
3. SSH in:

```bash
ssh root@YOUR_VM_IP
# or: ssh ubuntu@YOUR_VM_IP
```

---

## 2) Install system packages

```bash
sudo apt-get update
sudo apt-get install -y \
  git python3.11 python3.11-venv python3-pip \
  docker.io docker-compose-v2 \
  chromium-browser chromium-chromedriver \
  curl ca-certificates
sudo usermod -aG docker "$USER"
# log out and back in so docker group applies
```

If `chromium-browser` is missing on your Ubuntu version, install Google Chrome instead:

```bash
curl -fsSL https://dl.google.com/linux/linux_signing_key.pub | sudo gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg
echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" \
  | sudo tee /etc/apt/sources.list.d/google-chrome.list
sudo apt-get update && sudo apt-get install -y google-chrome-stable
```

---

## 3) Clone the repo

```bash
cd /opt
sudo mkdir -p /opt/vendor-intel
sudo chown "$USER":"$USER" /opt/vendor-intel
cd /opt/vendor-intel
git clone YOUR_GITHUB_REPO_URL .
# or: scp/rsync from your laptop if the repo is private and not on GitHub
```

---

## 4) Start Postgres + SearXNG (same as local)

```bash
cd /opt/vendor-intel
docker compose up -d
docker compose ps
```

You should see `postgres` and `searxng` healthy/running.  
Defaults match local `.env`:

- Postgres: `postgresql+psycopg://vendor:vendor@127.0.0.1:5432/vendor_intel`
- SearXNG: `http://127.0.0.1:8080`

---

## 5) Python env + dependencies

```bash
cd /opt/vendor-intel
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 6) Configure `.env` (copy from your working laptop)

```bash
cp .env.example .env
nano .env   # or paste your working local .env and edit
```

**Must match local quality (do not weaken these):**

```env
USE_MOCK_DATA=false
WEB_FETCH_ENABLED=true
SELENIUM_HEADLESS=true
WIKIDATA_ENABLED=true
SEARCH_PRIMARY=duckduckgo
SEARCH_BACKUP=searxng
SEARXNG_BASE_URL=http://127.0.0.1:8080
SKIP_DDGS=false
SKIP_BING_HTML=false
MARKET_QUERY_OUTPUT_DIR=output/demo

LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=your-real-key
# keep the same model flags you use locally
```

**Auth (for the team):**

```env
DATABASE_URL=postgresql+psycopg://vendor:vendor@127.0.0.1:5432/vendor_intel
JWT_SECRET=paste-a-long-random-string
JWT_ALGORITHM=HS256
AUTH_SESSION_HOURS=24
AUTH_ALLOWED_EMAIL_DOMAINS=coherentmarketinsights.com
AUTH_ADMIN_EMAILS=you@coherentmarketinsights.com
AUTH_APP_NAME=Vendor Intelligence

# Real email for OTP (console only prints on the server — researchers will never see it)
AUTH_EMAIL_BACKEND=resend
RESEND_API_KEY=re_...
SMTP_FROM=noreply@coherentmarketinsights.com
```

If Chromium is not on the default path, set:

```env
CHROME_BINARY_PATH=/usr/bin/chromium-browser
# or: CHROME_BINARY_PATH=/usr/bin/google-chrome-stable
```

Create auth tables:

```bash
source .venv/bin/activate
python scripts/init_auth_db.py
```

---

## 7) First smoke test (before sharing the URL)

```bash
cd /opt/vendor-intel
source .venv/bin/activate
streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

From your laptop open: `http://YOUR_VM_IP:8501`

Checklist:

1. Login with `@coherentmarketinsights.com` — OTP arrives by email  
2. Run **one market** you already ran locally  
3. Confirm scrape runs (no “WEB_FETCH disabled” warnings in server logs)  
4. Download Excel and sanity-check coverage vs your local run  

If that looks right, quality path is good.

---

## 8) Keep Streamlit running (systemd)

Create `/etc/systemd/system/vendor-intel.service`:

```ini
[Unit]
Description=Vendor Intelligence Streamlit
After=network.target docker.service
Requires=docker.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/vendor-intel
Environment=PATH=/opt/vendor-intel/.venv/bin:/usr/bin
ExecStart=/opt/vendor-intel/.venv/bin/streamlit run app.py --server.address 0.0.0.0 --server.port 8501 --browser.gatherUsageStats=false
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Change `User=ubuntu` to your SSH user if different.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now vendor-intel
sudo systemctl status vendor-intel
```

Logs:

```bash
journalctl -u vendor-intel -f
```

Also ensure Docker services start on boot:

```bash
docker compose -f /opt/vendor-intel/docker-compose.yml up -d
sudo systemctl enable docker
```

---

## 9) Optional hardening (recommended before wide rollout)

- Put **nginx or Caddy** in front with HTTPS + domain name  
- Restrict port **8501** to office VPN / allowlisted IPs  
- Change default Postgres password in `docker-compose.yml` + `DATABASE_URL`  
- One heavy run at a time (same as local)  
- Do not hit Stop mid-run unless hung  

---

## 10) Hand over to researchers

Give them only:

1. App URL (e.g. `https://vendor-intel.yourcompany.com` or `http://IP:8501`)  
2. `RESEARCH_TEAM_GUIDE.md`  

They sign in with company email and use the wizard. No VM/SSH/repo access needed.

---

## Troubleshooting

| Symptom | Fix |
|--------|-----|
| OTP never arrives | Set `AUTH_EMAIL_BACKEND=resend` (or SMTP) and check Resend/SMTP keys; `console` only shows codes in `journalctl` |
| Scrape fails / Chrome errors | Install Chromium/Chrome; set `CHROME_BINARY_PATH`; keep `SELENIUM_HEADLESS=true` |
| Thin search results | `docker compose ps` — SearXNG must be up; `SEARXNG_BASE_URL=http://127.0.0.1:8080` |
| Auth DB errors | `docker compose up -d postgres` then `python scripts/init_auth_db.py` |
| App died after reboot | `sudo systemctl start vendor-intel` and `docker compose up -d` |

---

## Quality rule

If you ever feel tempted to turn off scrape, skip SearXNG, or move to free Streamlit Cloud to “make deploy easier,” you are choosing a **different product quality**. This VM path is the one that stays aligned with your laptop.
