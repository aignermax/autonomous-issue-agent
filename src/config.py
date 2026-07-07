"""
Configuration management for Autonomous Issue Agent.
"""

import os
from pathlib import Path
from typing import Optional


class Config:
    """Application configuration loaded from environment variables."""

    def __init__(self):
        # Multi-repository support: AGENT_REPOS (comma-separated) or single AGENT_REPO
        repos_str = os.environ.get("AGENT_REPOS", "")
        if repos_str:
            # Multi-repo mode: "owner/repo1,owner/repo2,owner/repo3"
            self.repo_names: list[str] = [r.strip() for r in repos_str.split(",") if r.strip()]
        else:
            # Single repo mode (backwards compatible)
            single_repo = os.environ.get("AGENT_REPO", "aignermax/Connect-A-PIC-Pro")
            self.repo_names: list[str] = [single_repo]

        # Legacy single repo support
        self.repo_name: str = self.repo_names[0]  # First repo for backwards compatibility

        self.local_path: Path = Path(os.environ.get("AGENT_REPO_PATH", "./repo"))
        self.branch_prefix: str = "agent/"
        self.poll_interval: int = int(os.environ.get("AGENT_POLL_INTERVAL", "15"))

        # Issue activation label: Single label to trigger agent work
        self.issue_label: str = os.environ.get("AGENT_ISSUE_LABEL", "agent-task")

        # Complexity modifier tag: Presence of this tag activates higher limits
        self.complexity_tag: str = os.environ.get("AGENT_COMPLEXITY_TAG", "complex")

        self.session_dir: Path = Path(os.environ.get("AGENT_SESSION_DIR", "./.sessions"))

        # Tools install (auto-detected via tools_bootstrap; lazy init in Agent)
        self.tools_dir: Optional[Path] = None
        self.tools_python: Optional[Path] = None

        # Worker (implementer) model + reasoning effort. Applied to every
        # ClaudeCode session across all repos. Default to the best model at
        # maximum practical effort; override via env for cheaper runs.
        self.worker_model: str = os.environ.get("AGENT_WORKER_MODEL", "claude-opus-4-8")
        self.effort: str = os.environ.get("AGENT_EFFORT", "xhigh")

        # Usage guardrail — rolling token budgets protecting the Claude
        # subscription's 5-hour and 7-day limits. The agent pauses picking up
        # NEW issues once a window's budget is reached (in-flight work finishes),
        # and also backs off if the CLI reports a real limit. Set 0 to disable a
        # window. These are conservative starting points — TUNE to your plan.
        self.limit_5h_tokens: int = int(os.environ.get("AGENT_LIMIT_5H_TOKENS", "40000000"))
        self.limit_7d_tokens: int = int(os.environ.get("AGENT_LIMIT_7D_TOKENS", "250000000"))
        # Fallback backoff when the CLI reports a limit but gives no reset time.
        self.limit_backoff_seconds: int = int(os.environ.get("AGENT_LIMIT_BACKOFF_SECONDS", "3600"))
        self.usage_ledger_path: Path = self.session_dir / "usage-ledger.json"

        # Reviewer settings
        self.max_review_rounds: int = int(os.environ.get("AGENT_MAX_REVIEW_ROUNDS", "2"))
        self.reviewer_model_default: str = os.environ.get(
            "AGENT_REVIEWER_MODEL", "claude-sonnet-4-6")
        self.reviewer_model_critical: str = os.environ.get(
            "AGENT_REVIEWER_MODEL_CRITICAL", "claude-opus-4-8")
        self.critical_label: str = os.environ.get("AGENT_CRITICAL_LABEL", "critical")
        self.reviewer_max_turns: int = int(os.environ.get("AGENT_REVIEWER_MAX_TURNS", "50"))

        # Test gate: deterministic build/test run before the LLM reviewer
        self.test_gate_enabled: bool = os.environ.get("AGENT_TEST_GATE", "true").lower() == "true"
        self.test_cmd: Optional[str] = os.environ.get("AGENT_TEST_CMD")
        self.test_timeout: int = int(os.environ.get("AGENT_TEST_TIMEOUT", "1800"))

        # Resource limits based on complexity
        # Regular tasks (agent-task only): Simple fixes, docs, small features
        self.max_turns_regular: int = int(os.environ.get("AGENT_MAX_TURNS_REGULAR", "150"))
        self.max_tokens_regular: int = int(os.environ.get("AGENT_MAX_TOKENS_REGULAR", "8000000"))  # 8M tokens ≈ €24-40

        # Complex tasks (agent-task + complex tag): Full features, refactoring, architecture
        self.max_turns_complex: int = int(os.environ.get("AGENT_MAX_TURNS_COMPLEX", "500"))
        self.max_tokens_complex: int = int(os.environ.get("AGENT_MAX_TOKENS_COMPLEX", "15000000"))  # 15M tokens ≈ €45-75

        # Defaults (will be overridden per issue based on complexity tag)
        self.max_turns: int = self.max_turns_regular
        self.max_tokens_per_issue: int = self.max_tokens_regular

        # Stacked PRs - PRs build on each other instead of all on main
        self.enable_stacked_prs: bool = os.environ.get("AGENT_ENABLE_STACKED_PRS", "false").lower() == "true"

        # Tokens
        self.github_token: Optional[str] = os.environ.get("GITHUB_TOKEN")
        self.anthropic_api_key: Optional[str] = os.environ.get("ANTHROPIC_API_KEY")

        # Ensure session directory exists
        self.session_dir.mkdir(parents=True, exist_ok=True)

        # Worktree base directory (one subdir per repo+branch)
        self.worktree_dir: Path = Path(
            os.environ.get("AGENT_WORKTREE_DIR", "~/.aia-worktrees")
        ).expanduser()

    def validate(self) -> list[str]:
        """Validate required configuration. Returns list of missing variables.

        ANTHROPIC_API_KEY is intentionally not required: this agent shells out to
        the Claude Code CLI, which authenticates via OAuth (`claude login`)
        against a Claude Pro/Max subscription. Setting ANTHROPIC_API_KEY can make
        the CLI prefer per-token API billing over the subscription.
        """
        missing = []
        if not self.github_token:
            missing.append("GITHUB_TOKEN")
        return missing
