@echo off
cd /d "%~dp0"
echo Vendor Intelligence - setup
echo.
echo For the full local UI (recommended), use:
echo   1. copy .env.local.example .env   ^& paste your LLM key
echo   2. START_STREAMLIT.bat            ^(no Node needed^)
echo   or START_WEB.bat                  ^(needs Node for Next.js UI^)
echo.
echo See LOCAL_SETUP.md
echo.
call "%~dp0setup_local.bat"
if errorlevel 1 (
  pause
  exit /b 1
)
echo.
echo Ready. Next:
echo   START_STREAMLIT.bat
echo   or  run.bat "Give me the best laptop companies in India"
echo.
pause
