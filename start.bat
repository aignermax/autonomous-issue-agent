@echo off
REM Single entry point: starts the autonomous agent + dashboard in WSL.
REM Underlying bash logic lives in run.sh — this .bat just provides a nice
REM Windows-side wrapper (Windows Terminal if available, otherwise plain WSL)
REM and is shared with start-agent-autostart.bat.

cd /d "%~dp0"

echo ========================================
echo Autonomous Issue Agent - WSL Launch
echo ========================================
echo.
echo Starting agent in background + dashboard in foreground.
echo Dashboard controls:
echo   [g] Start agent (if not running)   [k] Stop agent
echo   [s] Stream logs                    [q] Quit dashboard
echo.

REM Convert this directory to a WSL path: C:\Users\Foo\bar -> /mnt/c/Users/Foo/bar
for %%I in (.) do set CURRENT_DIR=%%~fI
set WSL_PATH=%CURRENT_DIR:\=/%
set WSL_PATH=%WSL_PATH:C:=/mnt/c%
set WSL_PATH=%WSL_PATH:D:=/mnt/d%
set WSL_PATH=%WSL_PATH:E:=/mnt/e%

REM Prefer Windows Terminal for better rendering; fall back to plain WSL.
where wt.exe >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    start wt.exe -p "Ubuntu" wsl.exe bash -c "cd '%WSL_PATH%' && ./run.sh"
) else (
    wsl.exe bash -c "cd '%WSL_PATH%' && ./run.sh"
)
