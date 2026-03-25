@echo off
REM Interactive Dashboard with keyboard controls
REM Works on Windows

cd /d "%~dp0"

REM Activate venv if it exists
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
)

python src\dashboard_interactive.py

pause
