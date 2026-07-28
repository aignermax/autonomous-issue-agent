"""Tests for the per-issue team base branch (issue form field "Team branch")."""

import sys
import types
from unittest.mock import MagicMock

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


def _agent():
    from src.agent import Agent

    return Agent.__new__(Agent)


def _issue(body):
    issue = MagicMock()
    issue.body = body
    return issue


class TestExtractTeamBranch:
    def test_issue_form_heading(self):
        body = "### Problem\n\nLaser drifts.\n\n### Team branch\n\nteam/photon\n\n### Non-goals\n\nnone"
        assert _agent()._extract_team_branch_from_issue(_issue(body)) == "team/photon"

    def test_inline_team_branch(self):
        assert _agent()._extract_team_branch_from_issue(_issue("Team branch: team/photon")) == "team/photon"

    def test_inline_base_branch(self):
        assert _agent()._extract_team_branch_from_issue(_issue("base branch = team/alpha")) == "team/alpha"

    def test_markdown_formatting_is_stripped(self):
        assert _agent()._extract_team_branch_from_issue(_issue("Team branch: `team/photon`")) == "team/photon"

    def test_no_response_placeholder_returns_none(self):
        body = "### Team branch\n\n_No response_"
        assert _agent()._extract_team_branch_from_issue(_issue(body)) is None

    def test_missing_field_returns_none(self):
        assert _agent()._extract_team_branch_from_issue(_issue("### Problem\n\njust text")) is None

    def test_empty_body_returns_none(self):
        assert _agent()._extract_team_branch_from_issue(_issue(None)) is None

    def test_form_heading_does_not_leak_into_work_branch_extractor(self):
        """The legacy 'branch:' extractor must not misread the form field as
        the agent's own work branch."""
        body = "### Team branch\n\nteam/photon"
        assert _agent()._extract_branch_from_issue(_issue(body)) is None

    def test_inline_forms_do_not_leak_into_work_branch_extractor(self):
        """Review finding: 'Team branch: x' matched the legacy 'branch:'
        pattern and 'base branch = x' matched 'branch=', making the agent
        commit directly to the team branch."""
        agent = _agent()
        assert agent._extract_branch_from_issue(_issue("Team branch: team/photon")) is None
        assert agent._extract_branch_from_issue(_issue("base branch = team/alpha")) is None
        # ...while a genuine work-branch directive still works alongside one:
        body = "Team branch: team/photon\n\nWork on branch: feature/xyz"
        assert agent._extract_branch_from_issue(_issue(body)) == "feature/xyz"
        assert agent._extract_team_branch_from_issue(_issue(body)) == "team/photon"

    def test_leading_dash_value_is_rejected(self):
        """Review finding: a value like '-x' would be parsed as a git option."""
        assert _agent()._extract_team_branch_from_issue(_issue("Team branch: -evil")) is None


class TestGetBaseBranch:
    def test_team_branch_wins(self):
        agent = _agent()
        # No config/git access needed when the issue declares a team branch.
        assert agent._get_base_branch(_issue("### Team branch\n\nteam/photon")) == "team/photon"

    def test_falls_back_to_working_branch_without_team_branch(self):
        agent = _agent()
        agent.config = MagicMock()
        agent.config.enable_stacked_prs = False
        agent.git = MagicMock()
        agent.git.get_working_branch.return_value = "dev"
        assert agent._get_base_branch(_issue("### Problem\n\nno branch here")) == "dev"

    def test_no_issue_keeps_legacy_behavior(self):
        agent = _agent()
        agent.config = MagicMock()
        agent.config.enable_stacked_prs = False
        agent.git = MagicMock()
        agent.git.get_working_branch.return_value = "main"
        assert agent._get_base_branch() == "main"


def _git_run_stub(push_rc):
    """git.run stub: branch missing on origin, push returns `push_rc`."""
    def run(*args, **kwargs):
        if args[0] == "ls-remote":
            return MagicMock(returncode=0, stdout="")  # branch missing
        if args[0] == "push":
            return MagicMock(returncode=push_rc, stdout="", stderr="denied")
        return MagicMock(returncode=0, stdout="ok", stderr="")
    return run


class TestMissingTeamBranch:
    """A missing team branch is created automatically from the working
    branch (dev → main fallback); only a failed creation escalates."""

    def _agent_with_mocks(self, push_rc):
        agent = _agent()
        agent.config = MagicMock()
        agent.config.issue_label = "agent-task"
        agent.git = MagicMock()
        agent.git.run.side_effect = _git_run_stub(push_rc)
        agent.git.get_working_branch.return_value = "main"
        agent._release_assignee_lock = MagicMock()
        return agent

    def _issue(self):
        issue = MagicMock()
        issue.number = 9
        issue.body = "### Team branch\n\nteam/fresh"
        issue.title = "t"
        issue.labels = []
        return issue

    def test_missing_branch_is_created_from_working_branch(self):
        agent = self._agent_with_mocks(push_rc=0)
        issue = self._issue()

        assert agent._ensure_team_branch_exists(issue, "team/fresh") is True
        push_calls = [c for c in agent.git.run.call_args_list if c.args[0] == "push"]
        assert push_calls == [
            (("push", "origin", "origin/main:refs/heads/team/fresh"),)]
        issue.create_comment.assert_called_once()  # creation announced
        issue.add_to_labels.assert_not_called()    # no escalation
        agent._release_assignee_lock.assert_not_called()

    def test_failed_creation_escalates_once(self):
        agent = self._agent_with_mocks(push_rc=1)
        issue = self._issue()

        assert agent._ensure_team_branch_exists(issue, "team/fresh") is False
        issue.create_comment.assert_called_once()
        issue.add_to_labels.assert_called_once_with("needs-human")
        agent._release_assignee_lock.assert_called_once()

    def test_failed_creation_stops_process_issue_without_rollback_loop(self):
        agent = self._agent_with_mocks(push_rc=1)
        agent.session_manager = MagicMock()
        agent.session_manager.load_state.return_value = None
        agent.worktrees = MagicMock()
        agent._claim_issue_and_create_branch = MagicMock(return_value="agent/issue-9-x")
        agent._rollback_claim = MagicMock()
        issue = self._issue()

        result = agent.process_issue(issue)

        assert result.success is False
        # crucial: NOT the transient-rollback path (which re-adds agent-task)
        agent._rollback_claim.assert_not_called()
        agent.worktrees.create.assert_not_called()

    def test_existing_branch_short_circuits(self):
        agent = self._agent_with_mocks(push_rc=1)  # push would fail, but…
        agent.git.run.side_effect = None
        agent.git.run.return_value = MagicMock(returncode=0, stdout="ref exists")
        issue = self._issue()
        assert agent._ensure_team_branch_exists(issue, "team/fresh") is True
        issue.create_comment.assert_not_called()  # nothing to announce
