#!/usr/bin/env bash
# agentchattr — unified start script for server + all agents
# Usage: ./macos-linux/start.sh

cd "$(dirname "$0")/.."

# 1. Setup environment
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
    .venv/bin/pip install -q -r requirements.txt
fi
source .venv/bin/activate

# 2. Check for tmux
if ! command -v tmux > /dev/null 2>&1; then
    echo "Error: tmux is required for this script."
    exit 1
fi

# 3. Start Server if not running
if ! lsof -i :8300 -sTCP:LISTEN >/dev/null 2>&1 && \
   ! ss -tlnp 2>/dev/null | grep -q ':8300 '; then
    echo "Starting server in tmux (agentchattr-server)..."
    tmux new-session -d -s agentchattr-server "source .venv/bin/activate && python run.py"
    
    # Wait for server to be ready (up to 15s)
    echo "Waiting for server to be ready..."
    for i in $(seq 1 30); do
        (lsof -i :8300 -sTCP:LISTEN >/dev/null 2>&1 || ss -tlnp 2>/dev/null | grep -q ':8300 ') && break
        sleep 0.5
    done
else
    echo "Server already running on port 8300."
fi

# 4. Start Agents (idempotent)
start_agent() {
    local agent=$1
    local extra=$2
    local session="agentchattr-$agent"
    
    if ! tmux has-session -t "$session" 2>/dev/null; then
        echo "Starting $agent in headless mode..."
        # Run wrapper in background. It creates its own tmux session and watches queue.
        nohup python wrapper.py "$agent" --headless $extra > "data/${agent}_wrapper.log" 2>&1 &
    else
        echo "Agent $agent already running ($session)."
    fi
}

mkdir -p data
start_agent claude
start_agent codex
start_agent gemini "--approval-mode yolo"

echo ""
echo "===================================================="
echo "  agentchattr started!"
echo "  Web UI: http://localhost:8300"
echo "===================================================="
echo "  Tmux sessions active:"
tmux ls | grep agentchattr
echo "===================================================="
echo "  To see an agent: tmux attach -t agentchattr-<name>"
echo "  To stop: tmux kill-server (or kill individual sessions)"
echo ""
