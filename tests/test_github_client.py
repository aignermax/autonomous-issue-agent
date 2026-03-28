"""
Unit tests for GitHub client.
"""

import os
from unittest.mock import Mock, MagicMock, patch

import pytest

from src.github_client import GitHubClient


class TestGitHubClient:
    """Test GitHubClient class."""

    @pytest.fixture
    def mock_github_api(self):
        """Create mocked GitHub API."""
        with patch('src.github_client.Github') as mock_gh_class:
            # Setup mock repository
            mock_repo = Mock()
            mock_repo.default_branch = "main"
            mock_repo.name = "test-repo"

            # Setup mock GitHub instance
            mock_gh = Mock()
            mock_gh.get_repo.return_value = mock_repo
            mock_gh_class.return_value = mock_gh

            yield {
                'github_class': mock_gh_class,
                'github': mock_gh,
                'repo': mock_repo,
            }

    def test_init_with_default_branch(self, mock_github_api, monkeypatch):
        """Test initialization detects default branch."""
        monkeypatch.setenv("GITHUB_TOKEN", "test-token")

        # Set default branch to "dev"
        mock_github_api['repo'].default_branch = "dev"

        client = GitHubClient("owner/repo")

        assert client.repo_name == "owner/repo"
        assert client.default_branch == "dev"
        mock_github_api['github'].get_repo.assert_called_once_with("owner/repo")

    def test_get_pr_by_branch_with_owner_format(self, mock_github_api, monkeypatch):
        """Test get_pr_by_branch uses owner:branch format."""
        monkeypatch.setenv("GITHUB_TOKEN", "test-token")

        # Setup mock PR
        mock_pr = Mock()
        mock_pr.head.ref = "agent/issue-123"
        mock_github_api['repo'].get_pulls.return_value = [mock_pr]

        client = GitHubClient("aignermax/test-repo")
        pr = client.get_pr_by_branch("agent/issue-123")

        # Verify it called with owner:branch format
        mock_github_api['repo'].get_pulls.assert_called_with(
            state="open",
            head="aignermax:agent/issue-123"
        )
        assert pr == mock_pr

    def test_get_pr_by_branch_with_fallback(self, mock_github_api, monkeypatch):
        """Test get_pr_by_branch falls back to manual search."""
        monkeypatch.setenv("GITHUB_TOKEN", "test-token")

        # Setup mock PR
        mock_pr = Mock()
        mock_pr.head.ref = "agent/issue-123"

        # First call raises exception (API format fails)
        # Second call returns PRs for manual search
        mock_github_api['repo'].get_pulls.side_effect = [
            Exception("API error"),
            [mock_pr]  # Fallback returns this
        ]

        client = GitHubClient("owner/repo")
        pr = client.get_pr_by_branch("agent/issue-123")

        # Should have been called twice (once with head param, once without)
        assert mock_github_api['repo'].get_pulls.call_count == 2
        assert pr == mock_pr

    def test_get_pr_by_branch_not_found(self, mock_github_api, monkeypatch):
        """Test get_pr_by_branch returns None when PR not found."""
        monkeypatch.setenv("GITHUB_TOKEN", "test-token")

        # No PRs found
        mock_github_api['repo'].get_pulls.return_value = []

        client = GitHubClient("owner/repo")
        pr = client.get_pr_by_branch("nonexistent-branch")

        assert pr is None

    def test_find_next_issue(self, mock_github_api, monkeypatch):
        """Test finding next issue with label."""
        monkeypatch.setenv("GITHUB_TOKEN", "test-token")

        # Setup mock issues
        mock_issue1 = Mock()
        mock_issue1.number = 123
        mock_issue1.pull_request = None  # Not a PR

        mock_issue2 = Mock()
        mock_issue2.number = 124
        mock_issue2.pull_request = None

        mock_github_api['repo'].get_issues.return_value = [mock_issue1, mock_issue2]

        client = GitHubClient("owner/repo")
        issue = client.find_next_issue("agent-task")

        # Should return first issue
        assert issue == mock_issue1
        mock_github_api['repo'].get_issues.assert_called_once_with(
            state="open",
            labels=["agent-task"],
            sort="created",
            direction="asc"
        )

    def test_find_next_issue_skips_prs(self, mock_github_api, monkeypatch):
        """Test that find_next_issue skips PRs."""
        monkeypatch.setenv("GITHUB_TOKEN", "test-token")

        # First is a PR, second is an issue
        mock_pr = Mock()
        mock_pr.number = 123
        mock_pr.pull_request = Mock()  # Has pull_request attribute

        mock_issue = Mock()
        mock_issue.number = 124
        mock_issue.pull_request = None

        mock_github_api['repo'].get_issues.return_value = [mock_pr, mock_issue]

        client = GitHubClient("owner/repo")
        issue = client.find_next_issue("agent-task")

        # Should skip PR and return issue
        assert issue == mock_issue

    def test_find_next_issue_none_found(self, mock_github_api, monkeypatch):
        """Test find_next_issue returns None when no issues found."""
        monkeypatch.setenv("GITHUB_TOKEN", "test-token")

        mock_github_api['repo'].get_issues.return_value = []

        client = GitHubClient("owner/repo")
        issue = client.find_next_issue("agent-task")

        assert issue is None

    def test_create_pull_request_basic(self, mock_github_api, monkeypatch):
        """Test creating a basic pull request."""
        monkeypatch.setenv("GITHUB_TOKEN", "test-token")

        # Setup mock issue
        mock_issue = Mock()
        mock_issue.number = 123
        mock_issue.title = "Add new feature"

        # Setup mock PR
        mock_pr = Mock()
        mock_pr.html_url = "https://github.com/owner/repo/pull/456"
        mock_github_api['repo'].create_pull.return_value = mock_pr

        client = GitHubClient("owner/repo")
        pr_url = client.create_pull_request(
            branch="agent/issue-123",
            issue=mock_issue,
            base="main"
        )

        assert pr_url == "https://github.com/owner/repo/pull/456"
        mock_github_api['repo'].create_pull.assert_called_once()

        # Verify call arguments
        call_args = mock_github_api['repo'].create_pull.call_args
        assert call_args.kwargs['title'] == "Agent: Add new feature"
        assert call_args.kwargs['head'] == "agent/issue-123"
        assert call_args.kwargs['base'] == "main"
        assert "#123" in call_args.kwargs['body']

    def test_create_pull_request_with_stacking(self, mock_github_api, monkeypatch):
        """Test creating a stacked PR."""
        monkeypatch.setenv("GITHUB_TOKEN", "test-token")

        mock_issue = Mock()
        mock_issue.number = 124
        mock_issue.title = "Second feature"

        mock_pr = Mock()
        mock_pr.html_url = "https://github.com/owner/repo/pull/457"
        mock_github_api['repo'].create_pull.return_value = mock_pr

        client = GitHubClient("owner/repo")
        pr_url = client.create_pull_request(
            branch="agent/issue-124",
            issue=mock_issue,
            base="agent/issue-123",
            previous_pr_number=456
        )

        # Verify stacking warning is in body
        call_args = mock_github_api['repo'].create_pull.call_args
        body = call_args.kwargs['body']
        assert "Stacked PR" in body
        assert "#456" in body

    def test_create_pull_request_with_summary(self, mock_github_api, monkeypatch):
        """Test creating PR with Claude Code summary."""
        monkeypatch.setenv("GITHUB_TOKEN", "test-token")

        mock_issue = Mock()
        mock_issue.number = 123
        mock_issue.title = "Fix bug"

        mock_pr = Mock()
        mock_pr.html_url = "https://github.com/owner/repo/pull/456"
        mock_github_api['repo'].create_pull.return_value = mock_pr

        client = GitHubClient("owner/repo")
        pr_url = client.create_pull_request(
            branch="agent/issue-123",
            issue=mock_issue,
            summary="## Changes\n- Fixed null reference\n- Added tests",
            body_suffix="## Stats\nTokens: 1000"
        )

        call_args = mock_github_api['repo'].create_pull.call_args
        body = call_args.kwargs['body']
        assert "## Changes" in body
        assert "Fixed null reference" in body
        assert "## Stats" in body
        assert "Tokens: 1000" in body

    def test_close_issue(self, mock_github_api, monkeypatch):
        """Test closing an issue with PR link."""
        monkeypatch.setenv("GITHUB_TOKEN", "test-token")

        mock_issue = Mock()
        pr_url = "https://github.com/owner/repo/pull/456"

        client = GitHubClient("owner/repo")
        client.close_issue(mock_issue, pr_url)

        # Verify comment was added
        mock_issue.create_comment.assert_called_once()
        comment = mock_issue.create_comment.call_args[0][0]
        assert pr_url in comment
        assert "complete" in comment.lower()

        # Verify issue was closed
        mock_issue.edit.assert_called_once_with(state="closed")

    def test_add_issue_comment(self, mock_github_api, monkeypatch):
        """Test adding a comment to an issue."""
        monkeypatch.setenv("GITHUB_TOKEN", "test-token")

        mock_issue = Mock()

        client = GitHubClient("owner/repo")
        client.add_issue_comment(mock_issue, "Test comment")

        mock_issue.create_comment.assert_called_once_with("Test comment")


