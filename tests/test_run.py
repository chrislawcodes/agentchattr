"""Tests for run.py — session token persistence and server restart watcher."""

import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Session token persistence
# ---------------------------------------------------------------------------

def test_token_persisted_on_first_run(tmp_path):
    """Token is written to the token file on first run (when no file exists)."""
    token_file = tmp_path / "session_token.txt"

    with patch("run._TOKEN_FILE", token_file), \
         patch("subprocess.run") as mock_proc:
        # Keychain unavailable
        mock_proc.side_effect = Exception("no keychain")
        from run import _stable_session_token
        token = _stable_session_token()

    assert token_file.exists(), "Token file should be created on first run"
    assert token_file.read_text("utf-8").strip() == token


def test_token_reused_on_second_run(tmp_path):
    """Token from a previous run is reused without calling keychain."""
    token_file = tmp_path / "session_token.txt"
    token_file.write_text("deadbeef" * 8, "utf-8")  # 64-char hex

    with patch("run._TOKEN_FILE", token_file), \
         patch("subprocess.run") as mock_proc:
        from run import _stable_session_token
        # Force reimport to use patched _TOKEN_FILE
        import importlib
        import run
        importlib.reload(run)
        with patch("run._TOKEN_FILE", token_file):
            token = run._stable_session_token()

    assert token == "deadbeef" * 8
    mock_proc.assert_not_called()


def test_token_written_even_when_keychain_fails(tmp_path):
    """A random token is persisted even when keychain lookup fails."""
    token_file = tmp_path / "session_token.txt"

    with patch("run._TOKEN_FILE", token_file), \
         patch("subprocess.run", side_effect=Exception("no keychain")):
        from run import _stable_session_token
        token = _stable_session_token()

    assert len(token) == 64  # secrets.token_hex(32) = 64 hex chars
    assert token_file.read_text("utf-8").strip() == token


# ---------------------------------------------------------------------------
# Server restart watcher — C-c only after second consecutive cycle
# ---------------------------------------------------------------------------

def test_server_watch_sends_c_after_second_cycle(tmp_path):
    """kill-session is sent only on the second consecutive 10s cycle with a changed timestamp."""
    from wrapper import _watch_for_server_restart

    started_at = tmp_path / "server_started_at.txt"
    started_at.write_text("100.0", "utf-8")

    stop_event = threading.Event()
    sent_c = []

    def fake_subprocess_run(cmd, **kwargs):
        if "kill-session" in cmd:
            sent_c.append(True)
        return MagicMock(returncode=0)

    # Simulate: file unchanged on first poll, then changed, then same (two cycles)
    call_count = [0]
    original_wait = stop_event.wait

    def fake_wait(timeout):
        call_count[0] += 1
        if call_count[0] == 1:
            # First cycle: change the timestamp (detection)
            started_at.write_text("200.0", "utf-8")
        elif call_count[0] == 2:
            # Second cycle: same new timestamp (confirmation) → restart should fire
            pass
        elif call_count[0] >= 3:
            stop_event.set()
        return stop_event.is_set()

    stop_event.wait = fake_wait

    with patch("subprocess.run", side_effect=fake_subprocess_run):
        _watch_for_server_restart(tmp_path, "agentchattr-test", stop_event)

    assert len(sent_c) == 1, "tmux kill-session should be sent exactly once after second cycle"


def test_server_watch_does_not_send_c_on_first_cycle(tmp_path):
    """tmux kill-session is NOT sent on the first 10s detection cycle after timestamp change."""
    from wrapper import _watch_for_server_restart

    started_at = tmp_path / "server_started_at.txt"
    started_at.write_text("100.0", "utf-8")

    stop_event = threading.Event()
    sent_c = []

    def fake_subprocess_run(cmd, **kwargs):
        if "kill-session" in cmd:
            sent_c.append(True)
        return MagicMock(returncode=0)

    call_count = [0]

    def fake_wait(timeout):
        call_count[0] += 1
        if call_count[0] == 1:
            # First cycle: change timestamp
            started_at.write_text("200.0", "utf-8")
        elif call_count[0] >= 2:
            # Stop before second confirmation cycle
            stop_event.set()
        return stop_event.is_set()

    stop_event.wait = fake_wait

    with patch("subprocess.run", side_effect=fake_subprocess_run):
        _watch_for_server_restart(tmp_path, "agentchattr-test", stop_event)

    assert len(sent_c) == 0, "C-c should NOT be sent on first detection cycle"
