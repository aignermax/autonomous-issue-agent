#!/bin/bash
# Start the autonomous agent with dashboard

cd "$(dirname "$0")"

echo "🤖 Starting Autonomous Issue Agent"
echo ""

# Check if venv exists
if [ ! -d "venv" ]; then
    echo "❌ Virtual environment not found!"
    echo "Run: python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

# Activate virtual environment
source venv/bin/activate

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
