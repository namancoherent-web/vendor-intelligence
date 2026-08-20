@echo off
REM Always run from the folder this script lives in
cd /d "%~dp0"
REM Force UTF-8 stdio so any non-ASCII log output (em-dashes, checkmarks, etc.) never
REM crashes a run with a silent UnicodeEncodeError on a fresh Windows console.
set PYTHONIOENCODING=utf-8
if not exist "%~dp0app.py" (
  echo ERROR: app.py not found in %~dp0
  pause
  exit /b 1
)
title VendorIntel-Streamlit
echo.
echo ========================================
echo  Vendor Intelligence - Streamlit
echo  Folder: %~dp0
echo ========================================
echo.

if exist "%~dp0.venv\Scripts\python.exe" (
  "%~dp0.venv\Scripts\python.exe" "%~dp0scripts\update_check.py" 2>nul
)

call "%~dp0setup_local.bat"
if errorlevel 1 goto :fail

findstr /C:"PASTE_YOUR_KEY_HERE" "%~dp0.env" >nul 2>&1
if not errorlevel 1 (
  echo ACTION: Open .env and put your API key, then run again.
  notepad "%~dp0.env"
  goto :end
)

echo.
echo Starting Streamlit at http://127.0.0.1:8501
echo Keep this window open. Ctrl+C to stop.
echo.
.venv\Scripts\python.exe -m streamlit run app.py --server.headless true --browser.gatherUsageStats false
echo.
echo Streamlit stopped.
goto :end

:fail
echo.
echo Setup failed. See messages above.

:end
echo.
pause
