"""Tests for WorktreeManager."""

import subprocess
from pathlib import Path

import pytest

from src.worktree import WorktreeManager


@pytest.fixture
def repo(tmp_path):
    """Create a real git repo for worktree integration tests."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    (repo / "README.md").write_text("hi")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)
    return repo


class TestWorktreeManager:
    def test_create_worktree_for_new_branch(self, repo, tmp_path):
        """create() makes a new branch and worktree at expected location."""
        wt_root = tmp_path / "worktrees"
        mgr = WorktreeManager(worktree_root=wt_root)

        path = mgr.create(repo_path=repo, branch="agent/issue-1", base="main")

        assert path.is_dir()
        assert (path / ".git").exists()
        assert (path / "README.md").is_file()
        # Branch checked out in worktree
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=path, capture_output=True, text=True,
        )
        assert result.stdout.strip() == "agent/issue-1"

    def test_create_is_idempotent(self, repo, tmp_path):
        """Calling create() twice with same branch returns existing worktree."""
        wt_root = tmp_path / "worktrees"
        mgr = WorktreeManager(worktree_root=wt_root)

        p1 = mgr.create(repo_path=repo, branch="agent/issue-2", base="main")
        p2 = mgr.create(repo_path=repo, branch="agent/issue-2", base="main")

        assert p1 == p2

    def test_remove_worktree(self, repo, tmp_path):
        """remove() detaches worktree and deletes the directory."""
        wt_root = tmp_path / "worktrees"
        mgr = WorktreeManager(worktree_root=wt_root)
        path = mgr.create(repo_path=repo, branch="agent/issue-3", base="main")
        assert path.is_dir()

        mgr.remove(repo_path=repo, branch="agent/issue-3")

        assert not path.exists()
        # Branch still exists in repo, just not checked out
        result = subprocess.run(
            ["git", "branch", "--list", "agent/issue-3"],
            cwd=repo, capture_output=True, text=True,
        )
        assert "agent/issue-3" in result.stdout

    def test_list_worktrees(self, repo, tmp_path):
        """list() returns all known worktrees for the repo."""
        wt_root = tmp_path / "worktrees"
        mgr = WorktreeManager(worktree_root=wt_root)
        mgr.create(repo_path=repo, branch="agent/issue-4", base="main")
        mgr.create(repo_path=repo, branch="agent/issue-5", base="main")

        wts = mgr.list(repo_path=repo)

        branches = {wt.branch for wt in wts}
        assert "agent/issue-4" in branches
        assert "agent/issue-5" in branches
