#!/usr/bin/env bash
# agentchattr wrapper watchdog
# Restarts missing headless wrapper processes for codex/gemini/claude.

cd "$(dirname "$0")/.."

source .venv/bin/activate
mkdir -p data

wrapper_running() {
    local agent=$1
    pgrep -f "python .*wrapper.py ${agent}( |$)" >/dev/null 2>&1
}

restart_agent() {
    local agent=$1
    local extra=$2
    echo "[$(date '+%H:%M:%S')] Restarting missing wrapper for $agent"
    nohup python wrapper.py "$agent" --headless $extra >> "data/${agent}_wrapper.log" 2>&1 &
}

while true; do
    # Claude is excluded — its wrapper kills the active session on restart,
    # ending the user's conversation. Claude manages its own MCP connection.
    wrapper_running codex || restart_agent codex
    wrapper_running gemini || restart_agent gemini
    sleep 60
done
