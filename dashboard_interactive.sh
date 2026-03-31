#!/bin/bash
# Interactive Dashboard with keyboard controls
cd "$(dirname "$0")"

# Activate venv if it exists
if [ -d "wsl-venv" ]; then
    source wsl-venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
fi

python3 src/dashboard_interactive.py
