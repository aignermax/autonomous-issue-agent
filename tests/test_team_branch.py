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
