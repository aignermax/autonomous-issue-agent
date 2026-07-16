#!/bin/bash
# Start the autonomous agent with dashboard

cd "$(dirname "$0")"

echo "🤖 Starting Autonomous Issue Agent"
echo ""

# Add development tools to PATH
# - $HOME/.dotnet           dotnet build / test
# - $HOME/.dotnet/tools     dotnet global tools
# - $HOME/.npm-global/bin   codegraph (MCP server binary)
# - $HOME/.cargo/bin        rustup-installed toolchains
export DOTNET_ROOT="$HOME/.dotnet"
export PATH="$HOME/.npm-global/bin:$HOME/.dotnet:$HOME/.dotnet/tools:$HOME/.cargo/bin:$PATH"

# Check if WSL venv exists (for WSL environment)
if [ -d "wsl-venv" ]; then
    echo "Using WSL virtual environment..."
    source wsl-venv/bin/activate
elif [ -d "venv" ]; then
    echo "Using standard virtual environment..."
    source venv/bin/activate
else
    echo "❌ Virtual environment not found!"
    echo "Run: python3 -m venv wsl-venv && source wsl-venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

# Show available development tools
echo ""
echo "Development tools available:"
command -v dotnet &> /dev/null && echo "  ✅ .NET SDK $(dotnet --version 2>/dev/null || echo 'installed')" || echo "  ⚠️  .NET SDK not found"
command -v rustc &> /dev/null && echo "  ✅ Rust $(rustc --version 2>/dev/null | awk '{print $2}')" || echo "  ⚠️  Rust not found"
command -v node &> /dev/null && echo "  ✅ Node.js $(node --version 2>/dev/null)" || echo "  ⚠️  Node.js not found"
command -v cmake &> /dev/null && echo "  ✅ CMake $(cmake --version 2>/dev/null | head -1 | awk '{print $3}')" || echo "  ⚠️  CMake not found"
command -v wix &> /dev/null && echo "  ✅ WiX Toolset $(wix --version 2>/dev/null || echo 'v7')" || echo "  ⚠️  WiX not found"
echo ""

# Start coder + QA agents in background. Both roles must run for a fully
# autonomous loop: the coder writes/reviews code, the QA agent runs tests
# against the resulting PRs and posts a verdict (which the coder then
# reacts to via its qa-fix flow).
echo "Starting agents in background..."
if command -v gnome-session-inhibit &> /dev/null; then
    nohup gnome-session-inhibit --inhibit suspend,idle --who "CAP Agent" --what "Processing GitHub issues" --why "Autonomous coder agent" python3 main.py > /dev/null 2>&1 &
    AGENT_PID=$!
    nohup gnome-session-inhibit --inhibit suspend,idle --who "CAP QA Agent" --what "Verifying agent PRs" --why "Autonomous QA agent" python3 main.py --role qa > qa-agent.log 2>&1 &
    QA_PID=$!
    nohup gnome-session-inhibit --inhibit suspend,idle --who "CAP PR-Feedback Agent" --what "Handling PR feedback comments" --why "Autonomous PR-feedback agent" python3 main.py --role pr-feedback > pr-feedback-agent.log 2>&1 &
    FB_PID=$!
    echo "✅ Coder started with sleep prevention (PID: $AGENT_PID)"
    echo "✅ QA agent started with sleep prevention (PID: $QA_PID)"
    echo "✅ PR-feedback agent started with sleep prevention (PID: $FB_PID)"
else
    nohup python3 main.py > /dev/null 2>&1 &
    AGENT_PID=$!
    nohup python3 main.py --role qa > qa-agent.log 2>&1 &
    QA_PID=$!
    nohup python3 main.py --role pr-feedback > pr-feedback-agent.log 2>&1 &
    FB_PID=$!
    echo "✅ Coder started (PID: $AGENT_PID)"
    echo "✅ QA agent started (PID: $QA_PID)"
    echo "✅ PR-feedback agent started (PID: $FB_PID)"
    echo "⚠️  Note: gnome-session-inhibit not found - system may sleep"
fi
sleep 2

# Launch dashboard in foreground
echo "Launching dashboard..."
echo ""
python3 src/dashboard_interactive.py
