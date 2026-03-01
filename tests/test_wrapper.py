"""Tests for wrapper.py — cooldown selection and queue watcher logic."""

import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from wrapper import DEFAULT_TRIGGER_COOLDOWN_SECONDS, _trigger_cooldown_seconds  # noqa: E402


# ---------------------------------------------------------------------------
# Cooldown selection
# ---------------------------------------------------------------------------

def test_default_cooldown_when_no_config():
    assert _trigger_cooldown_seconds("claude", {}) == DEFAULT_TRIGGER_COOLDOWN_SECONDS


def test_custom_cooldown_from_config():
    assert _trigger_cooldown_seconds("gemini", {"trigger_cooldown": 10.0}) == 10.0


def test_cooldown_accepts_int_value():
    assert _trigger_cooldown_seconds("codex", {"trigger_cooldown": 5}) == 5.0


def test_cooldown_falls_back_when_key_missing():
    assert _trigger_cooldown_seconds("gemini", {"color": "#4285f4"}) == DEFAULT_TRIGGER_COOLDOWN_SECONDS


# ---------------------------------------------------------------------------
# inject() call ordering (wrapper_unix)
# ---------------------------------------------------------------------------

def test_inject_sends_escape_before_text():
    """Escape must be sent before the literal text to clear pending TUI input."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        from wrapper_unix import inject
        inject("chat - use mcp", tmux_session="test-session")

    calls = mock_run.call_args_list
    assert len(calls) == 4, f"Expected 4 subprocess calls (C-u, Escape, text, Enter), got {len(calls)}"

    # First call: C-u (line clear)
    first_cmd = calls[0][0][0]
    assert "C-u" in first_cmd, f"First call should send C-u, got: {first_cmd}"

    # Second call: Escape
    second_cmd = calls[1][0][0]
    assert "Escape" in second_cmd, f"Second call should send Escape, got: {second_cmd}"

    # Third call: literal text
    third_cmd = calls[2][0][0]
    assert "-l" in third_cmd, f"Third call should use -l flag for literal text, got: {third_cmd}"
    assert "chat - use mcp" in third_cmd

    # Fourth call: Enter
    fourth_cmd = calls[3][0][0]
    assert "Enter" in fourth_cmd, f"Fourth call should send Enter, got: {fourth_cmd}"


def test_inject_uses_correct_session_name():
    """All tmux calls must target the specified session."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        from wrapper_unix import inject
        inject("hello", tmux_session="agentchattr-gemini")

    for c in mock_run.call_args_list:
        cmd = c[0][0]
        assert "agentchattr-gemini" in cmd, f"Expected session name in call: {cmd}"


# ---------------------------------------------------------------------------
# Queue watcher — trigger collapsing and malformed JSON handling
# ---------------------------------------------------------------------------

def test_queue_watcher_ignores_malformed_json(tmp_path):
    """Malformed JSON lines in the queue file should be skipped silently."""
    from wrapper import _queue_watcher, MonitorState

    queue_file = tmp_path / "test_queue.jsonl"
    inject_fn = MagicMock()
    state = MonitorState()

    # Write one valid + one invalid line
    queue_file.write_text(
        'not valid json\n'
        '{"sender": "user", "text": "hello", "time": "00:00:00"}\n'
    )

    # Run one iteration by patching time.sleep to raise after first pass
    call_count = 0

    def fake_sleep(n):
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            raise SystemExit

    with patch("time.sleep", side_effect=fake_sleep):
        with pytest.raises(SystemExit):
            _queue_watcher(queue_file, "claude", inject_fn, {}, state)

    # Valid line should still trigger an inject
    inject_fn.assert_called_once_with("chat - use mcp")


def test_queue_watcher_drains_queue_after_trigger(tmp_path):
    """Queue file should be cleared after processing triggers."""
    from wrapper import _queue_watcher, MonitorState

    queue_file = tmp_path / "test_queue.jsonl"
    inject_fn = MagicMock()
    state = MonitorState()

    queue_file.write_text('{"sender": "user", "text": "ping", "time": "00:00:00"}\n')

    call_count = 0

    def fake_sleep(n):
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            raise SystemExit

    with patch("time.sleep", side_effect=fake_sleep):
        with pytest.raises(SystemExit):
            _queue_watcher(queue_file, "claude", inject_fn, {}, state)

    assert queue_file.read_text() == "", "Queue file should be empty after processing"


def test_queue_watcher_skips_truncated_line_and_logs_warning(tmp_path):
    """A truncated queue line should be warned about and ignored without blocking valid entries."""
    from wrapper import _queue_watcher, MonitorState

    queue_file = tmp_path / "test_queue.jsonl"
    inject_fn = MagicMock()
    state = MonitorState()

    queue_file.write_text(
        '{"sender": "user", "text": "first", "time": "00:00:00"}\n'
        '{"sender": "user", "text": "truncated"\n'
        '{"sender": "user", "text": "second", "time": "00:00:01"}\n'
    )

    call_count = 0

    def fake_sleep(n):
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            raise SystemExit

    with patch("wrapper.log.warning") as mock_warning, \
         patch("time.sleep", side_effect=fake_sleep):
        with pytest.raises(SystemExit):
            _queue_watcher(queue_file, "codex", inject_fn, {}, state)

    inject_fn.assert_called_once_with("chat - use mcp")
    mock_warning.assert_called_once()
    assert "Skipping malformed queue entry for %s: %r" in mock_warning.call_args[0][0]
    assert mock_warning.call_args[0][1] == "codex"
    assert "truncated" in mock_warning.call_args[0][2]


