"""
Tests for the timeout + no-prompt safety behaviour of GitRepo.

Backstory: the Lunima #518 demo run hung for >24h on `git push` because
subprocess.run had no timeout and GIT_TERMINAL_PROMPT was unset. These
tests pin down the contract so we don't regress.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from src import git_repo as gr
from src.git_repo import GitRepo, _no_prompt_env


class TestNoPromptEnv:
    def test_disables_terminal_prompt(self):
        env = _no_prompt_env()
        assert env["GIT_TERMINAL_PROMPT"] == "0"

    def test_neutralises_askpass(self):
        """GIT_ASKPASS must point at something that won't actually answer."""
        env = _no_prompt_env()
        # `echo` exits 0 with empty stdout — git treats empty creds as fail.
        assert env["GIT_ASKPASS"] == "echo"

    def test_respects_caller_supplied_askpass(self, monkeypatch):
        """If the user explicitly set GIT_ASKPASS, keep theirs."""
        monkeypatch.setenv("GIT_ASKPASS", "/custom/askpass")
        env = _no_prompt_env()
        assert env["GIT_ASKPASS"] == "/custom/askpass"


class TestRunPassesTimeoutAndEnv:
    """`GitRepo.run` must hand subprocess a timeout and the no-prompt env."""

    def test_default_timeout_is_applied(self, tmp_path):
        repo = GitRepo(tmp_path, "(unused)", "main")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["git", "status"], returncode=0, stdout="", stderr=""
            )
            repo.run("status")

        _, kwargs = mock_run.call_args
        assert kwargs["timeout"] == gr.DEFAULT_GIT_TIMEOUT_SEC
        assert kwargs["env"]["GIT_TERMINAL_PROMPT"] == "0"

    def test_explicit_timeout_overrides_default(self, tmp_path):
        repo = GitRepo(tmp_path, "(unused)", "main")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["git", "push"], returncode=0, stdout="", stderr=""
            )
            repo.run("push", "origin", "main", timeout=42)

        _, kwargs = mock_run.call_args
        assert kwargs["timeout"] == 42

    def test_timeout_converts_to_failed_completed_process(self, tmp_path):
        """A TimeoutExpired must NOT raise — caller code checks returncode."""
        repo = GitRepo(tmp_path, "(unused)", "main")
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(
            cmd=["git", "push"], timeout=120
        )):
            result = repo.run("push")

        assert result.returncode == 124  # GNU `timeout` convention
        assert "timed out" in result.stderr


class TestEnsureClonedTimeout:
    """`git clone` is the one place we let TimeoutExpired propagate (as
    RuntimeError) because there's no useful return-code path — the
    caller already treats any clone failure as fatal."""

    def test_clone_raises_runtime_error_on_timeout(self, tmp_path):
        # Pick a path that does NOT yet have .git, so ensure_cloned() takes
        # the clone branch.
        empty = tmp_path / "fresh"
        empty.mkdir()
        repo = GitRepo(empty, "https://example.invalid/foo.git", "main")

        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(
                cmd=["git", "clone"], timeout=gr.CLONE_GIT_TIMEOUT_SEC,
            ),
        ):
            with pytest.raises(RuntimeError, match="timed out"):
                repo.ensure_cloned()


class TestPushUsesLongerTimeout:
    """commit_and_push() should ask for a *clone-size* timeout on push
    so a first-time branch upload doesn't hit the 120s default."""

    def test_push_call_gets_clone_timeout(self, tmp_path):
        # Real local repo so the lead-up commands behave normally.
        subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path,
                       check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path,
                       check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path,
                       check=True, capture_output=True)
        (tmp_path / "f.txt").write_text("hi\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path,
                       check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path,
                       check=True, capture_output=True)

        repo = GitRepo(tmp_path, "(unused)", "main")
        timeouts_seen: list[int] = []

        real_run = subprocess.run

        def spy_run(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args")
            if isinstance(cmd, list) and len(cmd) >= 2 and cmd[1] == "push":
                timeouts_seen.append(kwargs.get("timeout"))
                # Skip the actual push — there's no remote.
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout="", stderr=""
                )
            return real_run(*args, **kwargs)

        with patch("subprocess.run", side_effect=spy_run):
            repo.commit_and_push("main", "msg")

        assert timeouts_seen, "push was never invoked"
        # All push calls used the clone-size budget, not the short default.
        for t in timeouts_seen:
            assert t == gr.CLONE_GIT_TIMEOUT_SEC
