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

REM Open WSL and run dashboard directly
wsl.exe bash -c "cd ~/autonomous-agent-linux && venv/bin/python3 src/dashboard_interactive.py"
