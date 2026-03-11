"""
Configuration management for Autonomous Issue Agent.
"""

import os
from pathlib import Path
from typing import Optional


class Config:
    """Application configuration loaded from environment variables."""

    def __init__(self):
        self.repo_name: str = os.environ.get("AGENT_REPO", "aignermax/Connect-A-PIC-Pro")
        self.local_path: Path = Path(os.environ.get("AGENT_REPO_PATH", "./repo"))
        self.branch_prefix: str = "agent/"
        self.poll_interval: int = int(os.environ.get("AGENT_POLL_INTERVAL", "300"))
        self.issue_label: str = os.environ.get("AGENT_ISSUE_LABEL", "agent-task")
        self.max_turns: int = int(os.environ.get("AGENT_MAX_TURNS", "300"))
        self.session_dir: Path = Path(os.environ.get("AGENT_SESSION_DIR", "./.sessions"))

        # Stacked PRs - PRs build on each other instead of all on main
        self.enable_stacked_prs: bool = os.environ.get("AGENT_ENABLE_STACKED_PRS", "false").lower() == "true"

        # Tokens
        self.github_token: Optional[str] = os.environ.get("GITHUB_TOKEN")
        self.anthropic_api_key: Optional[str] = os.environ.get("ANTHROPIC_API_KEY")

        # Ensure session directory exists
        self.session_dir.mkdir(parents=True, exist_ok=True)

    def validate(self) -> list[str]:
        """Validate required configuration. Returns list of missing variables."""
        missing = []
        if not self.github_token:
            missing.append("GITHUB_TOKEN")
        if not self.anthropic_api_key:
            missing.append("ANTHROPIC_API_KEY")
        return missing
