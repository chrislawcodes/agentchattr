"""Tests for mcp_bridge cursor persistence."""

import os
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


def test_save_cursors_writes_file_atomically(tmp_path):
    """_save_cursors writes the temp file, then renames it into place."""
    import mcp_bridge

    mcp_bridge._CURSORS_FILE = tmp_path / "mcp_cursors.json"
    mcp_bridge._cursors.clear()
    mcp_bridge._cursors["default:claude"] = 42
    mcp_bridge._cursors["default:codex"] = 17

    real_replace = os.replace

    def checked_replace(src, dst):
        src_path = Path(src)
        dst_path = Path(dst)
        assert src_path.name == "mcp_cursors.tmp"
        assert dst_path == mcp_bridge._CURSORS_FILE
        assert src_path.exists()
        saved = src_path.read_text("utf-8")
        assert '"default:claude": 42' in saved
        assert '"default:codex": 17' in saved
        real_replace(src, dst)

    with patch("os.replace", side_effect=checked_replace) as mock_replace:
        mcp_bridge._save_cursors()

    mock_replace.assert_called_once()
    assert mcp_bridge._CURSORS_FILE.exists()


def test_load_cursors_reads_file_back_correctly(tmp_path):
    """_load_cursors restores persisted cursor values into memory."""
    import mcp_bridge

    mcp_bridge._CURSORS_FILE = tmp_path / "mcp_cursors.json"
    mcp_bridge._CURSORS_FILE.write_text(
        '{"default:claude": 42, "default:codex": 17}',
        "utf-8",
    )
    mcp_bridge._cursors.clear()

    mcp_bridge._load_cursors()

    assert mcp_bridge._cursors.get("default:claude") == 42
    assert mcp_bridge._cursors.get("default:codex") == 17


def test_load_cursors_noop_when_file_missing(tmp_path):
    """_load_cursors is a no-op when the cursors file does not exist."""
    import mcp_bridge

    mcp_bridge._CURSORS_FILE = tmp_path / "missing.json"
    mcp_bridge._cursors.clear()
    mcp_bridge._cursors["existing"] = 99

    mcp_bridge._load_cursors()

    assert mcp_bridge._cursors.get("existing") == 99


def test_save_cursors_noop_when_file_not_set():
    """_save_cursors is a no-op when _CURSORS_FILE is None."""
    import mcp_bridge

    original = mcp_bridge._CURSORS_FILE
    mcp_bridge._CURSORS_FILE = None
    mcp_bridge._cursors["foo"] = 1

    with patch("os.replace") as mock_replace:
        mcp_bridge._save_cursors()

    mock_replace.assert_not_called()
    mcp_bridge._CURSORS_FILE = original
