# Deploy Vendor Intelligence on Google Cloud Run

Complete Docker image + YAML for Cloud Run. Quality needs: **Chrome scrape on**, **Postgres (Cloud SQL)**, optional **SearXNG**, long timeout, **CPU always allocated**, **concurrency = 1**.

---

## Architecture (Cloud Run)

Cloud Run runs **one container per service**. Do not put Postgres inside the app image.

```
[Browser] → Cloud Run: vendor-intel (this Dockerfile / Streamlit + Chrome)
                │
                ├── Cloud SQL Postgres  (DATABASE_URL)
                ├── LLM APIs            (ANTHROPIC_API_KEY, …)
                └── Cloud Run/VM: SearXNG  (SEARXNG_BASE_URL)  ← optional but recommended
```

| Local Compose | Cloud Run |
|---------------|-----------|
| `app` service | Cloud Run service `vendor-intel` |
| `postgres` | **Cloud SQL** Postgres |
| `searxng` | Second Cloud Run service **or** small VM |

---

## Files added

| File | Purpose |
|------|---------|
| `Dockerfile` | Full app image (Python 3.11 + Chrome + Streamlit) |
| `docker/entrypoint.sh` | DB init + Streamlit on `$PORT` |
| `docker-compose.yml` | Local full stack: app + Postgres + SearXNG |
| `.dockerignore` | Smaller / safer builds |
| `cloudbuild.yaml` | Build & push to Artifact Registry |
| `deploy/cloudrun/service.yaml` | App service template |
| `deploy/cloudrun/searxng.yaml` | Optional SearXNG service |

---

## 0) Local test of the image (before Cloud)

```bash
# From project root — needs a filled .env
docker compose up -d --build
```

Open http://localhost:8501 — login, run one market, confirm scrape works.

```bash
docker compose logs -f app
docker compose down
```

Build only:

```bash
docker build -t vendor-intel:latest .
```

---

## 1) GCP project prep

```bash
export PROJECT_ID=your-gcp-project
export REGION=asia-south1
export REPO=vendor-intel

gcloud config set project $PROJECT_ID
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  sqladmin.googleapis.com \
  secretmanager.googleapis.com

gcloud artifacts repositories create $REPO \
  --repository-format=docker \
  --location=$REGION \
  --description="Vendor Intelligence"
```

---

## 2) Cloud SQL Postgres

```bash
gcloud sql instances create vendor-intel-pg \
  --database-version=POSTGRES_16 \
  --tier=db-custom-1-3840 \
  --region=$REGION \
  --root-password=GENERATE_A_STRONG_PASSWORD

gcloud sql databases create vendor_intel --instance=vendor-intel-pg
gcloud sql users create vendor --instance=vendor-intel-pg --password=GENERATE_A_STRONG_PASSWORD
```

Connection name:

```bash
gcloud sql instances describe vendor-intel-pg --format='value(connectionName)'
# → PROJECT_ID:REGION:vendor-intel-pg
```

`DATABASE_URL` for Cloud Run (Unix socket via Cloud SQL):

```text
postgresql+psycopg://vendor:PASSWORD@/vendor_intel?host=/cloudsql/PROJECT_ID:REGION:vendor-intel-pg
```

---

## 3) Secrets

```bash
echo -n 'postgresql+psycopg://vendor:PASSWORD@/vendor_intel?host=/cloudsql/PROJECT_ID:REGION:vendor-intel-pg' \
  | gcloud secrets create DATABASE_URL --data-file=-

echo -n 'your-long-jwt-secret' | gcloud secrets create JWT_SECRET --data-file=-
echo -n 'sk-ant-...' | gcloud secrets create ANTHROPIC_API_KEY --data-file=-
echo -n 're_...' | gcloud secrets create RESEND_API_KEY --data-file=-
```

Grant the Cloud Run runtime service account access to these secrets and Cloud SQL Client.

---

## 4) Build & push image

```bash
gcloud builds submit --config=cloudbuild.yaml \
  --substitutions=_REGION=$REGION,_REPO=$REPO
```

Image:

`REGION-docker.pkg.dev/PROJECT_ID/vendor-intel/app:latest`

---

## 5) Deploy app to Cloud Run

