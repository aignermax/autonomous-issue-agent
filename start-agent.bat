@echo off
REM Start the autonomous issue agent with dashboard
REM This must be run OUTSIDE of a Claude Code session

echo === Autonomous Issue Agent (AIA) ===
echo.

REM Change to script directory
cd /d "%~dp0"

REM Check if .env file exists
if not exist .env (
    echo ERROR: .env file not found!
    echo.
    echo Please create a .env file with your credentials:
    echo   copy .env.example .env
    echo.
    echo Then edit .env and add your tokens:
    echo   GITHUB_TOKEN=ghp_your_github_token_here
    echo   ANTHROPIC_API_KEY=sk-ant-your_anthropic_key_here
    echo   AGENT_REPO=owner/repo-name
    echo.
    pause
    exit /b 1
)

echo Loading environment variables from .env...

REM Check if venv exists
if not exist venv (
    echo Virtual environment not found. Creating...
    python -m venv venv
    echo Virtual environment created
    echo.
)

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Check if dependencies are installed
python -c "import github" 2>nul
if errorlevel 1 (
    echo Installing dependencies...
    pip install -r requirements.txt
    echo Dependencies installed
    echo.
)

REM Check if Claude Code CLI is installed
where claude >nul 2>nul
if errorlevel 1 (
    echo WARNING: Claude Code CLI not found!
    echo Install with: npm install -g @anthropic-ai/claude-code
    echo.
    pause
)

echo.
echo Starting agent with dashboard...
echo.

REM Check for --no-dashboard flag
set SHOW_DASHBOARD=1
for %%a in (%*) do (
    if "%%a"=="--no-dashboard" set SHOW_DASHBOARD=0
)

REM Start dashboard in new window if not disabled
if "%SHOW_DASHBOARD%"=="1" (
    echo Dashboard will launch in a new window...
    start "Agent Dashboard" cmd /k "cd /d "%~dp0" && call venv\Scripts\activate.bat && python src\dashboard.py"
    timeout /t 2 >nul
)

REM Unset CLAUDECODE variable to allow nested sessions (use with caution!)
set CLAUDECODE=

REM Run the agent
python main.py %*

pause
