#!/bin/bash
# Start the autonomous agent with dashboard

cd "$(dirname "$0")"

echo "🤖 Starting Autonomous Issue Agent"
echo ""

# Add development tools to PATH
export PATH="$HOME/.dotnet:$HOME/.cargo/bin:$PATH"

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
echo ""

# Start agent in background (with suspend inhibit if available)
echo "Starting agent in background..."
if command -v gnome-session-inhibit &> /dev/null; then
    # GNOME: Prevent sleep while agent runs
    nohup gnome-session-inhibit --inhibit suspend,idle --who "CAP Agent" --what "Processing GitHub issues" --why "Autonomous agent running" python3 main.py > /dev/null 2>&1 &
    AGENT_PID=$!
    echo "✅ Agent started with sleep prevention (PID: $AGENT_PID)"
else
    nohup python3 main.py > /dev/null 2>&1 &
    AGENT_PID=$!
    echo "✅ Agent started (PID: $AGENT_PID)"
    echo "⚠️  Note: gnome-session-inhibit not found - system may sleep"
fi
sleep 2

# Launch dashboard in foreground
echo "Launching dashboard..."
echo ""
python3 src/dashboard_interactive.py
