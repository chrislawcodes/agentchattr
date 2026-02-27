#!/usr/bin/env bash
# agentchattr — starts the server only
cd "$(dirname "$0")/.."

# Auto-create venv and install deps on first run
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    .venv/bin/pip install -q -r requirements.txt > /dev/null 2>&1
fi
source .venv/bin/activate

python run.py
echo ""
echo "=== Server exited with code $? ==="
