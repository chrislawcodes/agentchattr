"""Agent wrapper — runs the real interactive CLI with auto-trigger on @mentions.

Usage:
    python wrapper.py claude     # Claude Code with chat auto-trigger
    python wrapper.py codex      # Codex with chat auto-trigger

Cross-platform:
  - Windows: injects keystrokes via Win32 WriteConsoleInput  (wrapper_windows.py)
  - Mac/Linux: injects keystrokes via tmux send-keys          (wrapper_unix.py)

How it works:
  1. Starts the agent CLI in an interactive terminal (full TUI)
  2. Watches the queue file in background for @mentions from the chat room
  3. When triggered, injects "chat - use mcp" + Enter into the agent
  4. The agent picks up the prompt as if the user typed it
"""

import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
import tomllib
from pathlib import Path

ROOT = Path(__file__).parent
log = logging.getLogger(__name__)

SERVER_NAME = "agentchattr"
DEFAULT_TRIGGER_COOLDOWN_SECONDS = 2.0
MCP_TOOL_CALL_TIMEOUT_SECONDS = 5.0
RESTART_WATCH_INTERVAL_SECONDS = 10.0

# ---------------------------------------------------------------------------
# MCP auto-config — ensure .mcp.json and .gemini/settings.json exist
# ---------------------------------------------------------------------------

def _ensure_mcp(project_dir: Path, mcp_cfg: dict):
    """Create MCP config files in the agent's working directory if missing."""
    http_port = mcp_cfg.get("http_port", 8200)
    sse_port = mcp_cfg.get("sse_port", 8201)
    http_url = f"http://127.0.0.1:{http_port}/mcp"
    sse_url = f"http://127.0.0.1:{sse_port}/sse"

    # --- Claude (.mcp.json) ---
    _ensure_json_mcp(project_dir / ".mcp.json", http_url)

    # --- Gemini (.gemini/settings.json) ---
    _ensure_json_mcp(project_dir / ".gemini" / "settings.json", sse_url, transport="sse")

    # --- Codex (.codex/config.toml) ---
    _ensure_codex_mcp(project_dir / ".codex" / "config.toml", http_url)


def _ensure_json_mcp(mcp_file: Path, url: str, transport: str = "http"):
    """Add agentchattr to a JSON MCP config file (Claude / Gemini)."""
    mcp_file.parent.mkdir(parents=True, exist_ok=True)

    if mcp_file.exists():
        try:
            data = json.loads(mcp_file.read_text("utf-8"))
        except json.JSONDecodeError:
            print(f"  MCP: WARNING — {mcp_file} has invalid JSON, can't add {SERVER_NAME}")
            return
    else:
        data = {}

    servers = data.setdefault("mcpServers", {})
    if SERVER_NAME in servers:
        return

    servers[SERVER_NAME] = {"type": transport, "url": url}
    mcp_file.write_text(json.dumps(data, indent=2) + "\n", "utf-8")
    print(f"  MCP: added {SERVER_NAME} to {mcp_file}")


def _ensure_codex_mcp(toml_file: Path, url: str):
    """Add agentchattr to Codex's TOML config file."""
    toml_file.parent.mkdir(parents=True, exist_ok=True)
    section = f"mcp_servers.{SERVER_NAME}"

    if toml_file.exists():
        content = toml_file.read_text("utf-8")
        if section in content:
            return
    else:
        content = ""

    block = f'\n[{section}]\nurl = "{url}"\n'
    toml_file.write_text(content + block, "utf-8")
    print(f"  MCP: added {SERVER_NAME} to {toml_file}")


# ---------------------------------------------------------------------------
# Queue Watcher — polls for @mention triggers, calls platform inject function
# ---------------------------------------------------------------------------

class MonitorState:
    def __init__(self):
        self.last_inject_at = 0.0
        self.lock = threading.Lock()

    def record_inject(self):
        with self.lock:
            self.last_inject_at = time.time()

    def get_last_inject(self):
        with self.lock:
            return self.last_inject_at


def _notify_recovery(data_dir: Path, agent_name: str):
    """Write a flag file that the server picks up and broadcasts as a system message."""
    try:
        flag = data_dir / f"{agent_name}_recovered"
        flag.write_text(agent_name, "utf-8")
    except Exception:
        pass


def _trigger_cooldown_seconds(agent_name: str, agent_cfg: dict) -> float:
    """Per-agent debounce to avoid spamming interactive CLIs with repeated wake commands.

    Reads 'trigger_cooldown' from the agent's config section (config.toml).
    Falls back to DEFAULT_TRIGGER_COOLDOWN_SECONDS if not set.
    """
    return float(agent_cfg.get("trigger_cooldown", DEFAULT_TRIGGER_COOLDOWN_SECONDS))


