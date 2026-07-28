#!/bin/bash
set -euxo pipefail
IMAGE="us-central1-docker.pkg.dev/project-2ab6c3f5-86a7-4aa2-a59/vendor-intel/app:vm-test"
NAME="vendor-intel"

# Auth for Artifact Registry
if command -v gcloud >/dev/null 2>&1; then
  gcloud auth configure-docker us-central1-docker.pkg.dev -q || true
fi

docker pull "$IMAGE"

# Preserve env from existing container if present
ENV_FILE=/tmp/vendor-intel.env
if docker inspect "$NAME" >/dev/null 2>&1; then
  docker inspect "$NAME" --format '{{range .Config.Env}}{{println .}}{{end}}' > "$ENV_FILE" || true
  docker stop "$NAME" || true
  docker rm "$NAME" || true
else
  cat > "$ENV_FILE" <<'EOF'
PORT=8080
USE_MOCK_DATA=false
WEB_FETCH_ENABLED=true
SELENIUM_HEADLESS=true
CHROME_BINARY_PATH=/usr/bin/google-chrome-stable
LLM_PROVIDER=deepseek
DEEPSEEK_MODEL=deepseek-chat
AUTH_ALLOWED_EMAIL_DOMAINS=coherentmarketinsights.com
AUTH_EMAIL_BACKEND=console
AUTH_SKIP_OTP=true
AUTH_APP_NAME=Vendor Intelligence
JWT_ALGORITHM=HS256
AUTH_SESSION_HOURS=24
GCS_BUCKET=vendor-intel-runs-488586803367
MARKET_QUERY_OUTPUT_DIR=output/demo
SEARCH_BACKUP=searxng
SEARXNG_BASE_URL=http://172.17.0.1:8081
EOF
fi

# Ensure GCS_BUCKET and SearXNG URL are set for VM testing
grep -q '^GCS_BUCKET=' "$ENV_FILE" || echo 'GCS_BUCKET=vendor-intel-runs-488586803367' >> "$ENV_FILE"
# Prefer host SearXNG if we start it on 8081
sed -i '/^SEARXNG_BASE_URL=/d' "$ENV_FILE" || true
echo 'SEARXNG_BASE_URL=http://172.17.0.1:8081' >> "$ENV_FILE"

# Start lightweight SearXNG on host port 8081 if not running
if ! docker ps --format '{{.Names}}' | grep -qx searxng; then
  docker rm -f searxng 2>/dev/null || true
  docker run -d --name searxng --restart unless-stopped \
    -p 8081:8080 \
    -e SEARXNG_BASE_URL=http://127.0.0.1:8081/ \
    searxng/searxng:latest || true
fi

docker run -d --name "$NAME" --restart unless-stopped \
  -p 8080:8080 \
  --env-file "$ENV_FILE" \
  "$IMAGE"

sleep 5
curl -s -o /dev/null -w "health=%{http_code}\n" http://127.0.0.1:8080/_stcore/health || true
docker ps --format '{{.Names}} {{.Status}} {{.Ports}}'
echo DONE
