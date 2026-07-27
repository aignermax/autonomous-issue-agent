"""Tests for GitRepo (src/git_repo.py)."""
import subprocess

from src.git_repo import GitRepo


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def _make_repo_with_worktree(tmp_path):
    """Primary clone on main + linked worktree on an agent branch."""
    primary = tmp_path / "primary"
    primary.mkdir()
    _git(primary, "init", "-b", "main")
    _git(primary, "config", "user.email", "t@t")
    _git(primary, "config", "user.name", "t")
    (primary / "f.txt").write_text("x", encoding="utf-8")
    _git(primary, "add", ".")
    _git(primary, "commit", "-m", "init")
    wt = tmp_path / "wt"
    _git(primary, "worktree", "add", "-b", "agent/issue-1-x", str(wt), "main")
    return primary, wt


def test_ensure_cloned_in_linked_worktree_keeps_branch(tmp_path):
    """In a linked worktree ensure_cloned must NOT try to check out main.

    That checkout always fails ("'main' is already used by worktree ...") —
    it produced a recurring ERROR-level self-heal on every issue pickup —
    and the subsequent pull/reset would target the agent branch instead.
    """
    primary, wt = _make_repo_with_worktree(tmp_path)
    repo = GitRepo(wt, remote_url=str(primary), default_branch="main")

    repo.ensure_cloned()  # must not raise

    head = _git(wt, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    assert head == "agent/issue-1-x"  # branch untouched


def test_ensure_cloned_primary_clone_stays_on_working_branch(tmp_path):
    """Primary clone keeps the classic sync behavior (checkout + pull)."""
    origin = tmp_path / "origin"
    origin.mkdir()
    _git(origin, "init", "--bare", "-b", "main")
    src = tmp_path / "src"
    _git(tmp_path, "clone", str(origin), str(src))
    _git(src, "config", "user.email", "t@t")
    _git(src, "config", "user.name", "t")
    (src / "f.txt").write_text("x", encoding="utf-8")
    _git(src, "add", ".")
    _git(src, "commit", "-m", "init")
    _git(src, "push", "origin", "main")

    repo = GitRepo(src, remote_url=str(origin), default_branch="main")
    repo.ensure_cloned()  # must not raise
    head = _git(src, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    assert head == "main"
