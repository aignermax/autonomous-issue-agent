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
        assert config.max_turns == 300
        assert config.issue_label == "agent-task"

    def test_custom_configuration(self, monkeypatch):
        """Test loading custom configuration from env vars."""
        monkeypatch.setenv("GITHUB_TOKEN", "custom-token")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "custom-key")
        monkeypatch.setenv("AGENT_REPO", "user/custom-repo")
        monkeypatch.setenv("AGENT_POLL_INTERVAL", "600")
        monkeypatch.setenv("AGENT_MAX_TURNS", "500")
        monkeypatch.setenv("AGENT_ISSUE_LABEL", "custom-label")

        config = Config()

        assert config.repo_name == "user/custom-repo"
        assert config.poll_interval == 600
        assert config.max_turns == 500
        assert config.issue_label == "custom-label"

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

    def test_session_dir_created(self, tmp_path, monkeypatch):
        """Test that session directory is created."""
        session_dir = tmp_path / "test_sessions"
        monkeypatch.setenv("AGENT_SESSION_DIR", str(session_dir))
        monkeypatch.setenv("GITHUB_TOKEN", "test")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")

        config = Config()

        assert session_dir.exists()
        assert session_dir.is_dir()
