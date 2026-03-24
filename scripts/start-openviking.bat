@echo off
REM Start OpenViking server for Windows
REM This script is called automatically by start-agent.bat

REM Check if OpenViking is installed
where openviking-server >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo OpenViking server not found. Run setup-openviking.bat first.
    exit /b 0
)

REM Check if server is already running
tasklist /FI "IMAGENAME eq openviking-server.exe" 2>NUL | find /I /N "openviking-server.exe">NUL
if %ERRORLEVEL% EQU 0 (
    echo OpenViking server already running
    exit /b 0
)

REM Create log directory
if not exist "%USERPROFILE%\.openviking" mkdir "%USERPROFILE%\.openviking"

REM Start server in background
echo Starting OpenViking server...
start /B openviking-server > "%USERPROFILE%\.openviking\server.log" 2>&1

REM Wait a moment for startup
timeout /t 2 /nobreak >nul

REM Verify it started
tasklist /FI "IMAGENAME eq openviking-server.exe" 2>NUL | find /I /N "openviking-server.exe">NUL
if %ERRORLEVEL% EQU 0 (
    echo OpenViking server started
) else (
    echo Failed to start OpenViking server
    exit /b 1
)

exit /b 0
