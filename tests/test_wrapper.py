"""Tests for wrapper injection and queue watcher error handling."""

import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


def test_inject_returns_false_on_tmux_failure():
    """inject() returns False and logs a warning when tmux send-keys fails."""
    with patch("subprocess.run") as mock_run, patch("wrapper_unix.log") as mock_log:
        def side_effect(cmd, **kwargs):
            if "-l" in cmd:
                return MagicMock(returncode=1)
            return MagicMock(returncode=0)

        mock_run.side_effect = side_effect

        from wrapper_unix import inject

        result = inject("chat - use mcp", tmux_session="agentchattr-gemini")

    assert result is False
    mock_log.warning.assert_called_once()


def test_inject_returns_true_on_success():
    """inject() returns True when all tmux calls succeed."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)

        from wrapper_unix import inject

        result = inject("chat - use mcp", tmux_session="agentchattr-gemini")

    assert result is True


def test_queue_watcher_logs_exception_on_inject_failure(tmp_path, caplog):
    """Queue watcher logs errors instead of silently swallowing exceptions."""
    from wrapper import _queue_watcher

    queue_file = tmp_path / "test_queue.jsonl"
    queue_file.write_text('{"sender": "user", "channel": "general"}\n')

    def exploding_inject(text):
        raise RuntimeError("boom")

    call_count = 0

    def fake_sleep(_seconds):
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            raise SystemExit

    with caplog.at_level(logging.ERROR, logger="wrapper"), patch("time.sleep", side_effect=fake_sleep):
        with pytest.raises(SystemExit):
            _queue_watcher(queue_file, "claude", exploding_inject)

    assert any("queue watcher error" in record.message for record in caplog.records)


def test_queue_watcher_uses_channel_in_injected_prompt(tmp_path):
    """Queue watcher preserves the queued channel in the injected command."""
    from wrapper import _queue_watcher

    queue_file = tmp_path / "test_queue.jsonl"
    queue_file.write_text('{"sender": "user", "channel": "dev"}\n')
    inject_fn = MagicMock()

    call_count = 0

    def fake_sleep(_seconds):
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            raise SystemExit

    with patch("time.sleep", side_effect=fake_sleep):
        with pytest.raises(SystemExit):
            _queue_watcher(queue_file, "claude", inject_fn)

    inject_fn.assert_called_once_with("mcp read #dev and if addressed respond in the chat")
