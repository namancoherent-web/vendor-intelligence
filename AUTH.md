# Auth — email OTP login for internal research team
#
# Streamlit Community Cloud: see STREAMLIT_CLOUD.md (hosted Postgres + secrets.toml).
#
# 1) Start Postgres (+ optional SearXNG):
#      docker compose up -d postgres
#
# 2) Add to .env (see .env.example):
#      DATABASE_URL=postgresql+psycopg://vendor:vendor@127.0.0.1:5432/vendor_intel
#      AUTH_EMAIL_BACKEND=console
#      AUTH_ALLOWED_EMAIL_DOMAINS=coherentmarketinsights.com
#
#    Login email format: username@coherentmarketinsights.com
#
# 3) Install deps + create tables:
#      .venv\Scripts\python.exe -m pip install "SQLAlchemy>=2.0.36" "psycopg[binary]>=3.2.0" email-validator
#      .venv\Scripts\python.exe scripts\init_auth_db.py
#
# 4) Run Streamlit — login screen appears first:
#      .venv\Scripts\python.exe -m streamlit run app.py
#    With AUTH_EMAIL_BACKEND=console the OTP prints in the terminal.
#
# 5) Optional HTTP API:
#      .venv\Scripts\python.exe run_auth_api.py
#      → http://127.0.0.1:8001/docs
#
# Tables: users, otp_challenges, sessions, auth_events
# After OTP verify the API/UI gets a JWT (Bearer). Expiry: AUTH_SESSION_HOURS (default 24).
# Logout revokes the JWT jti in Postgres so the token cannot be reused.
# Promote admins: AUTH_ADMIN_EMAILS=you@coherentmarketinsights.com
#
# JWT:
#   JWT_SECRET=<long random string>
#   JWT_ALGORITHM=HS256
# API usage: Authorization: Bearer <access_token>
