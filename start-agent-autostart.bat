@echo off
REM Autonomous Issue Agent - Autostart Script for Windows
REM This script starts the agent in WSL after Windows boots

echo Starting Autonomous Issue Agent in WSL...
echo Time: %date% %time%

REM Start WSL with the agent
wsl bash -c "cd /mnt/c/Users/MaxAigner/autonomous-issue-agent && ./run.sh"

REM If WSL fails, log the error
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to start agent at %date% %time% >> %TEMP%\agent-autostart-error.log
    echo Check WSL installation and agent configuration >> %TEMP%\agent-autostart-error.log
)
