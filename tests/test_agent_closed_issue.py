"""Test closed-issue early-return path in _process_issue_in_worktree."""

import sys
import types
from unittest.mock import MagicMock
from pathlib import Path

# Same github stub pattern used by test_agent_count_tool_usage.py
for mod_name in ("github", "github.Auth"):
    if mod_name not in sys.modules:
        sys.modules[mod_name] = types.ModuleType(mod_name)

github_mod = sys.modules["github"]
if not hasattr(github_mod, "Github"):
    github_mod.Github = MagicMock()
if not hasattr(github_mod, "Auth"):
    auth_mod = sys.modules.get("github.Auth") or types.ModuleType("github.Auth")
    auth_mod.Token = MagicMock()
    sys.modules["github.Auth"] = auth_mod
    github_mod.Auth = auth_mod


class TestClosedIssue:
    def test_closed_issue_returns_failure_does_not_raise(self):
        """A closed issue must not raise TypeError; should return IssueResult."""
        from src.agent import Agent, IssueResult

        agent = Agent.__new__(Agent)
        # Set up the minimum the closed-issue path needs.
        agent.config = MagicMock()
        agent.config.complexity_tag = "complex"
        agent.config.max_turns_regular = 100
        agent.config.max_tokens_regular = 1_000_000
        agent.config.max_turns_complex = 200
        agent.config.max_tokens_complex = 2_000_000
        agent.git = MagicMock()
        agent.github = MagicMock()
        agent.session_manager = MagicMock()
        agent.session_manager.load_state.return_value = None

        issue = MagicMock()
        issue.number = 42
        issue.state = "closed"
        issue.labels = []

        # _process_issue_in_worktree is the method that contains the early-exit
        result = agent._process_issue_in_worktree(
            issue=issue, branch="agent/issue-42", worktree_path=Path("/tmp/x"),
        )

        assert isinstance(result, IssueResult)
        assert result.success is False
        assert "closed" in (result.error or "").lower()
