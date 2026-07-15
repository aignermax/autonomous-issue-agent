"""
Unit tests for the bundled Claude Code settings (comment-hygiene commit hook).
"""

import json
from pathlib import Path

import pytest

from src.claude_code import ClaudeCode, default_settings_path


@pytest.fixture
def claude(monkeypatch):
    """ClaudeCode instance without touching the real CLI."""
    monkeypatch.setattr("src.claude_code.find_claude_cli", lambda: "claude")
    monkeypatch.setattr(ClaudeCode, "_verify_installation", lambda self: None)
    return ClaudeCode(working_dir=Path("/tmp"))


class TestBundledSettingsFile:
    def test_settings_file_exists_and_is_valid_json(self):
        path = default_settings_path()
        assert path.exists()
        data = json.loads(path.read_text())
        assert "hooks" in data

    def test_settings_define_agent_hook_on_git_commit(self):
        data = json.loads(default_settings_path().read_text())
        matchers = data["hooks"]["PostToolUse"]
        bash_matcher = next(m for m in matchers if m["matcher"] == "Bash")
        hook = bash_matcher["hooks"][0]
        assert hook["type"] == "agent"
        assert "git commit" in hook["if"]
        assert "commit message" in hook["prompt"]


class TestSettingsFlagInCommands:
    def test_headless_cmd_includes_settings_flag(self, claude):
        cmd = claude._build_headless_cmd("do something")
        idx = cmd.index("--settings")
        assert cmd[idx + 1] == str(default_settings_path())

    def test_interactive_cmd_includes_settings_flag(self, claude):
        cmd = claude._build_interactive_cmd()
        idx = cmd.index("--settings")
        assert cmd[idx + 1] == str(default_settings_path())

    def test_settings_flag_omitted_when_file_missing(self, monkeypatch):
        monkeypatch.setattr("src.claude_code.find_claude_cli", lambda: "claude")
        monkeypatch.setattr(ClaudeCode, "_verify_installation", lambda self: None)
        claude = ClaudeCode(working_dir=Path("/tmp"), settings_file=Path("/nonexistent.json"))
        assert "--settings" not in claude._build_headless_cmd("do something")
        assert "--settings" not in claude._build_interactive_cmd()

    def test_headless_cmd_keeps_existing_flags(self, claude):
        cmd = claude._build_headless_cmd("do something")
        assert "-p" in cmd
        assert "--dangerously-skip-permissions" in cmd
        assert "--output-format" in cmd
