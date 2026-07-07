"""Regression tests for _claim_issue_and_create_branch lock independence.

Bug: label removal, assignment, and the claim comment shared one try/except,
so a transient GitHub 404/5xx on label removal aborted the whole claim — the
issue was left unassigned AND still labelled, and got re-picked/re-run on the
next poll cycle (duplicate PR + duplicate spend).

Fix: assignment (the durable lock) runs first, and each operation has its own
try/except so one failing never skips the others.
"""

import sys
import types
from unittest.mock import MagicMock

# Same github stub pattern used by the other agent tests.
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


def _make_agent():
    from src.agent import Agent

    agent = Agent.__new__(Agent)
    agent.config = MagicMock()
    agent.config.issue_label = "agent-task"
    agent.github = MagicMock()
    agent.github.repo.owner.login = "bot"
    # Short-circuit branch determination so the test targets only the claim.
    agent._extract_branch_from_issue = MagicMock(return_value="agent/issue-7")
    return agent


def _make_issue():
    issue = MagicMock()
    issue.number = 7
    issue.assignees = []  # not yet claimed
    return issue


class TestClaimLock:
    def test_label_removal_failure_still_assigns(self):
        """A 404 on label removal must NOT skip the assignment lock."""
        agent = _make_agent()
        issue = _make_issue()
        issue.remove_from_labels.side_effect = Exception("Label does not exist: 404")

        branch = agent._claim_issue_and_create_branch(issue)

        # The durable lock (assignment) must have been applied despite the label error.
        issue.add_to_assignees.assert_called_once_with("bot")
        assert branch == "agent/issue-7"

    def test_assignment_failure_still_removes_label(self):
        """An assignment failure must NOT skip label removal."""
        agent = _make_agent()
        issue = _make_issue()
        issue.add_to_assignees.side_effect = Exception("403 forbidden")

        agent._claim_issue_and_create_branch(issue)

        issue.remove_from_labels.assert_called_once_with("agent-task")

    def test_already_assigned_skips_reassign_and_comment(self):
        """If already assigned to the bot, don't re-assign or re-comment."""
        agent = _make_agent()
        issue = _make_issue()
        me = MagicMock()
        me.login = "bot"
        issue.assignees = [me]

        agent._claim_issue_and_create_branch(issue)

        issue.add_to_assignees.assert_not_called()
        issue.create_comment.assert_not_called()
        # Label removal still runs so the issue leaves the pending queue.
        issue.remove_from_labels.assert_called_once_with("agent-task")

    def test_happy_path_assigns_removes_and_comments(self):
        agent = _make_agent()
        issue = _make_issue()

        agent._claim_issue_and_create_branch(issue)

        issue.add_to_assignees.assert_called_once_with("bot")
        issue.remove_from_labels.assert_called_once_with("agent-task")
        issue.create_comment.assert_called_once()
