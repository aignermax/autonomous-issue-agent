#!/bin/bash
# Start autonomous agent in WSL

cd /mnt/c/Users/MaxAigner/autonomous-issue-agent

# Create venv if not exists
if [ ! -d "wsl-venv" ]; then
    echo "Creating venv..."
    python3 -m venv wsl-venv
    wsl-venv/bin/pip install -q -r requirements.txt
fi

# Start agent
echo "Starting agent..."
nohup wsl-venv/bin/python3 main.py > agent.log 2>&1 &
PID=$!
echo "Agent started with PID: $PID"
echo $PID > agent.pid
