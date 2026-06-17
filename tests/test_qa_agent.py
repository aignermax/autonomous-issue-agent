"""
Integration tests for the QA agent.

Strategy: spin up a bare git remote in a tmp dir, push a feature branch
with an .agent.toml, then drive QAAgent.verify_pr against a Mock PR
object. Real git + real subprocess; only GitHub API access is faked.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from src.agents.qa_agent import (
    QAAgent,
    LABEL_PASSED,
    LABEL_FAILED,
    LABEL_RUNNING,
)
from src.claude_code import UsageStats
from src.config import Config
from src.git_repo import GitRepo


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def remote_repo(tmp_path: Path):
    """Create a bare remote and a working clone with one commit on main."""
    remote = tmp_path / "remote.git"
    work = tmp_path / "work"

    _git(tmp_path, "-c", "init.defaultBranch=main", "init", "--bare", str(remote))
    _git(tmp_path, "clone", str(remote), str(work))
    _git(work, "config", "user.email", "test@example.com")
    _git(work, "config", "user.name", "Test")
    _git(work, "checkout", "-b", "main")

    (work / "README.md").write_text("hello\n")
    _git(work, "add", ".")
    _git(work, "commit", "-m", "init")
    _git(work, "push", "origin", "main")

    return remote, work


def _push_feature_branch(work: Path, branch: str, agent_toml: str) -> None:
    _git(work, "checkout", "-b", branch)
    (work / ".agent.toml").write_text(agent_toml)
    _git(work, "add", ".agent.toml")
    _git(work, "commit", "-m", f"add agent config on {branch}")
    _git(work, "push", "origin", branch)


def _make_qa_agent(tmp_path: Path, remote_url: Path, monkeypatch,
                   claude_factory=None) -> QAAgent:
    """Build a QAAgent that bypasses real GitHub but uses a real local clone."""
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    config = Config()

    if claude_factory is None:
        # Default stub for tests: never invoked unless qa_review_enabled.
        # If a test forgot to opt in but QA tries to call Claude, this
        # will surface as an explicit failure rather than a silent no-op.
        def _no_claude(*args, **kwargs):
            raise AssertionError("claude_factory should not be called in this test")
        claude_factory = _no_claude

    qa = QAAgent(config, claude_factory=claude_factory)
    qa.current_repo_name = "owner/repo"
    qa.github = Mock()
    qa.git = GitRepo(tmp_path / "qa-clone", str(remote_url), "main")
    return qa


def _stub_claude_factory(canned_output: str):
    """Return a claude_factory that hands back `canned_output` once."""
    calls = []

    class _StubClaude:
        def __init__(self, working_dir, max_turns, model=None):
            calls.append({
                "working_dir": working_dir,
                "max_turns": max_turns,
                "model": model,
            })

        def execute(self, prompt, resume_file=None):
            return canned_output, False, UsageStats()

    factory = lambda **kw: _StubClaude(**kw)
    factory.calls = calls  # introspection hook for assertions
    return factory


_REVIEW_OK_OUTPUT = """Looks good.

=== REVIEW RESULT ===
VERDICT: OK
SUMMARY: Diff is fine.
=== FINDINGS ===
=== END ===
"""

_REVIEW_BLOCKING_OUTPUT = """Found a problem.

