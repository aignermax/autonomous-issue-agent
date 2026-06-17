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

    def test_create_distinguishes_branches_with_slashes_vs_underscores(self, repo, tmp_path):
        """`feat/foo` and `feat_foo` must not collide."""
        wt_root = tmp_path / "worktrees"
        mgr = WorktreeManager(worktree_root=wt_root)

        p1 = mgr.create(repo_path=repo, branch="feat/foo", base="main")
        p2 = mgr.create(repo_path=repo, branch="feat_foo", base="main")

        assert p1 != p2
        assert p1.is_dir() and p2.is_dir()

    def test_base_falls_back_to_origin_when_local_missing(self, tmp_path):
        """Reproduces the Lunima/akhetonics-desktop crash: caller asks to
        derive from `dev`, but the local clone only has `origin/dev` as a
        remote-tracking ref. create() must transparently fall back to
        `origin/dev` instead of exploding with 'invalid reference: dev'.
        """
        # Build a fake remote with a `dev` branch.
        remote = tmp_path / "remote.git"
        seed = tmp_path / "seed"
        subprocess.run(["git", "-c", "init.defaultBranch=main", "init", "--bare",
                        str(remote)], check=True, capture_output=True)
        subprocess.run(["git", "clone", str(remote), str(seed)],
                       check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=seed, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=seed, check=True)
        subprocess.run(["git", "checkout", "-b", "main"], cwd=seed, check=True,
                       capture_output=True)
        (seed / "README.md").write_text("hi\n")
        subprocess.run(["git", "add", "."], cwd=seed, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=seed, check=True,
                       capture_output=True)
        subprocess.run(["git", "push", "origin", "main"], cwd=seed, check=True,
                       capture_output=True)
        subprocess.run(["git", "checkout", "-b", "dev"], cwd=seed, check=True,
                       capture_output=True)
        (seed / "dev-only.txt").write_text("on dev\n")
        subprocess.run(["git", "add", "."], cwd=seed, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "dev"], cwd=seed, check=True,
                       capture_output=True)
        subprocess.run(["git", "push", "origin", "dev"], cwd=seed, check=True,
                       capture_output=True)

        # The main checkout that the agent uses: clones the remote, sits on
        # `main`, has `origin/dev` only as a remote-tracking ref.
        main_clone = tmp_path / "main-clone"
        subprocess.run(["git", "clone", str(remote), str(main_clone)],
                       check=True, capture_output=True)

        # Sanity: `dev` is NOT a local branch in the main clone.
        local_dev = subprocess.run(
            ["git", "rev-parse", "--verify", "dev"],
            cwd=main_clone, capture_output=True, text=True,
        )
        assert local_dev.returncode != 0

        wt_root = tmp_path / "worktrees"
        mgr = WorktreeManager(worktree_root=wt_root)

        # The failing call — pre-fix it raised RuntimeError. Now it should
        # silently resolve `dev` → `origin/dev`.
        path = mgr.create(
            repo_path=main_clone,
            branch="agent/issue-254",
            base="dev",
        )

        assert path.is_dir()
        # Worktree must have started from the dev tip, so dev-only.txt is there.
        assert (path / "dev-only.txt").is_file()

    def test_list_marks_detached_head(self, repo, tmp_path):
        """A detached-HEAD worktree should be listed with branch='(detached)'."""
        import subprocess
        wt_root = tmp_path / "worktrees"
        mgr = WorktreeManager(worktree_root=wt_root)

        # Create a worktree, then detach HEAD inside it
        path = mgr.create(repo_path=repo, branch="feat/detach-me", base="main")
        subprocess.run(["git", "checkout", "--detach"], cwd=path, check=True,
                       capture_output=True)

        wts = mgr.list(repo_path=repo)
        detached = [w for w in wts if w.path.resolve() == path.resolve()]
        assert len(detached) == 1
        assert detached[0].branch == "(detached)"
