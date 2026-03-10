@echo off
REM Start the autonomous issue agent
REM This must be run OUTSIDE of a Claude Code session

echo Starting Autonomous Issue Agent...
echo.
echo Make sure you are NOT inside a Claude Code session!
echo The agent will poll for 'agent-task' labeled issues every 5 minutes.
echo Press Ctrl+C to stop.
echo.

cd /d C:\dev\Akhetonics\autonomous-issue-agent

REM Unset CLAUDECODE variable to allow nested sessions (use with caution!)
set CLAUDECODE=

python main.py

pause
