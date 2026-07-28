# Vendor Intelligence — Streamlit + Chrome (Cloud Run / Compose)
# Build:  docker build -t vendor-intel:latest .
# Run:    see docker-compose.yml or deploy/cloudrun/

FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    CHROME_BINARY_PATH=/usr/bin/google-chrome-stable \
    SELENIUM_HEADLESS=true \
    WEB_FETCH_ENABLED=true \
    MARKET_QUERY_OUTPUT_DIR=output/demo

WORKDIR /app

# System deps + Google Chrome (Selenium scrape)
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      wget \
      gnupg \
      unzip \
      fonts-liberation \
      libasound2 \
      libatk-bridge2.0-0 \
      libatk1.0-0 \
      libcups2 \
      libdbus-1-3 \
      libdrm2 \
      libgbm1 \
      libgtk-3-0 \
      libnspr4 \
      libnss3 \
      libx11-xcb1 \
      libxcomposite1 \
      libxdamage1 \
      libxrandr2 \
      xdg-utils \
    && wget -q -O /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get install -y --no-install-recommends /tmp/chrome.deb \
    && rm -f /tmp/chrome.deb \
    && google-chrome-stable --version \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip \
 && pip install -r requirements.txt \
 && python -m playwright install --with-deps chromium firefox

COPY app.py run_query.py run_pipeline.py run_auth_api.py ./
COPY ui ./ui
COPY src ./src
COPY config ./config
COPY queries ./queries
COPY scripts ./scripts
COPY crawler ./crawler
COPY .streamlit ./.streamlit

COPY docker/entrypoint.sh /entrypoint.sh
RUN sed -i 's/\r$//' /entrypoint.sh \
 && chmod +x /entrypoint.sh \
 && mkdir -p /app/output/demo \
 && useradd --create-home --shell /bin/bash appuser \
 && chown -R appuser:appuser /app

USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT}/_stcore/health" || exit 1

ENTRYPOINT ["/entrypoint.sh"]
