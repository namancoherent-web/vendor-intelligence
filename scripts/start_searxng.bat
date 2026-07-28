@echo off
cd /d "%~dp0.."
echo Starting SearXNG on http://127.0.0.1:8080 (GRANIAN_WORKERS=5 from docker-compose.yml) ...
docker compose up -d searxng
echo.
echo Verify workers: docker exec vendor-intel-searxng ps aux
echo Test in browser: http://127.0.0.1:8080
pause