class TestGitHubClientErrorHandling:
    """Test error handling in GitHubClient."""

    def test_pr_already_exists_scenario(self, monkeypatch):
        """
        Integration test: Simulate the Issue #319 bug scenario.
        When PR already exists, get_pr_by_branch should find it.
        """
        monkeypatch.setenv("GITHUB_TOKEN", "test-token")

        with patch('src.github_client.Github') as mock_gh_class:
            # Setup mocks
            mock_repo = Mock()
            mock_repo.default_branch = "main"

            existing_pr = Mock()
            existing_pr.number = 322
            existing_pr.head.ref = "agent/issue-319-1774683470"
            existing_pr.html_url = "https://github.com/owner/repo/pull/322"

            # First call with head param succeeds and returns the existing PR
            mock_repo.get_pulls.return_value = [existing_pr]

            mock_gh = Mock()
            mock_gh.get_repo.return_value = mock_repo
            mock_gh_class.return_value = mock_gh

            # Test the scenario
            client = GitHubClient("aignermax/Connect-A-PIC-Pro")
            found_pr = client.get_pr_by_branch("agent/issue-319-1774683470")

            # Agent should find the existing PR
            assert found_pr is not None
            assert found_pr.number == 322
            assert found_pr.html_url == "https://github.com/owner/repo/pull/322"

            # Verify correct API call format
            mock_repo.get_pulls.assert_called_with(
                state="open",
                head="aignermax:agent/issue-319-1774683470"
            )
