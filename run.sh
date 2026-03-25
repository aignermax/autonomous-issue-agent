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

# Start agent in background
echo "Starting agent in background..."
nohup python3 main.py > /dev/null 2>&1 &
AGENT_PID=$!
echo "✅ Agent started (PID: $AGENT_PID)"
sleep 2

# Launch dashboard in foreground
echo "Launching dashboard..."
echo ""
python3 src/dashboard_interactive.py
