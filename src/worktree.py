"""Git worktree management for isolated per-issue working directories.

Each issue gets its own worktree under <worktree_root>/<repo-name>/<branch>/.
This isolates parallel issue processing and prevents working-directory
contamination between runs.
"""

import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List

log = logging.getLogger("agent")


@dataclass(frozen=True)
class WorktreeInfo:
    """One row from `git worktree list`."""
    path: Path
    branch: str
    head: str


class WorktreeManager:
    """Creates and removes git worktrees for the agent."""

    def __init__(self, worktree_root: Path):
        """
        Args:
            worktree_root: Base directory for all agent worktrees
                           (e.g. ~/.aia-worktrees).
        """
        self.worktree_root = worktree_root.expanduser()
        self.worktree_root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, repo_path: Path, branch: str) -> Path:
        repo_name = repo_path.resolve().name
        safe = branch.replace("/", "_")
        return self.worktree_root / repo_name / safe

    def create(self, repo_path: Path, branch: str, base: str) -> Path:
        """Create a worktree for `branch` derived from `base`.

        If the worktree already exists, returns its path without re-creating.

        Args:
            repo_path: Main checkout (where .git lives).
            branch: Branch name to create or check out.
            base: Branch to derive from when creating new branch.

        Returns:
            Absolute path of the worktree.
        """
        target = self._path_for(repo_path, branch)
        if target.is_dir() and (target / ".git").exists():
            log.info(f"Worktree already exists: {target}")
            return target

        target.parent.mkdir(parents=True, exist_ok=True)

        # Check if branch already exists locally
        local = subprocess.run(
            ["git", "rev-parse", "--verify", branch],
            cwd=repo_path, capture_output=True, text=True,
        )
        if local.returncode == 0:
            cmd = ["git", "worktree", "add", str(target), branch]
        else:
            cmd = ["git", "worktree", "add", "-b", branch, str(target), base]

        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"git worktree add failed: {result.stderr}")
        log.info(f"Created worktree: {target} (branch {branch})")
        return target

    def remove(self, repo_path: Path, branch: str) -> None:
        """Remove a worktree by branch. Does not delete the branch itself."""
        target = self._path_for(repo_path, branch)
        if not target.exists():
            log.info(f"Worktree already gone: {target}")
            return
        result = subprocess.run(
            ["git", "worktree", "remove", "--force", str(target)],
            cwd=repo_path, capture_output=True, text=True,
        )
        if result.returncode != 0:
            log.warning(f"git worktree remove failed, falling back to manual delete: {result.stderr}")
            import shutil
            shutil.rmtree(target, ignore_errors=True)
            subprocess.run(
                ["git", "worktree", "prune"],
                cwd=repo_path, capture_output=True, text=True,
            )

    def list(self, repo_path: Path) -> List[WorktreeInfo]:
        """List all worktrees registered in `repo_path`."""
        result = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            cwd=repo_path, capture_output=True, text=True,
        )
        if result.returncode != 0:
            return []

        worktrees: List[WorktreeInfo] = []
        current: dict = {}
        for line in result.stdout.splitlines():
            if not line.strip():
                if current.get("worktree"):
                    worktrees.append(WorktreeInfo(
                        path=Path(current["worktree"]),
                        branch=current.get("branch", "").replace("refs/heads/", ""),
                        head=current.get("HEAD", ""),
                    ))
                current = {}
                continue
            m = re.match(r"^(\S+)\s*(.*)$", line)
            if m:
                current[m.group(1)] = m.group(2)
        if current.get("worktree"):
            worktrees.append(WorktreeInfo(
                path=Path(current["worktree"]),
                branch=current.get("branch", "").replace("refs/heads/", ""),
                head=current.get("HEAD", ""),
            ))
        # Drop the main checkout (no branch ref or first entry)
        return [w for w in worktrees if w.path.resolve() != repo_path.resolve()]
