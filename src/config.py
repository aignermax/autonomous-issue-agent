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

        # QA-fix loop: cap how many times the coder will retry a PR that
        # QA has rejected before escalating to a human.
        self.max_qa_fix_rounds: int = int(os.environ.get("AGENT_MAX_QA_FIX_ROUNDS", "2"))

        # Reviewer settings. Review rounds depend on issue complexity:
        # regular tasks usually nail it in one pass; complex PRs are worth
        # re-verifying after the worker addresses round-1 feedback.
        # AGENT_MAX_REVIEW_ROUNDS (no suffix) is honored as a legacy override
        # — if set, it wins over the per-complexity values.
        _legacy_rounds = os.environ.get("AGENT_MAX_REVIEW_ROUNDS")
        self.max_review_rounds_regular: int = int(
            os.environ.get("AGENT_MAX_REVIEW_ROUNDS_REGULAR", _legacy_rounds or "1")
        )
        self.max_review_rounds_complex: int = int(
            os.environ.get("AGENT_MAX_REVIEW_ROUNDS_COMPLEX", _legacy_rounds or "2")
        )
        # Kept for callers that haven't migrated; equals the complex value
        # (the more conservative default) when the legacy var is unset.
        self.max_review_rounds: int = int(_legacy_rounds or self.max_review_rounds_complex)
        self.reviewer_model_default: str = os.environ.get(
            "AGENT_REVIEWER_MODEL", "claude-sonnet-4-6")
        self.reviewer_model_critical: str = os.environ.get(
            "AGENT_REVIEWER_MODEL_CRITICAL", "claude-opus-4-7")
        # Coder (worker) model. None => use the Claude Code CLI default.
        # Set AGENT_CODER_MODEL (e.g. "claude-fable-5") to override.
        self.coder_model: Optional[str] = os.environ.get("AGENT_CODER_MODEL") or None

        # PR-feedback role: reacts to human PR comments containing the marker,
        # implements the requested change, and replies with fresh screenshots.
        # Marker-based by design — agent comments post under the same token
        # (same GitHub user), so author filtering cannot tell them apart.
        self.pr_feedback_marker: str = os.environ.get(
            "AGENT_PR_FEEDBACK_MARKER", "@agent")
        self.pr_feedback_max_rounds: int = int(
            os.environ.get("AGENT_PR_FEEDBACK_MAX_ROUNDS", "3"))
        self.pr_feedback_max_turns: int = int(
            os.environ.get("AGENT_PR_FEEDBACK_MAX_TURNS", "120"))
        self.critical_label: str = os.environ.get("AGENT_CRITICAL_LABEL", "critical")
        self.reviewer_max_turns: int = int(os.environ.get("AGENT_REVIEWER_MAX_TURNS", "80"))

        # Test gate: deterministic build/test run before the LLM reviewer
        self.test_gate_enabled: bool = os.environ.get("AGENT_TEST_GATE", "true").lower() == "true"
        self.test_cmd: Optional[str] = os.environ.get("AGENT_TEST_CMD")
        self.test_timeout: int = int(os.environ.get("AGENT_TEST_TIMEOUT", "1800"))

        # Resource limits based on complexity. Budgets need to cover three
        # agents per issue (Worker + Reviewer + QA), each potentially looping:
        # Worker→Reviewer up to MAX_REVIEW_ROUNDS, plus a QA-fix loop up to
        # MAX_QA_FIX_ROUNDS. A single PR review can already burn ~500k
        # tokens, so the multi-role pipeline needs significantly more
        # headroom than the single-agent baseline did.
        # Regular tasks (agent-task only): Simple fixes, docs, small features
        self.max_turns_regular: int = int(os.environ.get("AGENT_MAX_TURNS_REGULAR", "150"))
        self.max_tokens_regular: int = int(os.environ.get("AGENT_MAX_TOKENS_REGULAR", "20000000"))  # 20M tokens

        # Complex tasks (agent-task + complex tag): Full features, refactoring, architecture
        self.max_turns_complex: int = int(os.environ.get("AGENT_MAX_TURNS_COMPLEX", "500"))
        self.max_tokens_complex: int = int(os.environ.get("AGENT_MAX_TOKENS_COMPLEX", "50000000"))  # 50M tokens

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
        """Validate required configuration. Returns list of missing variables."""
        missing = []
        if not self.github_token:
            missing.append("GITHUB_TOKEN")
        if not self.anthropic_api_key:
            missing.append("ANTHROPIC_API_KEY")
        return missing
