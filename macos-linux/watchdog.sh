#!/usr/bin/env bash
# agentchattr wrapper watchdog
# Restarts missing headless wrapper processes for codex/gemini/claude.

cd "$(dirname "$0")/.."

source .venv/bin/activate 2>/dev/null || true
mkdir -p data

wrapper_running() {
    local agent=$1
    pgrep -f "python .*wrapper.py ${agent}( |$)" >/dev/null 2>&1
}

session_alive() {
    local agent=$1
    tmux has-session -t "agentchattr-${agent}" 2>/dev/null
}

restart_agent() {
    local agent=$1
    
    if session_alive "$agent"; then
        echo "[$(date '+%H:%M:%S')] SKIP: tmux session for $agent is alive, not restarting wrapper"
        return
    fi

    echo "[$(date '+%H:%M:%S')] Restarting missing wrapper for $agent"
    nohup python wrapper.py "$agent" --headless >> "data/${agent}_wrapper.log" 2>&1 &
}

while true; do
    # Claude is excluded — its wrapper kills the active session on restart,
    # ending the user's conversation. Claude manages its own MCP connection.
    wrapper_running codex || restart_agent codex
    wrapper_running gemini || restart_agent gemini
    sleep 60
done
