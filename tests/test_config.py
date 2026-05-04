"""
Unit tests for configuration management.
"""

import os
from pathlib import Path

import pytest

from src.config import Config


class TestConfig:
    """Test Config class."""

    def test_default_configuration(self, monkeypatch):
        """Test loading default configuration."""
        # Set required env vars
        monkeypatch.setenv("GITHUB_TOKEN", "test-token")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

        config = Config()

        assert config.github_token == "test-token"
        assert config.anthropic_api_key == "test-key"
        assert config.poll_interval == 15  # Default is 15 seconds
        assert config.issue_label == "agent-task"
        assert config.complexity_tag == "complex"
        assert config.max_turns_regular == 150
        assert config.max_turns_complex == 500
        assert config.max_tokens_regular == 8000000
        assert config.max_tokens_complex == 15000000
        # Default should be regular limits
        assert config.max_turns == 150

    def test_custom_configuration(self, monkeypatch):
        """Test loading custom configuration from env vars."""
        monkeypatch.setenv("GITHUB_TOKEN", "custom-token")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "custom-key")
        monkeypatch.setenv("AGENT_REPO", "user/custom-repo")
        monkeypatch.setenv("AGENT_POLL_INTERVAL", "600")
        monkeypatch.setenv("AGENT_MAX_TURNS_REGULAR", "200")
        monkeypatch.setenv("AGENT_MAX_TURNS_COMPLEX", "600")
        monkeypatch.setenv("AGENT_ISSUE_LABEL", "custom-label")
        monkeypatch.setenv("AGENT_COMPLEXITY_TAG", "hard")

        config = Config()

        assert config.repo_name == "user/custom-repo"
        assert config.poll_interval == 600
        assert config.max_turns_regular == 200
        assert config.max_turns_complex == 600
        assert config.issue_label == "custom-label"
        assert config.complexity_tag == "hard"

    def test_validate_missing_tokens(self, monkeypatch):
        """Test validation with missing tokens."""
        # Clear env vars
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        config = Config()
        missing = config.validate()

        assert "GITHUB_TOKEN" in missing
        assert "ANTHROPIC_API_KEY" in missing

    def test_validate_complete(self, monkeypatch):
        """Test validation with all required tokens."""
        monkeypatch.setenv("GITHUB_TOKEN", "test-token")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

        config = Config()
        missing = config.validate()

        assert len(missing) == 0

    def test_tools_dir_default_none(self, monkeypatch):
        """tools_dir and tools_python start as None, populated lazily."""
        monkeypatch.setenv("GITHUB_TOKEN", "t")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
        config = Config()
        assert config.tools_dir is None
        assert config.tools_python is None

    def test_session_dir_created(self, tmp_path, monkeypatch):
        """Test that session directory is created."""
        session_dir = tmp_path / "test_sessions"
        monkeypatch.setenv("AGENT_SESSION_DIR", str(session_dir))
        monkeypatch.setenv("GITHUB_TOKEN", "test")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")

        config = Config()

        assert session_dir.exists()
        assert session_dir.is_dir()

    def test_worktree_dir_default(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "t")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
        config = Config()
        assert str(config.worktree_dir).endswith(".aia-worktrees")

    def test_worktree_dir_override(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GITHUB_TOKEN", "t")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
        monkeypatch.setenv("AGENT_WORKTREE_DIR", str(tmp_path / "wt"))
        config = Config()
        assert config.worktree_dir == tmp_path / "wt"

    def test_reviewer_defaults(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "t")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
        c = Config()
        assert c.max_review_rounds == 2
        assert c.reviewer_model_default == "claude-sonnet-4-6"
        assert c.reviewer_model_critical == "claude-opus-4-7"
        assert c.critical_label == "critical"
        assert c.reviewer_max_turns == 50

    def test_reviewer_overrides(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "t")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
        monkeypatch.setenv("AGENT_MAX_REVIEW_ROUNDS", "4")
        monkeypatch.setenv("AGENT_REVIEWER_MODEL", "x")
        c = Config()
        assert c.max_review_rounds == 4
        assert c.reviewer_model_default == "x"
