"""
Unit tests for the bundled Claude Code settings (comment-hygiene commit hook).
"""

import json
from pathlib import Path

import pytest

from src.claude_code import ClaudeCode, default_settings_path


@pytest.fixture
def make_claude(monkeypatch):
    """Factory for ClaudeCode instances without touching the real CLI."""
    monkeypatch.setattr("src.claude_code.find_claude_cli", lambda: "claude")
    monkeypatch.setattr(ClaudeCode, "_verify_installation", lambda self: None)

    def _make(working_dir=Path("/tmp"), **kwargs):
        return ClaudeCode(working_dir=working_dir, **kwargs)

    return _make


@pytest.fixture
def claude(make_claude):
    return make_claude()


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


class TestSettingsValidation:
    def test_init_raises_when_settings_file_missing(self, make_claude):
        with pytest.raises(FileNotFoundError):
            make_claude(settings_file=Path("/nonexistent.json"))

    def test_init_raises_on_malformed_settings_json(self, make_claude, tmp_path):
        broken = tmp_path / "broken.json"
        broken.write_text("{ not json")
        with pytest.raises(ValueError):
            make_claude(settings_file=broken)

    def test_init_raises_when_settings_lack_hooks(self, make_claude, tmp_path):
        hookless = tmp_path / "hookless.json"
        hookless.write_text('{"model": "opus"}')
        with pytest.raises(ValueError):
            make_claude(settings_file=hookless)

    def test_settings_flag_omitted_when_explicitly_disabled(self, make_claude):
        claude = make_claude(settings_file=None)
        assert "--settings" not in claude._build_headless_cmd("do something")
        assert "--settings" not in claude._build_interactive_cmd()


class TestSettingsFlagInCommands:
    def test_headless_cmd_includes_settings_flag(self, claude):
        cmd = claude._build_headless_cmd("do something")
        idx = cmd.index("--settings")
        assert cmd[idx + 1] == str(default_settings_path())

    def test_interactive_cmd_includes_settings_flag(self, claude):
        cmd = claude._build_interactive_cmd()
        idx = cmd.index("--settings")
        assert cmd[idx + 1] == str(default_settings_path())

    def test_headless_cmd_keeps_existing_flags(self, claude):
        cmd = claude._build_headless_cmd("do something")
        assert "-p" in cmd
        assert "--dangerously-skip-permissions" in cmd
        assert "--output-format" in cmd

    def test_interactive_cmd_has_no_prompt_flag(self, claude):
        assert "-p" not in claude._build_interactive_cmd()


class TestRelocatedFlags:
    def test_model_flag_present_when_set(self, make_claude):
        cmd = make_claude(model="claude-opus-4-7")._build_headless_cmd("x")
        idx = cmd.index("--model")
        assert cmd[idx + 1] == "claude-opus-4-7"

    def test_model_flag_omitted_by_default(self, claude):
        assert "--model" not in claude._build_headless_cmd("x")

    @pytest.mark.parametrize("build", ["_build_headless_cmd", "_build_interactive_cmd"])
    def test_resume_flag_present_when_file_exists(self, claude, tmp_path, build):
        resume = tmp_path / "session.state"
        resume.write_text("{}")
        args = ("x", resume) if build == "_build_headless_cmd" else (resume,)
        cmd = getattr(claude, build)(*args)
        idx = cmd.index("--resume")
        assert cmd[idx + 1] == str(resume)

    @pytest.mark.parametrize("build", ["_build_headless_cmd", "_build_interactive_cmd"])
    def test_missing_resume_file_omitted_with_warning(self, claude, tmp_path, build, caplog):
        resume = tmp_path / "gone.state"
        args = ("x", resume) if build == "_build_headless_cmd" else (resume,)
        with caplog.at_level("WARNING", logger="agent"):
            cmd = getattr(claude, build)(*args)
        assert "--resume" not in cmd
        assert any("resume" in r.message.lower() for r in caplog.records)

    def test_mcp_config_taken_from_working_dir_parent(self, make_claude, tmp_path):
        working_dir = tmp_path / "repo"
        working_dir.mkdir()
        (tmp_path / ".mcp.json").write_text("{}")
        cmd = make_claude(working_dir=working_dir)._build_interactive_cmd()
        idx = cmd.index("--mcp-config")
        assert cmd[idx + 1] == str(tmp_path / ".mcp.json")

    def test_mcp_config_omitted_when_absent(self, make_claude, tmp_path):
        working_dir = tmp_path / "repo"
        working_dir.mkdir()
        cmd = make_claude(working_dir=working_dir)._build_interactive_cmd()
        assert "--mcp-config" not in cmd
