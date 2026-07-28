#!/bin/bash
set -euxo pipefail
WORKDIR=/tmp/vi-code
rm -rf "$WORKDIR"
mkdir -p "$WORKDIR"
tar -xzf /tmp/vendor-intel-code.tgz -C "$WORKDIR"
cd "$WORKDIR"

BASE=us-central1-docker.pkg.dev/project-2ab6c3f5-86a7-4aa2-a59/vendor-intel/app:latest
gcloud auth configure-docker us-central1-docker.pkg.dev -q || true
docker pull "$BASE"

docker build -f Dockerfile.code-update -t vendor-intel:vm-test .

ENV_FILE=/tmp/vendor-intel.env
if docker inspect vendor-intel >/dev/null 2>&1; then
  docker inspect vendor-intel --format '{{range .Config.Env}}{{println .}}{{end}}' > "$ENV_FILE"
  docker stop vendor-intel || true
  docker rm vendor-intel || true
else
  printf '%s\n' \
    'PORT=8080' 'USE_MOCK_DATA=false' 'WEB_FETCH_ENABLED=true' 'SELENIUM_HEADLESS=true' \
    'CHROME_BINARY_PATH=/usr/bin/google-chrome-stable' 'LLM_PROVIDER=deepseek' \
    'DEEPSEEK_MODEL=deepseek-chat' 'AUTH_ALLOWED_EMAIL_DOMAINS=coherentmarketinsights.com' \
    'AUTH_EMAIL_BACKEND=console' 'AUTH_SKIP_OTP=true' 'AUTH_APP_NAME=Vendor Intelligence' \
    'JWT_ALGORITHM=HS256' 'AUTH_SESSION_HOURS=24' \
    'GCS_BUCKET=vendor-intel-runs-488586803367' 'MARKET_QUERY_OUTPUT_DIR=output/demo' \
    > "$ENV_FILE"
fi

grep -q '^GCS_BUCKET=' "$ENV_FILE" || echo 'GCS_BUCKET=vendor-intel-runs-488586803367' >> "$ENV_FILE"
sed -i '/^SEARXNG_BASE_URL=/d' "$ENV_FILE" || true
echo 'SEARXNG_BASE_URL=http://172.17.0.1:8081' >> "$ENV_FILE"
sed -i '/^SEARCH_BACKUP=/d' "$ENV_FILE" || true
echo 'SEARCH_BACKUP=searxng' >> "$ENV_FILE"

if ! docker ps --format '{{.Names}}' | grep -qx searxng; then
  docker rm -f searxng 2>/dev/null || true
  docker pull searxng/searxng:latest
  docker run -d --name searxng --restart unless-stopped -p 8081:8080 searxng/searxng:latest || true
fi

docker run -d --name vendor-intel --restart unless-stopped \
  -p 8080:8080 --env-file "$ENV_FILE" vendor-intel:vm-test

for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
  code=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/_stcore/health || true)
  echo "try $i health=$code"
  [ "$code" = "200" ] && break
  sleep 3
done
docker ps --format '{{.Names}} {{.Status}} {{.Image}} {{.Ports}}'
docker run --rm --entrypoint grep vendor-intel:vm-test -n "How many companies\|_wiz_leave_step3" /app/app.py | head -20
echo DONE