def _queue_watcher(queue_file: Path, agent_name: str, inject_fn, agent_cfg: dict, state: MonitorState):
    """Poll queue file; call inject_fn('chat - use mcp') when triggered."""
    cooldown = _trigger_cooldown_seconds(agent_name, agent_cfg)

    while True:
        try:
            if queue_file.exists() and queue_file.stat().st_size > 0:
                with open(queue_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                queue_file.write_text("")

                has_trigger = False
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        json.loads(line)
                        has_trigger = True
                    except json.JSONDecodeError:
                        log.warning("Skipping malformed queue entry for %s: %r", agent_name, line)

                if has_trigger:
                    # Debounce wake-ups so slower TUIs (notably Gemini CLI)
                    # can finish MCP prompts before the next injected command.
                    now = time.time()
                    last_inject_at = state.get_last_inject()
                    elapsed = now - last_inject_at
                    if elapsed < cooldown:
                        time.sleep(cooldown - elapsed)
                    # Small delay to let the TUI settle
                    time.sleep(0.5)
                    ok = inject_fn("chat - use mcp")
                    if ok is not False:  # None (old callers) or True = success
                        state.record_inject()
        except Exception as e:
            log.exception("queue watcher error (agent=%s): %s", agent_name, e)

        time.sleep(1)


def _task_monitor(queue_file: Path, inject_fn, state: MonitorState, timeout_minutes: float):
    """If queue is non-empty but no injection for >timeout, auto-reinject."""
    timeout_seconds = timeout_minutes * 60
    while True:
        try:
            time.sleep(30)  # Check every 30s
            if queue_file.exists() and queue_file.stat().st_size > 0:
                now = time.time()
                last_inject = state.get_last_inject()
                if now - last_inject > timeout_seconds:
                    print(f"  [Monitor] Agent seems stuck (queue non-empty for >{timeout_minutes}m). Re-injecting...")
                    ok = inject_fn("chat - use mcp")
                    if ok is not False:
                        state.record_inject()
        except Exception:
            pass


def _kill_tmux_session(tmux_session: str):
    """Kill a tmux session so the wrapper's restart loop recreates it."""
    if sys.platform == "win32":
        log.info("Skipping tmux restart on Windows for session %s", tmux_session)
        return
    subprocess.run(["tmux", "kill-session", "-t", tmux_session], capture_output=True)


def _call_mcp_tool_once(
    mcp_url: str,
    tool_name: str,
    arguments: dict | None = None,
    request_timeout: float = MCP_TOOL_CALL_TIMEOUT_SECONDS,
) -> tuple[bool, str]:
    """Perform one MCP HTTP tool call attempt."""
    import urllib.error
    import urllib.request

    payload = json.dumps({
        "jsonrpc": "2.0",
        "id": f"{tool_name}-call",
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments or {},
        },
    }).encode("utf-8")
    req = urllib.request.Request(
        mcp_url,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=request_timeout) as resp:
            # Read only the first chunk so streamable HTTP responses don't block
            # waiting for EOF on a long-lived connection.
            body = resp.read(4096).decode("utf-8", "replace")
            return 200 <= resp.status < 300, body
    except urllib.error.HTTPError as e:
        log.warning("MCP tool %s failed with HTTP %s", tool_name, e.code)
        return False, ""
    except Exception as e:
        log.warning("MCP tool %s failed: %s", tool_name, e)
        return False, ""


def _call_mcp_tool(
    mcp_url: str,
    tool_name: str,
    arguments: dict | None = None,
    timeout_seconds: float = MCP_TOOL_CALL_TIMEOUT_SECONDS,
) -> tuple[bool, str]:
    """Call a local MCP tool over HTTP."""
    return _call_mcp_tool_once(
        mcp_url,
        tool_name,
        arguments=arguments,
        request_timeout=timeout_seconds,
    )


def _check_mcp_health(mcp_url: str) -> bool:
    """Return True when the local MCP HTTP endpoint responds to chat_ping."""
    ok, body = _call_mcp_tool(mcp_url, "chat_ping")
    return ok and "pong" in body


