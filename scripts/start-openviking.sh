#!/bin/bash
# Start OpenViking server in background
# Called automatically by run_agent.sh

OPENVIKING_CMD="${HOME}/.local/bin/openviking-server"
LOG_FILE="${HOME}/.openviking/server.log"

# Check if OpenViking is installed
if [ ! -f "$OPENVIKING_CMD" ]; then
    echo "⚠️  OpenViking not installed. Run: ./scripts/setup-openviking.sh"
    exit 1
fi

# Check if already running
if pgrep -f "openviking-server" > /dev/null; then
    echo "✅ OpenViking server already running"
    exit 0
fi

# Start server in background
echo "🚀 Starting OpenViking server..."
nohup "$OPENVIKING_CMD" > "$LOG_FILE" 2>&1 &

# Wait for server to start
sleep 2

# Check if running
if pgrep -f "openviking-server" > /dev/null; then
    echo "✅ OpenViking server started (PID: $(pgrep -f 'openviking-server'))"
    echo "   Log: $LOG_FILE"
else
    echo "❌ Failed to start OpenViking server"
    echo "   Check log: $LOG_FILE"
    exit 1
fi
