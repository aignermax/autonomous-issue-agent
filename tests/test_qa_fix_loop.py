"""
Tests for the coder agent's QA-failed feedback loop (Phase 2).

`Agent._check_qa_failed_prs` and `_run_qa_fix` orchestrate the fix flow.
We mock GitHub + the worktree manager + ClaudeCode so the test runs
without network or a real CLI; the goal is to nail down the
control-flow contract:

  - PR with qa-failed → run Claude, push, remove qa-failed
  - PR over the fix-round budget → escalate, do NOT run Claude
  - No qa-failed PRs → return False, do nothing
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.agent import Agent
from src.config import Config


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    return monkeypatch


def _make_agent(env, tmp_path: Path) -> Agent:
    env.setenv("AGENT_REPO_PATH", str(tmp_path / "repo"))
    env.setenv("AGENT_SESSION_DIR", str(tmp_path / "sessions"))
    env.setenv("AGENT_WORKTREE_DIR", str(tmp_path / "worktrees"))

    config = Config()
    # Bypass the tools_bootstrap call which probes the network/disk.
    with patch("src.agent.ensure_tools_installed") as mock_bootstrap:
        mock_bootstrap.side_effect = RuntimeError("bootstrap skipped in tests")
        agent = Agent(config)
    return agent


def _make_pr(number: int, branch: str, body: str = "Automated implementation for #99\n"):
    pr = Mock()
    pr.number = number
    pr.title = f"Agent: issue {number}"
    pr.head.ref = branch
    pr.body = body
    pr.labels = []
    return pr


class TestCheckQAFailedPRs:
    """Top-level entry point — what does it return, what does it dispatch?"""

    def test_returns_false_when_no_qa_failed_prs(self, env, tmp_path):
        agent = _make_agent(env, tmp_path)
        agent.github = Mock()
        agent.github.find_qa_failed_prs.return_value = []

        assert agent._check_qa_failed_prs() is False
        agent.github.find_qa_failed_prs.assert_called_once()

    def test_returns_false_when_github_unset(self, env, tmp_path):
        agent = _make_agent(env, tmp_path)
        agent.github = None
        assert agent._check_qa_failed_prs() is False

    def test_returns_true_and_dispatches_oldest_pr(self, env, tmp_path):
        agent = _make_agent(env, tmp_path)
        pr_old = _make_pr(50, "agent/issue-50")
        pr_new = _make_pr(51, "agent/issue-51")
        agent.github = Mock()
        agent.github.find_qa_failed_prs.return_value = [pr_old, pr_new]

        with patch.object(agent, "_run_qa_fix") as mock_run:
            assert agent._check_qa_failed_prs() is True
        mock_run.assert_called_once_with(pr_old)

    def test_swallows_run_qa_fix_crash(self, env, tmp_path):
        """A crash during a fix must not break the polling loop."""
        agent = _make_agent(env, tmp_path)
        pr = _make_pr(60, "agent/issue-60")
        agent.github = Mock()
        agent.github.find_qa_failed_prs.return_value = [pr]

        with patch.object(agent, "_run_qa_fix", side_effect=RuntimeError("boom")):
            # Must still return True — work was attempted, even though it
            # crashed, so the caller skips the new-issue scan this cycle.
            assert agent._check_qa_failed_prs() is True


class TestRunQAFixEscalation:
    """`_run_qa_fix` should bail out before invoking Claude when the PR
    has already been fixed too many times."""

    def test_escalates_when_max_rounds_reached(self, env, tmp_path):
        agent = _make_agent(env, tmp_path)
        agent.config.max_qa_fix_rounds = 2
        agent.git = MagicMock()
        agent.github = Mock()
        agent.github.count_qa_failures.return_value = 2  # >= max_rounds

        pr = _make_pr(70, "agent/issue-70")

        with patch("src.agent.ClaudeCode") as mock_cc:
            agent._run_qa_fix(pr)
            mock_cc.assert_not_called()  # no Claude invocation on escalation

        # Escalation side effects:
        labels_added = [c.args[0] for c in pr.add_to_labels.call_args_list]
        assert "needs-human" in labels_added
        pr.create_issue_comment.assert_called_once()
        comment_body = pr.create_issue_comment.call_args.args[0]
        assert "max QA-fix rounds" in comment_body

        # Removes qa-failed so we don't loop on it again.
        agent.github.remove_pr_label.assert_called_once_with(pr, "qa-failed")


class TestRunQAFixHappyPath:
    """End-to-end-ish: real WorktreeManager against a real local repo,
    Claude stubbed, GitHub stubbed."""

    def test_runs_claude_pushes_and_removes_label(self, env, tmp_path, monkeypatch):
        # Set up a real local "repo" with a feature branch so worktree
        # creation has something to attach to.
        import subprocess

        def git(cwd, *args):
            subprocess.run(["git", *args], cwd=str(cwd), check=True,
                           capture_output=True, text=True)

        repo = tmp_path / "main-repo"
        repo.mkdir()
        git(repo, "-c", "init.defaultBranch=main", "init")
        git(repo, "config", "user.email", "test@example.com")
        git(repo, "config", "user.name", "Test")
        (repo / "README.md").write_text("hi\n")
        git(repo, "add", ".")
        git(repo, "commit", "-m", "init")
        git(repo, "checkout", "-b", "agent/issue-80")
        (repo / "feature.txt").write_text("change\n")
        git(repo, "add", ".")
        git(repo, "commit", "-m", "feature")
        git(repo, "checkout", "main")

        agent = _make_agent(env, tmp_path)
        agent.config.max_qa_fix_rounds = 3

        # Wire Agent.git to the real local repo. There's no real remote,
        # so we stub network-touching methods.
        from src.git_repo import GitRepo
        agent.git = GitRepo(repo, "(unused)", "main")
        # ensure_cloned would try to fetch from the bogus URL — short-circuit.
        agent.git.ensure_cloned = lambda: None

        agent.github = Mock()
        agent.github.default_branch = "main"
        agent.github.count_qa_failures.return_value = 0
        agent.github.get_latest_qa_comment.return_value = (
            "[qa-agent] **FAILED**\n- `build`: failed (exit 1)"
        )
        agent.github.repo.get_issue.return_value = Mock(
            number=99, title="x", body="b",
            labels=[],
        )

        # _detect_issue_complexity reads issue.labels — give it an empty list.
        # _find_issue_for_pr looks up #99 from PR body.
        pr = _make_pr(80, "agent/issue-80",
                      body="Automated implementation for #99\n")

        # Stub Claude so we don't shell out.
        from src.claude_code import UsageStats

        class _StubClaude:
            calls = []

            def __init__(self, working_dir, max_turns, model=None):
                self.calls.append(working_dir)

            def execute(self, prompt, resume_file=None):
                # Simulate Claude making a fix in the worktree.
                (Path(self.calls[-1]) / "fix.txt").write_text("fixed\n")
                return "did the work", False, UsageStats()

        # Stub git network ops on the worktree's GitRepo so we don't push.
        original_run = GitRepo.run

        def fake_run(self, *args, **kwargs):
            # Allow local ops; intercept network ones.
            if args and args[0] in ("fetch", "push"):
                return subprocess.CompletedProcess(args=list(args), returncode=0,
                                                   stdout="", stderr="")
            return original_run(self, *args, **kwargs)

        monkeypatch.setattr(GitRepo, "run", fake_run)
        # And neutralize the remote-branch existence check.
        monkeypatch.setattr(GitRepo, "remote_branch_exists", lambda self, b: False)

        with patch("src.agent.ClaudeCode", _StubClaude):
            agent._run_qa_fix(pr)

        # Claude must have been invoked exactly once.
        assert len(_StubClaude.calls) == 1
        # qa-failed label removed so QA can re-run.
        agent.github.remove_pr_label.assert_called_once_with(pr, "qa-failed")
        # No escalation:
        labels_added = [c.args[0] for c in pr.add_to_labels.call_args_list]
        assert "needs-human" not in labels_added
