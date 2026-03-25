#!/bin/bash
# Interactive Dashboard with keyboard controls
cd "$(dirname "$0")"

# Activate venv if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

python3 src/dashboard_interactive.py
