@echo off
REM Start Autonomous Agent System in WSL
REM Opens WSL terminal with the dashboard (use 'g' to start agent if not running)

cd /d "%~dp0"

echo ========================================
echo Autonomous Issue Agent - WSL Launch
echo ========================================
echo.
echo Opening WSL terminal...
echo.
echo The dashboard will show:
echo   - Agent status
echo   - Monitored repositories
echo   - Recent activity
echo.
echo Controls:
echo   [g] - Start agent if not running
echo   [s] - Stop agent
echo   [q] - Quit dashboard
echo.

REM Get current directory in Windows format and convert to WSL path
REM Example: C:\Users\Name\autonomous-issue-agent -> /mnt/c/Users/Name/autonomous-issue-agent
for %%I in (.) do set CURRENT_DIR=%%~fI
set WSL_PATH=%CURRENT_DIR:\=/%
set WSL_PATH=%WSL_PATH:C:=/mnt/c%
set WSL_PATH=%WSL_PATH:D:=/mnt/d%
set WSL_PATH=%WSL_PATH:E:=/mnt/e%

REM Open WSL and run dashboard from current directory
wsl.exe bash -c "cd '%WSL_PATH%' && ./dashboard_interactive.sh"
