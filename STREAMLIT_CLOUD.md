# Streamlit Community Cloud — deploy guide
#
# IMPORTANT limits on free Community Cloud:
# - No Docker (no local SearXNG / local Postgres)
# - Website scrape (WEB_FETCH_ENABLED=true) needs Chrome on the host — may need packages.txt
#   or a non-free host if Selenium fails on Community Cloud
# - Long 25–40 min runs may hit resource/timeout limits; prefer lighter caps for demos
# - You need a HOSTED Postgres (Neon / Supabase free tier) for login OTP + JWT
#
# -----------------------------------------------------------------------------
# 1) Push code to GitHub
# -----------------------------------------------------------------------------
# - Commit app.py, requirements.txt, src/, ui/, queries/, config/, .streamlit/config.toml
# - NEVER commit .env or .streamlit/secrets.toml
# - Note: queries/seeds/ is gitignored — either remove that ignore for deploy-needed
#   seed files, or rely on discovery without curated seeds
#
# -----------------------------------------------------------------------------
# 2) Create a free hosted Postgres
# -----------------------------------------------------------------------------
# Neon: https://neon.tech  → New project → copy connection string
# Example:
#   postgresql+psycopg://USER:PASSWORD@HOST/neondb?sslmode=require
#
# After first deploy (or locally with that DATABASE_URL):
#   python scripts/init_auth_db.py
#
# -----------------------------------------------------------------------------
# 3) Deploy on Streamlit Cloud
# -----------------------------------------------------------------------------
# 1. Go to https://share.streamlit.io  (sign in with GitHub)
# 2. New app → select this repo
# 3. Main file path:  app.py
# 4. Python version:  3.11 or 3.12 (prefer 3.11)
# 5. Advanced settings → Secrets → paste secrets (see secrets.toml.example)
# 6. Deploy
#
# -----------------------------------------------------------------------------
# 4) Secrets to paste (TOML) — copy from .streamlit/secrets.toml.example
# -----------------------------------------------------------------------------
# Minimum:
#   USE_MOCK_DATA, LLM_PROVIDER + API key, DATABASE_URL, JWT_SECRET,
#   AUTH_ALLOWED_EMAIL_DOMAINS, AUTH_EMAIL_BACKEND (use smtp or resend on cloud —
#   console OTP only appears in Cloud logs, not user email)
#
# For real OTP emails on Cloud set:
#   AUTH_EMAIL_BACKEND = "resend"
#   RESEND_API_KEY = "re_..."
#   SMTP_FROM = "noreply@coherentmarketinsights.com"
#
# -----------------------------------------------------------------------------
# 5) After first boot
# -----------------------------------------------------------------------------
# - Open the app URL → Sign in with @coherentmarketinsights.com
# - If tables missing, run init_auth_db.py once against the same DATABASE_URL
#   (from your laptop with that URL in .env), or the app may create tables via init_db()
# - Auth init_db() runs on first login screen load
#
# -----------------------------------------------------------------------------
# Recommended .env / secrets flags
# -----------------------------------------------------------------------------
# USE_MOCK_DATA = "false"
# WEB_FETCH_ENABLED = "true"          # company sites are scraped
# MARKET_QUERY_OUTPUT_DIR = "output/demo"
# AUTH_EMAIL_BACKEND = "resend"       # not console for real users
