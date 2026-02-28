"""Tests for run.py — session token persistence."""

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from run import _load_or_create_session_token


def test_token_persisted_on_first_run(tmp_path):
    """Token is written to the token file on first run (when no file exists)."""
    token_file = tmp_path / "session_token.txt"
    token = _load_or_create_session_token(tmp_path)

    assert token_file.exists(), "Token file should be created on first run"
    assert token_file.read_text("utf-8").strip() == token


def test_token_reused_on_second_run(tmp_path):
    """Token from a previous run is reused."""
    token_file = tmp_path / "session_token.txt"
    token_file.write_text("deadbeef" * 8, "utf-8")  # 64-char hex

    token = _load_or_create_session_token(tmp_path)

    assert token == "deadbeef" * 8