=== REVIEW RESULT ===
VERDICT: BLOCKING
SUMMARY: Null check missing.
=== FINDINGS ===
- [BLOCKING] foo.py:42 — null deref on early-return path — guard with explicit check
=== END ===
"""


def _make_pr_mock(branch: str, number: int):
    pr = Mock()
    pr.number = number
    pr.head.ref = branch
    pr.title = f"Agent: feature {number}"
    pr.labels = []
    return pr


def _labels_added(pr) -> list[str]:
    return [c.args[0] for c in pr.add_to_labels.call_args_list]


class TestQAAgentVerifyPr:
    """End-to-end checks of verify_pr against a real local git repo."""

    def test_passing_build_and_test_marks_pr_passed(
        self, tmp_path, remote_repo, monkeypatch
    ):
        remote, work = remote_repo
        agent_toml = (
            'build_cmd = "echo build-ok"\n'
            'test_cmd = "echo test-ok"\n'
            'agents_enabled = ["coder", "qa"]\n'
        )
        _push_feature_branch(work, "agent/issue-1", agent_toml)

        qa = _make_qa_agent(tmp_path, remote, monkeypatch)
        pr = _make_pr_mock(branch="agent/issue-1", number=1)

        result = qa.verify_pr(pr)

        assert result.overall_passed is True
        steps = {s.name: s for s in result.steps}
        assert steps["build"].passed is True
        assert steps["test"].passed is True
        assert steps["ui_test"].ran is False  # not configured

        labels = _labels_added(pr)
        assert LABEL_RUNNING in labels
        assert LABEL_PASSED in labels
        assert LABEL_FAILED not in labels

        pr.create_issue_comment.assert_called_once()
        comment_body = pr.create_issue_comment.call_args.args[0]
        assert "PASSED" in comment_body
        assert "build" in comment_body and "test" in comment_body

    def test_failing_build_skips_tests_and_marks_pr_failed(
        self, tmp_path, remote_repo, monkeypatch
    ):
        remote, work = remote_repo
        agent_toml = (
            'build_cmd = "exit 1"\n'
            'test_cmd = "echo should-not-run"\n'
            'agents_enabled = ["coder", "qa"]\n'
        )
        _push_feature_branch(work, "agent/issue-2", agent_toml)

        qa = _make_qa_agent(tmp_path, remote, monkeypatch)
        pr = _make_pr_mock(branch="agent/issue-2", number=2)

        result = qa.verify_pr(pr)

        assert result.overall_passed is False
        steps = {s.name: s for s in result.steps}
        assert steps["build"].ran is True
        assert steps["build"].passed is False
        assert steps["test"].ran is False  # short-circuited after build failure

        labels = _labels_added(pr)
        assert LABEL_FAILED in labels
        assert LABEL_PASSED not in labels

        pr.create_issue_comment.assert_called_once()
        comment_body = pr.create_issue_comment.call_args.args[0]
        assert "FAILED" in comment_body

    def test_failing_test_marks_pr_failed(self, tmp_path, remote_repo, monkeypatch):
        remote, work = remote_repo
        agent_toml = (
            'build_cmd = "echo build-ok"\n'
            'test_cmd = "exit 2"\n'
            'agents_enabled = ["coder", "qa"]\n'
        )
        _push_feature_branch(work, "agent/issue-3", agent_toml)

        qa = _make_qa_agent(tmp_path, remote, monkeypatch)
        pr = _make_pr_mock(branch="agent/issue-3", number=3)

        result = qa.verify_pr(pr)

        assert result.overall_passed is False
        steps = {s.name: s for s in result.steps}
        assert steps["build"].passed is True
        assert steps["test"].ran is True
        assert steps["test"].passed is False
        assert steps["test"].exit_code == 2

        assert LABEL_FAILED in _labels_added(pr)

    def test_qa_disabled_via_agent_toml_skips_steps(
        self, tmp_path, remote_repo, monkeypatch
    ):
        remote, work = remote_repo
        agent_toml = (
            'agents_enabled = ["coder"]\n'
            'build_cmd = "exit 1"\n'  # would fail if it ran
        )
        _push_feature_branch(work, "agent/issue-4", agent_toml)

        qa = _make_qa_agent(tmp_path, remote, monkeypatch)
        pr = _make_pr_mock(branch="agent/issue-4", number=4)

        result = qa.verify_pr(pr)

        # Disabled means QA bows out without a verdict — overall_passed stays True
        # so the agent doesn't tag the PR as failed.
        assert result.overall_passed is True
        assert result.error == "qa disabled for repo"
        assert result.steps == []

        # Running label was added then removed; no pass/fail label.
        labels = _labels_added(pr)
        assert LABEL_RUNNING in labels
        assert LABEL_PASSED not in labels
        assert LABEL_FAILED not in labels

        pr.create_issue_comment.assert_not_called()

    def test_no_agent_toml_skips_steps_but_does_not_fail(
        self, tmp_path, remote_repo, monkeypatch
    ):
        """A repo with no .agent.toml should be ignored, not failed.

        Defaults: agents_enabled=["coder"] only, so QA short-circuits the
        same way as test_qa_disabled_via_agent_toml_skips_steps.
        """
        remote, work = remote_repo
        # Push a feature branch with no .agent.toml at all.
        _git(work, "checkout", "-b", "agent/issue-5")
        (work / "feature.txt").write_text("change\n")
        _git(work, "add", "feature.txt")
        _git(work, "commit", "-m", "feature change")
        _git(work, "push", "origin", "agent/issue-5")

        qa = _make_qa_agent(tmp_path, remote, monkeypatch)
        pr = _make_pr_mock(branch="agent/issue-5", number=5)

        result = qa.verify_pr(pr)

        assert result.overall_passed is True
        assert result.error == "qa disabled for repo"
        labels = _labels_added(pr)
        assert LABEL_PASSED not in labels
        assert LABEL_FAILED not in labels


class TestQAAgentClaudeReview:
    """Verify the optional Claude PR review step."""

    def test_review_disabled_does_not_invoke_claude(
        self, tmp_path, remote_repo, monkeypatch
    ):
        remote, work = remote_repo
        agent_toml = (
            'build_cmd = "echo build-ok"\n'
            'test_cmd = "echo test-ok"\n'
            'agents_enabled = ["coder", "qa"]\n'
            # qa_review_enabled defaults to false
        )
        _push_feature_branch(work, "agent/issue-10", agent_toml)

        # Default factory raises if invoked — proves Claude wasn't called.
        qa = _make_qa_agent(tmp_path, remote, monkeypatch)
        pr = _make_pr_mock(branch="agent/issue-10", number=10)

        result = qa.verify_pr(pr)
        assert result.overall_passed is True
        assert result.review is None

    def test_review_enabled_and_ok_keeps_pr_passed(
        self, tmp_path, remote_repo, monkeypatch
    ):
        remote, work = remote_repo
        agent_toml = (
            'build_cmd = "echo build-ok"\n'
            'test_cmd = "echo test-ok"\n'
            'agents_enabled = ["coder", "qa"]\n'
            'qa_review_enabled = true\n'
        )
        _push_feature_branch(work, "agent/issue-11", agent_toml)

        factory = _stub_claude_factory(_REVIEW_OK_OUTPUT)
        qa = _make_qa_agent(tmp_path, remote, monkeypatch, claude_factory=factory)
        pr = _make_pr_mock(branch="agent/issue-11", number=11)

        result = qa.verify_pr(pr)

        assert result.overall_passed is True
        assert result.review is not None
        assert result.review.verdict == "OK"
        assert len(factory.calls) == 1  # Claude was invoked exactly once

        labels = _labels_added(pr)
        assert LABEL_PASSED in labels
        assert LABEL_FAILED not in labels

        comment_body = pr.create_issue_comment.call_args.args[0]
        assert "Claude review" in comment_body
        assert "OK" in comment_body

    def test_review_blocking_fails_pr_even_if_mechanical_ok(
        self, tmp_path, remote_repo, monkeypatch
    ):
        remote, work = remote_repo
        agent_toml = (
            'build_cmd = "echo build-ok"\n'
            'test_cmd = "echo test-ok"\n'
            'agents_enabled = ["coder", "qa"]\n'
            'qa_review_enabled = true\n'
        )
        _push_feature_branch(work, "agent/issue-12", agent_toml)

        factory = _stub_claude_factory(_REVIEW_BLOCKING_OUTPUT)
        qa = _make_qa_agent(tmp_path, remote, monkeypatch, claude_factory=factory)
        pr = _make_pr_mock(branch="agent/issue-12", number=12)

        result = qa.verify_pr(pr)

        assert result.overall_passed is False
        assert result.review is not None
        assert result.review.has_blocking is True

        labels = _labels_added(pr)
        assert LABEL_FAILED in labels
        assert LABEL_PASSED not in labels

        comment_body = pr.create_issue_comment.call_args.args[0]
        assert "BLOCKING" in comment_body
        assert "Null check missing" in comment_body

    def test_review_skipped_when_mechanical_already_failed(
        self, tmp_path, remote_repo, monkeypatch
    ):
        """No point burning tokens on a tree that already failed build/test."""
        remote, work = remote_repo
        agent_toml = (
            'build_cmd = "exit 1"\n'
            'test_cmd = "echo unused"\n'
            'agents_enabled = ["coder", "qa"]\n'
            'qa_review_enabled = true\n'
        )
        _push_feature_branch(work, "agent/issue-13", agent_toml)

        # Factory MUST NOT be invoked — assert via a poisoned factory.
        def poisoned(**kw):
            raise AssertionError("Claude must not run after mechanical failure")

        qa = _make_qa_agent(tmp_path, remote, monkeypatch, claude_factory=poisoned)
        pr = _make_pr_mock(branch="agent/issue-13", number=13)

        result = qa.verify_pr(pr)

        assert result.overall_passed is False
        assert result.review is None  # never ran
        assert LABEL_FAILED in _labels_added(pr)

    def test_review_crash_is_fail_safe_blocking(
        self, tmp_path, remote_repo, monkeypatch
    ):
        """If Claude blows up, we must not silently pass the PR."""
        remote, work = remote_repo
        agent_toml = (
            'build_cmd = "echo build-ok"\n'
            'test_cmd = "echo test-ok"\n'
            'agents_enabled = ["coder", "qa"]\n'
            'qa_review_enabled = true\n'
        )
        _push_feature_branch(work, "agent/issue-14", agent_toml)

        class _BoomClaude:
            def __init__(self, **kw):
                pass

            def execute(self, prompt, resume_file=None):
                raise RuntimeError("simulated CLI crash")

        qa = _make_qa_agent(
            tmp_path, remote, monkeypatch,
            claude_factory=lambda **kw: _BoomClaude(**kw),
        )
        pr = _make_pr_mock(branch="agent/issue-14", number=14)

        result = qa.verify_pr(pr)

        assert result.overall_passed is False
        assert result.review is not None
        assert result.review.verdict == "BLOCKING"
        assert "simulated CLI crash" in result.review.summary
        assert LABEL_FAILED in _labels_added(pr)
