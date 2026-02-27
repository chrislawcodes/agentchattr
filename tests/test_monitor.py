import time
import pytest
from unittest.mock import MagicMock, patch
from wrapper import _task_monitor, MonitorState


def test_monitor_triggers_on_stale_queue(tmp_path):
    """Monitor should re-inject if queue is non-empty and no activity for >timeout."""
    queue_file = tmp_path / "test_queue.jsonl"
    queue_file.write_text('{"trigger": true}\n')
    
    inject_fn = MagicMock()
    state = MonitorState()
    
    # Set last inject to 10 minutes ago
    state.last_inject_at = time.time() - 600
    
    # Patch time.sleep to run only once
    with patch("time.sleep", side_effect=[None, SystemExit]):
        with pytest.raises(SystemExit):
            _task_monitor(queue_file, inject_fn, state, timeout_minutes=5.0)
            
    inject_fn.assert_called_once_with("chat - use mcp")
    # Verify it updated the timestamp
    assert time.time() - state.get_last_inject() < 10


def test_monitor_skips_if_queue_empty(tmp_path):
    """Monitor should do nothing if the queue is empty."""
    queue_file = tmp_path / "test_queue.jsonl"
    queue_file.write_text("")
    
    inject_fn = MagicMock()
    state = MonitorState()
    state.last_inject_at = time.time() - 600
    
    with patch("time.sleep", side_effect=[None, SystemExit]):
        with pytest.raises(SystemExit):
            _task_monitor(queue_file, inject_fn, state, timeout_minutes=5.0)
            
    inject_fn.assert_not_called()


def test_monitor_skips_if_recent_activity(tmp_path):
    """Monitor should do nothing if there was recent activity, even if queue is non-empty."""
    queue_file = tmp_path / "test_queue.jsonl"
    queue_file.write_text('{"trigger": true}\n')
    
    inject_fn = MagicMock()
    state = MonitorState()
    
    # Recent activity (1 minute ago)
    state.last_inject_at = time.time() - 60
    
    with patch("time.sleep", side_effect=[None, SystemExit]):
        with pytest.raises(SystemExit):
            _task_monitor(queue_file, inject_fn, state, timeout_minutes=5.0)
            
    inject_fn.assert_not_called()
