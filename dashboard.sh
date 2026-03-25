#!/bin/bash
# Launch the Autonomous Issue Agent Dashboard
# Shows real-time status of agent and MCP servers

cd "$(dirname "$0")"

echo "🚀 Starting Autonomous Issue Agent Dashboard..."
echo ""
echo "Press Ctrl+C to exit"
echo ""

python3 src/dashboard.py
