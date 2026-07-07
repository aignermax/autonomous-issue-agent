"""Regression tests for GitRepo.commit_and_push silent-failure bugs.

History: on 2026-05-12 the agent processed issue Zebsi235/Fw91#42, Claude
made real edits, but the commit step failed with "Author identity unknown"
because no git user.name/user.email was set. The failure was logged only as
a warning, then a bogus `rev-list` fallback assumed `unpushed_count = 1`
when `origin/<branch>` did not yet exist. The agent pushed an empty branch
(tip == master) and GitHub returned 422 "No commits between …".

These tests pin the two fixes:
  1. commit_and_push RAISES if `git commit` returns non-zero.
  2. commit_and_push compares against `origin/<base>` (not `origin/<branch>`)
     so a missing origin/<branch> can never silently inflate the count.
"""

from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

import pytest

from src.git_repo import GitRepo


def _cp(returncode: int = 0, stdout: str = "", stderr: str = "") -> CompletedProcess:
    return CompletedProcess(args=["git"], returncode=returncode, stdout=stdout, stderr=stderr)


def _make_repo(tmp_path: Path) -> GitRepo:
    return GitRepo(
        path=tmp_path,
        remote_url="https://x@github.com/foo/bar.git",
        default_branch="master",
        author_name="Test",
        author_email="t@example.com",
    )


def test_commit_failure_raises_instead_of_silently_pushing_empty_branch(tmp_path):
    """If `git commit` returns non-zero, commit_and_push must raise — not
    log and continue (which historically led to pushing an empty branch
    and then a 422 PR creation)."""
    repo = _make_repo(tmp_path)

    def fake_run(*args):
        # Walk through the sequence commit_and_push performs.
        cmd = args
        if cmd[:1] == ("add",):
            return _cp(0)
        if cmd[:1] == ("status",):
            return _cp(0, stdout="M  somefile.c\n")  # has uncommitted
        if cmd[:1] == ("commit",):
            return _cp(128, stderr="*** Please tell me who you are.\n\nrun\n  git config ...\nfatal: empty ident name")
        pytest.fail(f"Unexpected git invocation after failed commit: {cmd}")

    with patch.object(repo, "run", side_effect=fake_run):
        with pytest.raises(RuntimeError, match="git commit failed"):
            repo.commit_and_push("feature/foo", "msg", base_branch="master")


def test_rev_list_compares_against_origin_base_not_origin_branch(tmp_path):
    """The 'anything to push?' check must use `origin/<base>..<branch>`,
    not `origin/<branch>..<branch>` — otherwise a missing origin/<branch>
    masks the no-new-commits case and the agent pushes an empty branch."""
    repo = _make_repo(tmp_path)
    seen = []

    def fake_run(*args):
        seen.append(args)
        if args[:1] == ("add",):
            return _cp(0)
        if args[:1] == ("status",):
            return _cp(0, stdout="")  # no uncommitted (everything already committed by Claude)
        if args[:1] == ("rev-list",):
            return _cp(0, stdout="0\n")  # nothing ahead in either rev-list call
        pytest.fail(f"Unexpected git invocation: {args}")

    with patch.object(repo, "run", side_effect=fake_run):
        pushed = repo.commit_and_push("feature/foo", "msg", base_branch="master")

    # The CRITICAL invariant: the first rev-list must compare against
    # origin/<base>, not origin/<branch>. The old code used origin/<branch>,
    # which silently failed (ambiguous arg) and fell back to "1 unpushed",
    # leading to empty-branch pushes.
    rev_lists = [a for a in seen if a[:1] == ("rev-list",)]
    assert rev_lists, "commit_and_push made no rev-list call"
    assert rev_lists[0] == ("rev-list", "--count", "origin/master..feature/foo"), (
        f"first rev-list must compare against origin/<base>; got: {rev_lists[0]}"
    )

    # And: no push attempt when there's nothing new.
    assert ("push", "--set-upstream", "origin", "feature/foo") not in seen
    assert pushed is False
