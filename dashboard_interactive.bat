@echo off
REM Interactive Dashboard with keyboard controls
REM Runs in WSL to detect WSL agent

cd /d "%~dp0"

echo Starting Dashboard in WSL...
echo This allows the dashboard to detect the WSL agent.
echo.

REM Run dashboard in WSL
wsl.exe bash -c "cd /mnt/c/Users/MaxAigner/autonomous-issue-agent && wsl-venv/bin/python3 src/dashboard_interactive.py"

pause
