@echo off
REM Always run from the folder this script lives in
cd /d "%~dp0"
if not exist "%~dp0api\main.py" (
  echo ERROR: api\main.py not found in %~dp0
  pause
  exit /b 1
)
title VendorIntel-Web
echo.
echo ========================================
echo  Vendor Intelligence - Web UI
echo  Folder: %~dp0
echo ========================================
echo.

if not exist "%~dp0frontend\out\index.html" (
  echo Frontend not built yet. Building once...
  where npm >nul 2>&1
  if errorlevel 1 (
    echo ERROR: Node/npm required once to build Web UI.
    echo Or use START_STREAMLIT.bat instead.
    goto :end
  )
  pushd "%~dp0frontend"
  call npm install
  if errorlevel 1 (
    popd
    echo ERROR: npm install failed
    goto :end
  )
  call npm run build
  if errorlevel 1 (
    popd
    echo ERROR: npm run build failed
    goto :end
  )
  popd
)

call "%~dp0setup_local.bat"
if errorlevel 1 goto :fail

findstr /C:"PASTE_YOUR_KEY_HERE" "%~dp0.env" >nul 2>&1
if not errorlevel 1 (
  echo ACTION: Open .env and put your API key, then run again.
  notepad "%~dp0.env"
  goto :end
)

set "FRONTEND_DIST=%~dp0frontend\out"
set "PYTHONPATH=%~dp0src;%~dp0"
set "PORT=8080"

echo.
echo Starting Web UI at http://127.0.0.1:8080
echo Keep this window open. Ctrl+C to stop.
echo.
.venv\Scripts\python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8080
echo.
echo Server stopped.
goto :end

:fail
echo.
echo Setup failed. See messages above.

:end
echo.
pause
