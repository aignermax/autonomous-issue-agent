"""Tests for Agent._run_review_loop."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from src.reviewer import ReviewResult, Finding


class TestRunReviewLoop:
    """Test the Worker → Reviewer iteration loop in isolation."""

    def _make_agent(self, max_review_rounds=2, default_branch="main"):
        from src.agent import Agent
        agent = Agent.__new__(Agent)
        agent.config = MagicMock()
        agent.config.max_review_rounds = max_review_rounds
        agent.config.tools_dir = Path("/tmp/tools")
        agent.config.tools_python = Path("/tmp/venv/bin/python3")
        agent.config.reviewer_model_default = "sonnet"
        agent.config.reviewer_model_critical = "opus"
        agent.config.critical_label = "critical"
        agent.config.reviewer_max_turns = 30
        agent.config.max_turns_regular = 100
        agent.config.max_turns_complex = 200
        agent.config.max_tokens_regular = 1_000_000
        agent.config.max_tokens_complex = 2_000_000
        agent.config.complexity_tag = "complex"
        agent.git = MagicMock()
        agent.git.default_branch = default_branch
        agent.github = MagicMock()
        return agent

    def test_loop_exits_on_first_ok(self, tmp_path):
        agent = self._make_agent(max_review_rounds=2)
        issue = MagicMock(); issue.labels = []
        pr = MagicMock(number=1)

        ok_result = ReviewResult(verdict="OK", summary="all good")

        with patch("src.agent.Reviewer") as MockReviewer:
            instance = MockReviewer.return_value
            instance.review.return_value = ok_result

            result = agent._run_review_loop(issue=issue, pr=pr, branch="agent/issue-1",
                                            worktree_path=tmp_path)

            assert instance.review.call_count == 1
            assert result is False

    def test_loop_runs_worker_retry_on_blocking(self, tmp_path):
        agent = self._make_agent(max_review_rounds=2)
        issue = MagicMock(); issue.labels = []
        pr = MagicMock(number=1)

        blocking = ReviewResult(verdict="BLOCKING", summary="bad",
                                findings=[Finding(severity="BLOCKING", text="x")])
        ok = ReviewResult(verdict="OK", summary="fixed")

        with patch("src.agent.Reviewer") as MockReviewer, \
             patch("src.agent.ClaudeCode") as MockClaude:
            instance = MockReviewer.return_value
            instance.review.side_effect = [blocking, ok]
            worker = MockClaude.return_value
            worker.execute.return_value = ("done", False, MagicMock())

            result = agent._run_review_loop(issue=issue, pr=pr, branch="agent/issue-1",
                                            worktree_path=tmp_path)

            assert instance.review.call_count == 2
            assert worker.execute.call_count == 1
            agent.git.commit_and_push.assert_called_once()
            assert result is False

    def test_loop_flags_for_human_on_exhaustion(self, tmp_path):
        agent = self._make_agent(max_review_rounds=2)
        issue = MagicMock(); issue.labels = []
        issue.add_to_labels = MagicMock()
        pr = MagicMock(number=1)

        blocking = ReviewResult(verdict="BLOCKING", summary="still bad",
                                findings=[Finding(severity="BLOCKING", text="x")])

        with patch("src.agent.Reviewer") as MockReviewer, \
             patch("src.agent.ClaudeCode") as MockClaude:
            instance = MockReviewer.return_value
            instance.review.return_value = blocking
            worker = MockClaude.return_value
            worker.execute.return_value = ("", False, MagicMock())

            result = agent._run_review_loop(issue=issue, pr=pr, branch="agent/issue-1",
                                            worktree_path=tmp_path)

            assert instance.review.call_count == 2
            issue.add_to_labels.assert_called_once_with("needs-human")
            pr.create_issue_comment.assert_called()
            assert result is True
