#!/bin/bash
# Start the autonomous agents (idempotent) + dashboard.
#
# Agents run as systemd user units (aia-coder / aia-qa / aia-prfeedback) —
# scripts/ensure-agents.sh leaves them running when current, restarts them
# when outdated, and never creates duplicates. This script may be run any
# number of times; it no longer spawns its own agent processes.

cd "$(dirname "$0")"

echo "🤖 Autonomous Issue Agent"
echo ""

# Add development tools to PATH (dashboard + any subprocesses)
export DOTNET_ROOT="$HOME/.dotnet"
export PATH="$HOME/.npm-global/bin:$HOME/.dotnet:$HOME/.dotnet/tools:$HOME/.cargo/bin:$PATH"

# Activate the WSL venv (required — Windows venv breaks on pty import)
if [ -d "wsl-venv" ]; then
    source wsl-venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
else
    echo "❌ Virtual environment not found!"
    echo "Run: python3 -m venv wsl-venv && source wsl-venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

# Ensure the three agent units are running with current code (no duplicates).
bash scripts/ensure-agents.sh
echo ""

# Launch dashboard in foreground
echo "Launching dashboard..."
echo ""
python3 src/dashboard_interactive.py
