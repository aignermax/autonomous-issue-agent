@echo off
REM Test the autonomous issue agent (single run)
REM This must be run OUTSIDE of a Claude Code session

echo Testing Autonomous Issue Agent (single run)...
echo.
echo Make sure you are NOT inside a Claude Code session!
echo The agent will process ONE issue and then exit.
echo.

cd /d C:\dev\Akhetonics\autonomous-issue-agent

REM Unset CLAUDECODE variable to allow nested sessions (use with caution!)
set CLAUDECODE=

REM Start OpenViking server if configured
if exist scripts\start-openviking.bat (
    call scripts\start-openviking.bat
)

python main.py --once

pause
