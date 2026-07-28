@echo off
cd /d "%~dp0"
call .venv\Scripts\activate.bat 2>nul || (echo Run setup.bat first & pause & exit /b 1)
if "%~1"=="" (
  python run_cli.py "Give me the best laptop companies in India"
) else (
  python run_cli.py %*
)
pause
