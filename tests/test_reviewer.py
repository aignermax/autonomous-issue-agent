"""Tests for Reviewer."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.reviewer import Reviewer, ReviewResult, parse_review_output


class TestParseReviewOutput:
    def test_parse_ok_verdict(self):
        out = """blah blah
=== REVIEW RESULT ===
VERDICT: OK
SUMMARY: All good.
=== FINDINGS ===
=== END ===
"""
        r = parse_review_output(out)
        assert r.verdict == "OK"
        assert r.summary == "All good."
        assert r.findings == []

    def test_parse_blocking_with_findings(self):
        out = """preamble
=== REVIEW RESULT ===
VERDICT: BLOCKING
SUMMARY: Two correctness bugs.
=== FINDINGS ===
- [BLOCKING] foo.py:12 — null deref — add null guard
- [NIT] bar.py:8 — naming — rename xyz
=== END ===
trailing"""
        r = parse_review_output(out)
        assert r.verdict == "BLOCKING"
        assert len(r.findings) == 2
        assert r.findings[0].severity == "BLOCKING"
        assert "null deref" in r.findings[0].text

    def test_parse_missing_block_treated_as_blocking(self):
        """If reviewer output lacks the result block, treat as BLOCKING (fail-safe)."""
        r = parse_review_output("just some text without the markers")
        assert r.verdict == "BLOCKING"
        assert "could not parse" in r.summary.lower()


class TestReviewer:
    def _make_config(self):
        config = MagicMock()
        config.reviewer_model_default = "sonnet"
        config.reviewer_model_critical = "opus"
        config.critical_label = "critical"
        config.reviewer_max_turns = 30
        config.tools_dir = Path("/tmp/tools")
        config.tools_python = Path("/tmp/venv/bin/python3")
        return config

    def _make_claude_factory(self, output: str):
        instance = MagicMock()
        instance.execute.return_value = (
            output,
            False,
            MagicMock(total_tokens=100, estimated_cost_usd=0.01),
        )
        factory = MagicMock(return_value=instance)
        return factory

    def test_review_invokes_claude_with_critical_model(self, tmp_path):
        """Critical-label issues get the opus model."""
        config = self._make_config()
        github = MagicMock()
        factory = self._make_claude_factory(
            "=== REVIEW RESULT ===\nVERDICT: OK\nSUMMARY: ok\n=== FINDINGS ===\n=== END ==="
        )

        rv = Reviewer(config=config, github=github, claude_factory=factory)
        issue = MagicMock()
        critical_label = MagicMock()
        critical_label.name = "critical"
        issue.labels = [critical_label]
        pr = MagicMock(number=99)

        rv.review(issue=issue, pr=pr, branch="agent/issue-1", base_branch="main",
                  worktree_path=tmp_path)

        kwargs = factory.call_args.kwargs
        assert kwargs["model"] == "opus"

    def test_review_uses_default_model_without_critical_label(self, tmp_path):
        config = self._make_config()
        github = MagicMock()
        factory = self._make_claude_factory(
            "=== REVIEW RESULT ===\nVERDICT: OK\nSUMMARY: ok\n=== FINDINGS ===\n=== END ==="
        )

        rv = Reviewer(config=config, github=github, claude_factory=factory)
        issue = MagicMock()
        issue.labels = []
        pr = MagicMock(number=99)

        rv.review(issue=issue, pr=pr, branch="b", base_branch="main",
                  worktree_path=tmp_path)

        kwargs = factory.call_args.kwargs
        assert kwargs["model"] == "sonnet"

    def test_review_posts_pr_comment(self, tmp_path):
        config = self._make_config()
        github = MagicMock()
        factory = self._make_claude_factory(
            "=== REVIEW RESULT ===\nVERDICT: BLOCKING\nSUMMARY: bug\n"
            "=== FINDINGS ===\n- [BLOCKING] x:1 — y — z\n=== END ==="
        )

        rv = Reviewer(config=config, github=github, claude_factory=factory)
        issue = MagicMock(); issue.labels = []
        pr = MagicMock(number=99)

        result = rv.review(issue=issue, pr=pr, branch="b", base_branch="main",
                           worktree_path=tmp_path)

        assert result.verdict == "BLOCKING"
        pr.create_issue_comment.assert_called_once()
        body = pr.create_issue_comment.call_args.args[0]
        assert "BLOCKING" in body
