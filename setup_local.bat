@echo off
cd /d "%~dp0"
title VendorIntel-Setup

where python >nul 2>&1
if errorlevel 1 goto :no_python

python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" 2>nul
if errorlevel 1 goto :bad_python

if not exist .venv (
  echo Creating .venv ...
  python -m venv .venv
  if errorlevel 1 exit /b 1
)

if not exist .venv\Scripts\python.exe (
  echo ERROR: .venv is broken. Delete .venv folder and retry.
  exit /b 1
)

if not exist .venv\.deps_ok (
  echo Installing Python packages first time...
  .venv\Scripts\python.exe -m pip install --upgrade pip -q
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  if errorlevel 1 (
    echo ERROR: pip install failed
    exit /b 1
  )
  type nul > .venv\.deps_ok
) else (
  echo Python packages already installed.
)

if not exist .env (
  if exist .env.local.example copy /Y .env.local.example .env >nul
  if not exist .env if exist .env.example copy /Y .env.example .env >nul
  echo Created .env - put your API key in it if needed.
)

if not exist data mkdir data
if not exist output mkdir output
if not exist output\demo mkdir output\demo

echo Init auth database...
.venv\Scripts\python.exe scripts\init_auth_db.py
if errorlevel 1 echo WARN: auth DB init failed

exit /b 0

:no_python
echo ERROR: Python not found. Install Python 3.11+ and tick Add to PATH.
exit /b 1

:bad_python
echo ERROR: Need Python 3.11+. Current:
python --version
exit /b 1
