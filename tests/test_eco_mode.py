"""Tests for eco mode (label → cheap provider for coder sessions)."""
from types import SimpleNamespace
from unittest.mock import MagicMock

from tests.test_team_branch import _agent  # reuses the github stub setup


def _issue_with_labels(*names):
    issue = MagicMock()
    issue.number = 5
    issue.labels = [SimpleNamespace(name=n) for n in names]
    return issue


def _eco_agent(api_key="sk-kimi"):
    agent = _agent()
    agent.config = MagicMock()
    agent.config.eco_tag = "eco"
    agent.config.eco_model = "kimi-k2-thinking"
    agent.config.eco_base_url = "https://api.moonshot.ai/anthropic"
    agent.config.eco_api_key = api_key
    agent.config.coder_model = "claude-fable-5"
    return agent


class TestWorkerProvider:
    def test_eco_label_switches_provider(self):
        model, env = _eco_agent()._worker_provider(_issue_with_labels("agent-task", "ECO"))
        assert model == "kimi-k2-thinking"
        assert env["ANTHROPIC_BASE_URL"] == "https://api.moonshot.ai/anthropic"
        assert env["ANTHROPIC_AUTH_TOKEN"] == "sk-kimi"
        assert env["ANTHROPIC_SMALL_FAST_MODEL"] == "kimi-k2-thinking"

    def test_without_label_uses_default(self):
        model, env = _eco_agent()._worker_provider(_issue_with_labels("agent-task"))
        assert model == "claude-fable-5"
        assert env == {}

    def test_missing_key_falls_back_with_default_provider(self):
        model, env = _eco_agent(api_key=None)._worker_provider(_issue_with_labels("eco"))
        assert model == "claude-fable-5"
        assert env == {}

    def test_none_issue_is_default(self):
        model, env = _eco_agent()._worker_provider(None)
        assert model == "claude-fable-5"
        assert env == {}


class TestClaudeCodeEnvOverrides:
    def test_overrides_are_stored_and_copied(self, monkeypatch):
        import src.claude_code as cc
        monkeypatch.setattr(cc, "find_claude_cli", lambda: "claude")
        monkeypatch.setattr(cc.ClaudeCode, "_verify_installation", lambda self: None)
        overrides = {"ANTHROPIC_BASE_URL": "https://api.moonshot.ai/anthropic"}
        runner = cc.ClaudeCode(
            working_dir=None, model="kimi-k2-thinking",
            settings_file=None, env_overrides=overrides)
        assert runner.env_overrides == overrides
        overrides["ANTHROPIC_BASE_URL"] = "mutated"
        assert runner.env_overrides["ANTHROPIC_BASE_URL"] == "https://api.moonshot.ai/anthropic"

    def test_default_is_empty(self, monkeypatch):
        import src.claude_code as cc
        monkeypatch.setattr(cc, "find_claude_cli", lambda: "claude")
        monkeypatch.setattr(cc.ClaudeCode, "_verify_installation", lambda self: None)
        runner = cc.ClaudeCode(working_dir=None, settings_file=None)
        assert runner.env_overrides == {}
