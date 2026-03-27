@echo off
REM Start Autonomous Agent in WSL
REM Agent runs in background and processes GitHub issues

cd /d "%~dp0"

echo ========================================
echo Starting Autonomous Issue Agent in WSL
echo ========================================
echo.
echo Repositories:
echo   - Akhetonics/akhetonics-desktop
echo   - Akhetonics/raycore-sdk
echo.
echo Label Filter: agent-task
echo.

REM Check if WSL venv exists, create if not
wsl.exe bash -c "cd /mnt/c/Users/MaxAigner/autonomous-issue-agent && if [ ! -d wsl-venv ]; then echo 'Creating Python venv...'; python3 -m venv wsl-venv && wsl-venv/bin/pip install -q -r requirements.txt; fi"

REM Start agent in background
echo Starting agent in background...
wsl.exe bash -c "cd /mnt/c/Users/MaxAigner/autonomous-issue-agent && nohup wsl-venv/bin/python3 main.py > agent.log 2>&1 & echo 'Agent started with PID:' \$! && echo \$! > agent.pid"

echo.
echo Agent is now running in WSL!
echo Use dashboard_interactive.bat to monitor progress.
echo.
echo Logs: autonomous-issue-agent\agent.log
echo.

pause