def _check_sse_health(sse_url: str) -> bool:
    """Return True when the SSE endpoint returns 200 OK (checked via GET)."""
    import urllib.request
    try:
        req = urllib.request.Request(
            sse_url,
            method="GET",
            headers={"Accept": "text/event-stream"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception:
        return False


def _announce_join(mcp_url: str, agent_name: str):
    """Emit chat_join after the agent session starts so presence resets immediately."""
    ok, body = _call_mcp_tool(mcp_url, "chat_join", {"name": agent_name})
    if not ok:
        log.warning("Failed to announce chat_join for %s", agent_name)
    elif "Joined." not in body:
        log.warning("Unexpected chat_join response for %s: %s", agent_name, body)


# ---------------------------------------------------------------------------
# Server restart watcher — kills the tmux session when the server restarts
# so the agent reconnects with a fresh MCP session instead of using stale IDs
# ---------------------------------------------------------------------------

def _watch_for_server_restart(data_dir: Path, tmux_session: str, stop_event: threading.Event):
    """Detect server restarts and kill the tmux session so the agent reconnects.

    Waits one extra 10s cycle after detecting a change to confirm the server is
    stable before restarting — avoids killing agents during server mid-boot.
    """
    started_at_file = data_dir / "server_started_at.txt"
    known_start = started_at_file.read_text().strip() if started_at_file.exists() else ""
    pending_restart = False

    while not stop_event.is_set():
        stop_event.wait(RESTART_WATCH_INTERVAL_SECONDS)
        if stop_event.is_set():
            break
        if not started_at_file.exists():
            pending_restart = False
            continue
        current = started_at_file.read_text().strip()
        if current != known_start:
            if pending_restart:
                # Second consecutive 10s cycle with new timestamp — server is stable, restart
                log.info("Server restart confirmed after 20s — restarting tmux session %s", tmux_session)
                _kill_tmux_session(tmux_session)
                known_start = current
                pending_restart = False
            else:
                # First detection — wait one more 10s cycle to confirm
                log.info("Server restart detected for %s — confirming in 10s", tmux_session)
                pending_restart = True
        else:
            pending_restart = False


def _watch_mcp_health(mcp_url: str, tmux_session: str, stop_event: threading.Event, sse_url: str = None):
    """Restart the tmux session after repeated MCP health check failures.
    
    If sse_url is provided, performs a fast (30s) probe of the SSE transport.
    """
    failures = 0

    # Grace period so the local MCP server can finish booting before checks start.
    if stop_event.wait(60):
        return

    while not stop_event.is_set():
        # 1. Fast SSE probe (if applicable)
        if sse_url:
            if not _check_sse_health(sse_url):
                log.warning("MCP SSE transport failed for %s — restarting immediately", tmux_session)
                _kill_tmux_session(tmux_session)
                # After restart, wait for recovery before next check
                if stop_event.wait(60):
                    break
                failures = 0
                continue

        # 2. Regular HTTP tool-call probe
        healthy = _check_mcp_health(mcp_url)
        if healthy:
            failures = 0
        else:
            failures += 1
            if failures >= 3:
                log.warning(
                    "MCP health failed %d times in a row — restarting tmux session %s",
                    failures,
                    tmux_session,
                )
                _kill_tmux_session(tmux_session)
                failures = 0

        # Poll interval: 30s if we have an SSE transport to monitor, else 5m
        interval = 30 if sse_url else 300
        if stop_event.wait(interval):
            break


def _watch_mcp_heartbeat(mcp_url: str, agent_name: str, stop_event: threading.Event):
    """Periodically refresh agent presence via chat_join to prevent SSE staling."""
    while not stop_event.is_set():
        # Wait first to avoid double-join at startup
        if stop_event.wait(60):
            break
        
        log.debug("Sending periodic heartbeat for %s", agent_name)
        _announce_join(mcp_url, agent_name)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import argparse

    # Load config to get valid agent names
    with open(ROOT / "config.toml", "rb") as f:
        config = tomllib.load(f)

    agent_names = list(config.get("agents", {}).keys())

    parser = argparse.ArgumentParser(description="Agent wrapper with chat auto-trigger")
    parser.add_argument("agent", choices=agent_names,
                        help=f"Agent to wrap ({', '.join(agent_names)})")
    parser.add_argument("--no-restart", action="store_true", help="Don't restart on exit")
    parser.add_argument("--headless", action="store_true", help="Run without attaching to terminal (for nohup/background use)")
    args, extra = parser.parse_known_args()

    agent = args.agent
    agent_cfg = config.get("agents", {}).get(agent, {})
    server_cfg = config.get("server", {})
    task_timeout = float(server_cfg.get("agent_task_timeout_minutes", 5.0))

    # Append resume_flag from config if not already manually provided
    resume_flag = agent_cfg.get("resume_flag")
    if resume_flag:
        import shlex
        resume_args = shlex.split(resume_flag)
        if not any(arg in extra for arg in resume_args):
            extra.extend(resume_args)

    cwd = agent_cfg.get("cwd", ".")
    command = agent_cfg.get("command", agent)
    data_dir = ROOT / config.get("server", {}).get("data_dir", "./data")
    data_dir.mkdir(parents=True, exist_ok=True)
    queue_file = data_dir / f"{agent}_queue.jsonl"

    # Monitor state shared between threads
    state = MonitorState()

    # Flush stale queue entries from previous crashed sessions
    if queue_file.exists():
        queue_file.write_text("", "utf-8")

    # Auto-configure MCP in the agent's working directory so it just works
    mcp_cfg = config.get("mcp", {})
    project_dir = (ROOT / cwd).resolve()
    _ensure_mcp(project_dir, mcp_cfg)

    # Strip CLAUDECODE to avoid "nested session" detection.
    # Also strip any env vars listed in the agent's strip_env config
    # (e.g. ANTHROPIC_API_KEY so Claude uses its stored OAuth credentials).
    strip_vars = {"CLAUDECODE"} | set(agent_cfg.get("strip_env", []))
    env = {k: v for k, v in os.environ.items() if k not in strip_vars}

    # Resolve command on PATH
    resolved = shutil.which(command)
    if not resolved:
        print(f"  Error: '{command}' not found on PATH.")
        print("  Install it first, then try again.")
        sys.exit(1)
    command = resolved

    print(f"  === {agent.capitalize()} Chat Wrapper ===")
    print(f"  @{agent} mentions auto-inject 'chat - use mcp'")
    print(f"  Starting {command} in {cwd}...\n")

    # Helper: start the queue watcher with a given inject function
    # Returns the thread so the monitor can check is_alive()
    _watcher_inject_fn = None
    _watcher_thread = None

    def start_watcher(inject_fn):
        nonlocal _watcher_inject_fn, _watcher_thread
        _watcher_inject_fn = inject_fn
        _watcher_thread = threading.Thread(
            target=_queue_watcher, args=(queue_file, agent, inject_fn, agent_cfg, state), daemon=True
        )
        _watcher_thread.start()
        
        # Start task monitor thread
        threading.Thread(
            target=_task_monitor, args=(queue_file, inject_fn, state, task_timeout), daemon=True
        ).start()

    # Monitor thread: checks watcher health and auto-restarts if dead
    def _watcher_monitor():
        nonlocal _watcher_thread
        while True:
            time.sleep(5)
            if _watcher_thread and not _watcher_thread.is_alive() and _watcher_inject_fn:
                _watcher_thread = threading.Thread(
                    target=_queue_watcher, args=(queue_file, agent, _watcher_inject_fn, agent_cfg, state), daemon=True
                )
                _watcher_thread.start()
                _notify_recovery(data_dir, agent)

    monitor = threading.Thread(target=_watcher_monitor, daemon=True)
    monitor.start()

    # Start server restart watcher — kills tmux session on server restart
    # so the agent process reconnects with a fresh MCP session
    _stop_event = threading.Event()
    tmux_session = f"agentchattr-{agent}"
    mcp_http_url = f"http://127.0.0.1:{mcp_cfg.get('http_port', 8200)}/mcp"
    
    # Detect if this agent uses SSE (currently only gemini)
    mcp_sse_url = None
    if agent == "gemini":
        mcp_sse_url = f"http://127.0.0.1:{mcp_cfg.get('sse_port', 8201)}/sse"

    server_watcher = threading.Thread(
        target=_watch_for_server_restart,
        args=(data_dir, tmux_session, _stop_event),
        daemon=True,
    )
    server_watcher.start()
    health_watcher = threading.Thread(
        target=_watch_mcp_health,
        args=(mcp_http_url, tmux_session, _stop_event, mcp_sse_url),
        daemon=True,
    )
    health_watcher.start()

    heartbeat_watcher = threading.Thread(
        target=_watch_mcp_heartbeat,
        args=(mcp_http_url, agent, _stop_event),
        daemon=True,
    )
    heartbeat_watcher.start()

    def on_session_started():
        threading.Thread(
            target=_announce_join,
            args=(mcp_http_url, agent),
            daemon=True,
        ).start()

    # Dispatch to platform-specific runner
    if sys.platform == "win32":
        from wrapper_windows import run_agent
    else:
        from wrapper_unix import run_agent

    run_agent(
        command=command,
        extra_args=extra,
        cwd=cwd,
        env=env,
        queue_file=queue_file,
        agent=agent,
        no_restart=args.no_restart,
        headless=args.headless,
        start_watcher=start_watcher,
        strip_env=list(strip_vars),
        on_session_started=on_session_started,
    )

    print("  Wrapper stopped.")


if __name__ == "__main__":
    main()
