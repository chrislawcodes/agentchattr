import pytest
from unittest.mock import MagicMock, patch
from tmux_cleanup import SessionCleanup


@pytest.fixture
def mock_config():
    return {
        "agents": {
            "claude": {"label": "Claude"},
            "codex": {"label": "Codex"}
        },
        "cleanup": {
            "enabled": True,
            "idle_timeout_minutes": 1,
            "check_interval_seconds": 1
        }
    }


def test_cleanup_kills_stale_session(mock_config):
    mock_store = MagicMock()
    now = 1000.0

    # Patch time.time during construction so _last_online is pre-populated with now
    with patch("time.time", return_value=now):
        cleanup = SessionCleanup(mock_config, store=mock_store)

    assert cleanup._last_online["claude"] == now

    with patch("tmux_cleanup.get_tmux_sessions", return_value=["agentchattr-claude"]), \
         patch("tmux_cleanup.kill_tmux_session") as mock_kill, \
         patch("mcp_bridge.is_online", return_value=False), \
         patch("time.time", return_value=now):

        # First check: agent offline but still within timeout — no kill
        cleanup._check_sessions()
        mock_kill.assert_not_called()

        # Second check: after timeout
        timeout = mock_config["cleanup"]["idle_timeout_minutes"] * 60
        later = now + timeout + 1
        with patch("time.time", return_value=later):
            cleanup._check_sessions()
            mock_kill.assert_called_once_with("agentchattr-claude")
            mock_store.add.assert_called_once()
            assert "Cleaned up stale tmux session for Claude" in mock_store.add.call_args[0][1]


def test_no_agents_killed_on_first_cycle_after_startup(mock_config):
    """Agents are not killed on the first cleanup cycle — _last_online is pre-populated at startup."""
    mock_store = MagicMock()
    now = 1000.0

    with patch("time.time", return_value=now):
        cleanup = SessionCleanup(mock_config, store=mock_store)

    # Both agents should be pre-populated with startup time
    assert cleanup._last_online["claude"] == now
    assert cleanup._last_online["codex"] == now

    # Even if agents appear offline, first cycle should never kill them
    with patch("tmux_cleanup.get_tmux_sessions", return_value=["agentchattr-claude", "agentchattr-codex"]), \
         patch("tmux_cleanup.kill_tmux_session") as mock_kill, \
         patch("mcp_bridge.is_online", return_value=False), \
         patch("time.time", return_value=now):
        cleanup._check_sessions()
        mock_kill.assert_not_called()


def test_cleanup_skips_online_session(mock_config):
    mock_store = MagicMock()
    cleanup = SessionCleanup(mock_config, store=mock_store)
    
    now = 1000.0
    with patch("tmux_cleanup.get_tmux_sessions", return_value=["agentchattr-claude"]), \
         patch("tmux_cleanup.kill_tmux_session") as mock_kill, \
         patch("mcp_bridge.is_online", return_value=True), \
         patch("time.time", return_value=now):
        
        # Initialize
        cleanup._check_sessions()
        
        # After timeout, but still online
        timeout = mock_config["cleanup"]["idle_timeout_minutes"] * 60
        later = now + timeout + 1
        with patch("time.time", return_value=later):
            cleanup._check_sessions()
            mock_kill.assert_not_called()
            assert cleanup._last_online["claude"] == later
