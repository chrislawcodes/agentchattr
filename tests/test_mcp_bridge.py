"""Tests for mcp_bridge — cursor persistence and activity timeout config."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


def _reset_mcp_bridge():
    """Re-import mcp_bridge with a clean slate to avoid state pollution."""
    import importlib
    import mcp_bridge
    importlib.reload(mcp_bridge)
    return mcp_bridge


# ---------------------------------------------------------------------------
# Cursor persistence
# ---------------------------------------------------------------------------

def test_save_and_load_cursors(tmp_path):
    """Cursors saved to disk are restored after clearing in-memory state."""
    import mcp_bridge
    mcp_bridge._CURSORS_FILE = tmp_path / "mcp_cursors.json"
    mcp_bridge._cursors.clear()

    # Populate cursors
    mcp_bridge._cursors["default:claude"] = 42
    mcp_bridge._cursors["default:codex"] = 17

    # Save to disk
    mcp_bridge._save_cursors()

    assert mcp_bridge._CURSORS_FILE.exists()

    # Clear in-memory and reload
    mcp_bridge._cursors.clear()
    mcp_bridge._load_cursors()

    assert mcp_bridge._cursors.get("default:claude") == 42
    assert mcp_bridge._cursors.get("default:codex") == 17


def test_load_cursors_noop_when_file_missing(tmp_path):
    """_load_cursors() is a no-op when the cursors file doesn't exist."""
    import mcp_bridge
    mcp_bridge._CURSORS_FILE = tmp_path / "nonexistent.json"
    mcp_bridge._cursors.clear()
    mcp_bridge._cursors["existing"] = 99

    mcp_bridge._load_cursors()  # should not raise or clear existing

    assert mcp_bridge._cursors.get("existing") == 99


def test_save_cursors_noop_when_file_not_set(tmp_path):
    """_save_cursors() is a no-op when _CURSORS_FILE is None."""
    import mcp_bridge
    original = mcp_bridge._CURSORS_FILE
    mcp_bridge._CURSORS_FILE = None
    mcp_bridge._cursors["foo"] = 1

    mcp_bridge._save_cursors()  # should not raise

    mcp_bridge._CURSORS_FILE = original


# ---------------------------------------------------------------------------
# Activity timeout default
# ---------------------------------------------------------------------------

def test_activity_timeout_default_is_120():
    """ACTIVITY_TIMEOUT should default to 120 seconds (not 30)."""
    import mcp_bridge
    assert mcp_bridge.ACTIVITY_TIMEOUT == 120, (
        f"Expected ACTIVITY_TIMEOUT=120, got {mcp_bridge.ACTIVITY_TIMEOUT}"
    )