# ---------------------------------------------------------------------------
# run_agent command construction
# ---------------------------------------------------------------------------

def test_run_agent_constructs_resume_command():
    """Verify that extra_args are properly formatted into the agent_cmd."""
    with patch("subprocess.run") as mock_run, \
         patch("shutil.which", return_value="/usr/bin/tmux"):
        from wrapper_unix import run_agent
        
        def fake_start_watcher(inject_fn):
            pass

        # mock_run side effects for the loop: kill-session, new-session, attach-session
        mock_run.side_effect = [
            MagicMock(returncode=0), # tmux kill-session
            MagicMock(returncode=0), # tmux new-session
            KeyboardInterrupt(),     # tmux attach-session (simulating user Ctrl+C)
            MagicMock(returncode=0), # tmux kill-session (in except block)
        ]
        
        run_agent(
            command="gemini",
            extra_args=["--approval-mode", "yolo", "--resume"],
            cwd=".",
            env={},
            queue_file="dummy.jsonl",
            agent="gemini",
            no_restart=True,
            start_watcher=fake_start_watcher
        )

    # Find the new-session call
    new_session_call = next(c for c in mock_run.call_args_list if "new-session" in c[0][0])
    cmd_args = new_session_call[0][0]
    
    # The agent_cmd is the last argument passed to tmux new-session -c <cwd> <cmd>
    agent_cmd = cmd_args[-1]
    
    assert "gemini" in agent_cmd
    assert "--resume" in agent_cmd
    assert "--approval-mode yolo" in agent_cmd


# ---------------------------------------------------------------------------
# Startup queue flushing
# ---------------------------------------------------------------------------

def test_wrapper_main_flushes_queue_file_on_startup(tmp_path):
    """Ensure leftover trigger files from previous runs are deleted when wrapper starts."""
    from wrapper import main

    # Setup dummy data dir and queue file
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    queue_file = data_dir / "claude_queue.jsonl"
    queue_file.write_text("stale_data\n")

    # Write a dummy config.toml
    config_file = tmp_path / "config.toml"
    config_file.write_text('[agents.claude]\ncommand = "claude"\n[server]\ndata_dir = "data"\n')

    with patch("wrapper.ROOT", tmp_path), \
         patch("sys.argv", ["wrapper.py", "claude"]), \
         patch("shutil.which", return_value="/bin/claude"), \
         patch("wrapper.threading.Thread"), \
         patch("sys.platform", "linux"), \
         patch("wrapper_unix.run_agent"):

        main()

    # Check if queue file was cleared
    assert queue_file.read_text() == "", "Queue file should be flushed on wrapper startup"


# ---------------------------------------------------------------------------
# Windows inject — Escape-before-inject parity
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# inject() exit-code detection
# ---------------------------------------------------------------------------

def test_inject_returns_false_on_tmux_failure():
    """inject() returns False and logs a warning when tmux send-keys fails."""
    with patch("subprocess.run") as mock_run, \
         patch("wrapper_unix.log") as mock_log:
        # Make the text send-keys call fail
        def side_effect(cmd, **kwargs):
            if "-l" in cmd:
                return MagicMock(returncode=1)
            return MagicMock(returncode=0)
        mock_run.side_effect = side_effect

        from wrapper_unix import inject
        result = inject("chat - use mcp", tmux_session="agentchattr-gemini")

    assert result is False
    mock_log.warning.assert_called_once()
    warning_msg = mock_log.warning.call_args[0][0]
    assert "failed" in warning_msg.lower()


