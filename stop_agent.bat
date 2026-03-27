@echo off
REM Stop Autonomous Agent in WSL

cd /d "%~dp0"

echo ========================================
echo Stopping Autonomous Issue Agent
echo ========================================
echo.

REM Kill all python processes running main.py
wsl.exe bash -c "pkill -f 'python3 main.py' && echo 'Agent stopped.' || echo 'No agent running.'"

REM Remove PID file if exists
if exist agent.pid del agent.pid

echo.
pause