```bash
export IMAGE=$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/app:latest
export CLOUDSQL=$PROJECT_ID:$REGION:vendor-intel-pg

gcloud run deploy vendor-intel \
  --image="$IMAGE" \
  --region="$REGION" \
  --platform=managed \
  --allow-unauthenticated=false \
  --port=8080 \
  --cpu=2 \
  --memory=4Gi \
  --timeout=3600 \
  --concurrency=1 \
  --min-instances=1 \
  --max-instances=3 \
  --session-affinity \
  --no-cpu-throttling \
  --execution-environment=gen2 \
  --add-cloudsql-instances="$CLOUDSQL" \
  --set-env-vars="USE_MOCK_DATA=false,WEB_FETCH_ENABLED=true,SELENIUM_HEADLESS=true,CHROME_BINARY_PATH=/usr/bin/google-chrome-stable,SEARCH_BACKUP=searxng,LLM_PROVIDER=anthropic,AUTH_ALLOWED_EMAIL_DOMAINS=coherentmarketinsights.com,AUTH_EMAIL_BACKEND=resend,AUTH_APP_NAME=Vendor Intelligence,MARKET_QUERY_OUTPUT_DIR=output/demo,JWT_ALGORITHM=HS256,AUTH_SESSION_HOURS=24,AUTH_SKIP_OTP=true,GCS_BUCKET=YOUR_RUNS_BUCKET" \
  --set-secrets="DATABASE_URL=DATABASE_URL:latest,JWT_SECRET=JWT_SECRET:latest,ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest,RESEND_API_KEY=RESEND_API_KEY:latest"
```

Notes:
- `--session-affinity` keeps each browser on the same instance (required for long Streamlit runs + in-memory job state).
- `GCS_BUCKET` makes Excel/Word + search history survive instance restarts.
- `AUTH_SKIP_OTP=true` = work-email login only (until company SMTP is ready).

Then grant your team access (IAP or `allAuthenticatedUsers` / organization accounts) as per CMI policy.

Or edit placeholders in `deploy/cloudrun/service.yaml` and:

```bash
gcloud run services replace deploy/cloudrun/service.yaml --region=$REGION
```

---

## 6) Optional: SearXNG on Cloud Run

```bash
gcloud run deploy vendor-intel-searxng \
  --image=searxng/searxng:latest \
  --region=$REGION \
  --port=8080 \
  --cpu=1 \
  --memory=1Gi \
  --min-instances=1 \
  --no-cpu-throttling \
  --allow-unauthenticated=false
```

Get URL and set on the app:

```bash
export SEARX_URL=$(gcloud run services describe vendor-intel-searxng --region=$REGION --format='value(status.url)')

gcloud run services update vendor-intel \
  --region=$REGION \
  --update-env-vars="SEARXNG_BASE_URL=$SEARX_URL"
```

If SearXNG on Cloud Run is flaky, run SearXNG on a small VM and point `SEARXNG_BASE_URL` there (often better for search quality).

---

## 7) Quality settings (do not weaken)

Keep on Cloud Run:

- `WEB_FETCH_ENABLED=true` (Chrome is in the image)
- `--timeout=3600`, `--no-cpu-throttling`, `--min-instances=1`
- `--concurrency=1` (Streamlit + Selenium are process-local)
- Real Postgres (Cloud SQL), real OTP email (`resend` / SMTP)
- Same LLM keys/models as local

Outputs live in the container filesystem (`output/demo`) — they reset when the instance is replaced. Downloads via the UI during the session; for durable files later add a GCS mount/bucket.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Cold start / session dies | `--min-instances=1` + `--no-cpu-throttling` |
| Chrome/scrape crash | Ensure image built from this Dockerfile; `shm` is limited on Cloud Run — scrape may be slower; 4Gi memory helps |
| Auth DB connection | Cloud SQL instance annotation + socket `DATABASE_URL` format above |
| Request timeout mid-run | `--timeout=3600` (Cloud Run max) + `--session-affinity` |
| Mid-run “logged out” / lost progress | Sticky sessions + auth token kept in URL (`?s=`) + Streamlit `disconnectedSessionTTL`; reopen finished work from **Search history** |
| Multiple users interfere | `--concurrency=1` and scale instances; avoid two heavy runs on one instance |
| Lost Excel/Word after refresh | Set `GCS_BUCKET` (signed links, max 7 days) + Search history panel |

---

## Production scaling schedule (live)

| Setting | Value |
|---------|--------|
| **Max instances** | **10** |
| **Mon–Sat** | **min = 3** from **08:00–23:00** IST, then **min = 1** overnight |
| **Sunday** | **min = 1** all day |
| Scheduler | `vendor-intel-min-day` (08:00 → 3), `vendor-intel-min-night` (23:00 → 1) |

Prod URL: https://vendor-intel-6zevitkldq-uc.a.run.app (Next.js). No Find free server.