def test_inject_returns_true_on_success():
    """inject() returns True when all tmux calls succeed."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        from wrapper_unix import inject
        result = inject("chat - use mcp", tmux_session="agentchattr-gemini")

    assert result is True


# ---------------------------------------------------------------------------
# Queue watcher — exception logging
# ---------------------------------------------------------------------------

def test_queue_watcher_logs_exception_on_inject_failure(tmp_path, caplog):
    """queue watcher logs an exception when inject_fn raises, instead of silently swallowing it."""
    import logging
    from wrapper import _queue_watcher, MonitorState

    queue_file = tmp_path / "test_queue.jsonl"
    queue_file.write_text('{"sender": "user", "text": "hello", "time": "00:00:00"}\n')

    def exploding_inject(text):
        raise RuntimeError("boom")

    state = MonitorState()
    call_count = 0

    def fake_sleep(n):
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            raise SystemExit

    with caplog.at_level(logging.ERROR, logger="wrapper"), \
         patch("time.sleep", side_effect=fake_sleep):
        with pytest.raises(SystemExit):
            _queue_watcher(queue_file, "claude", exploding_inject, {}, state)

    assert any("queue watcher error" in r.message for r in caplog.records), \
        "Expected 'queue watcher error' in log output"


# ---------------------------------------------------------------------------
# Windows inject — Escape-before-inject parity
# ---------------------------------------------------------------------------

def test_inject_windows_sends_escape_before_text():
    """Verify windows inject path also sends Escape first."""
    # We must patch sys.platform and WinDLL before importing wrapper_windows
    with patch("sys.platform", "win32"), \
         patch("ctypes.WinDLL", create=True), \
         patch("ctypes.byref"):

        # In case it was already imported/failed
        if "wrapper_windows" in sys.modules:
            del sys.modules["wrapper_windows"]

        import wrapper_windows

        with patch("wrapper_windows._write_key") as mock_write:
            wrapper_windows.inject("test")

            calls = mock_write.call_args_list
            # First two calls to _write_key are for Escape (down/up)
            assert calls[0][0][1] == "\x1b"
            assert calls[0][0][2] is True  # key_down
            assert calls[1][0][1] == "\x1b"
            assert calls[1][0][2] is False  # key_up

            # Check that "test" follows
            assert calls[2][0][1] == "t"


def test_watch_for_server_restart_triggers_on_change(tmp_path):
    """Verify that _watch_for_server_restart kills the session after 2 cycles of a changed timestamp."""
    from wrapper import _watch_for_server_restart
    
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    started_at_file = data_dir / "server_started_at.txt"
    
    # 1. Initial state: server is "running" at time 1000
    started_at_file.write_text("1000.0")
    
    stop_event = MagicMock()
    # is_set() is checked at loop start and after wait(). 
    # Return False enough times to allow 3 full cycles.
    stop_event.is_set.side_effect = [False] * 10 
    
    with patch("subprocess.run") as mock_run:
        def wait_side_effect(timeout):
            if wait_side_effect.call_count == 1:
                # After first cycle wait, change the timestamp
                started_at_file.write_text("2000.0")
            elif wait_side_effect.call_count == 2:
                # After second cycle wait, keep it at 2000.0 to confirm
                pass
            elif wait_side_effect.call_count == 3:
                # After third cycle (restart sent), signal loop stop
                stop_event.is_set.side_effect = [True] * 10
            
            wait_side_effect.call_count += 1
            return False

        wait_side_effect.call_count = 0
        stop_event.wait.side_effect = wait_side_effect
        
        _watch_for_server_restart(data_dir, "test-session", stop_event)

    waited_for = [c.args[0] for c in stop_event.wait.call_args_list[:2]]
    assert waited_for == [10.0, 10.0], f"Expected 10s confirmation cycles, got {waited_for}"

    # Verify kill-session was sent exactly once to the correct session
    kill_calls = [c for c in mock_run.call_args_list if "kill-session" in str(c[0][0])]
    assert len(kill_calls) == 1, f"Expected 1 kill-session call, got {len(kill_calls)}"
    assert "test-session" in kill_calls[0][0][0]


def test_watch_mcp_health_kills_immediately_on_sse_failure():
    """If sse_url is provided, a single probe failure should trigger an immediate kill."""
    from wrapper import _watch_mcp_health
    
    stop_event = MagicMock()
    # is_set() is checked at loop start. Return False, then True to exit after one check.
    stop_event.is_set.side_effect = [False, True]
    
    # wait() is called for grace period (60s) AND at end of loop.
    # Return False for grace period, then True for loop end.
    stop_event.wait.side_effect = [False, True]

    with patch("wrapper._check_sse_health", return_value=False) as mock_check, \
         patch("wrapper._kill_tmux_session") as mock_kill, \
         patch("wrapper._check_mcp_health", return_value=True):
        
        _watch_mcp_health(
            mcp_url="http://127.0.0.1:8200/mcp",
            tmux_session="test-session",
            stop_event=stop_event,
            sse_url="http://127.0.0.1:8201/sse"
        )
        
    mock_check.assert_called_once()
    mock_kill.assert_called_once_with("test-session")


def test_call_mcp_tool_reads_only_first_chunk():
    """Wrapper MCP calls should avoid blocking on stream EOF by reading a bounded chunk."""
    from wrapper import _call_mcp_tool_once

    mock_resp = MagicMock()
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = False
    mock_resp.status = 200
    mock_resp.read.return_value = b"pong"

    with patch("urllib.request.urlopen", return_value=mock_resp):
        ok, body = _call_mcp_tool_once(
            "http://127.0.0.1:8200/mcp",
            "chat_ping",
        )

    assert (ok, body) == (True, "pong")
    mock_resp.read.assert_called_once_with(4096)


def test_check_sse_health_sends_event_stream_accept_header():
    """Gemini SSE health probes must request the SSE media type."""
    from wrapper import _check_sse_health

    mock_resp = MagicMock()
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = False
    mock_resp.status = 200

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        assert _check_sse_health("http://127.0.0.1:8201/sse") is True

    req = mock_urlopen.call_args[0][0]
    assert req.headers["Accept"] == "text/event-stream"
