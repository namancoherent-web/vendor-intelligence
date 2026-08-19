@echo off
REM Double-click this if you know an update was shipped but the app hasn't picked it up yet
REM (it normally only checks once a day - this skips that wait and checks right now).
cd /d "%~dp0"
title VendorIntel-ForceUpdate
echo.
echo ========================================
echo  Vendor Intelligence - Force Update Check
echo ========================================
echo.

if not exist "%~dp0.venv\Scripts\python.exe" (
  echo ERROR: Setup hasn't run yet on this laptop.
  echo Please run START_WEB.bat or START_STREAMLIT.bat first, then try this again.
  goto :end
)

echo Checking for updates now...
echo.
"%~dp0.venv\Scripts\python.exe" "%~dp0scripts\update_check.py" --force

echo.
echo Done. You can now start the app as usual:
echo   START_WEB.bat
echo   or START_STREAMLIT.bat

:end
echo.
pause
