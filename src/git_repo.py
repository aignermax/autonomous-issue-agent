"""
Git repository operations for the agent.
"""

import subprocess
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger("agent")


class GitRepo:
    """Handles all local git operations."""

    def __init__(self, path: Path, remote_url: str):
        """
        Initialize Git repository handler.

        Args:
            path: Local path to the repository
            remote_url: Git remote URL (HTTPS or SSH)
        """
        self.path = path
        self.remote_url = remote_url

    def run(self, *args: str) -> subprocess.CompletedProcess:
        """
        Run a git command in the repository directory.

        Args:
            *args: Git command arguments

        Returns:
            CompletedProcess result
        """
        result = subprocess.run(
            ["git", *args],
            cwd=self.path,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            log.warning(f"git {' '.join(args)}: {result.stderr.strip()}")
        return result

    def ensure_cloned(self) -> None:
        """Clone repository if not exists, otherwise pull latest changes."""
        if not (self.path / ".git").exists():
            log.info(f"Cloning {self.remote_url} ...")
            subprocess.run(
                ["git", "clone", self.remote_url, str(self.path)],
                check=True,
                capture_output=True,
                text=True,
            )
        else:
            self.run("checkout", "main")
            self.run("pull", "--ff-only")

    def create_branch(self, name: str) -> None:
        """
        Create and checkout a new branch.

        Args:
            name: Branch name
        """
        self.run("checkout", "-b", name)

    def commit_and_push(self, branch: str, message: str) -> bool:
        """
        Stage all changes, commit, and push to remote.

        Args:
            branch: Branch name to push
            message: Commit message

        Returns:
            True if changes were committed/pushed, False if no changes at all
        """
        self.run("add", ".")

        # Check if there are changes to commit
        status = self.run("status", "--porcelain")
        has_uncommitted = bool(status.stdout.strip())

        if has_uncommitted:
            # Commit the changes
            self.run("commit", "-m", message)
            log.info("Changes committed.")
        else:
            log.info("No uncommitted changes in working directory.")

        # Check if there are unpushed commits (e.g., from Claude Code)
        # Compare local branch with remote
        result = self.run("rev-list", "--count", f"origin/{branch}..{branch}")
        if result.returncode != 0:
            # Remote branch doesn't exist yet - we have commits to push
            unpushed_count = 1
        else:
            unpushed_count = int(result.stdout.strip() or "0")

        if unpushed_count > 0:
            log.info(f"Found {unpushed_count} unpushed commit(s), pushing to origin...")
            self.run("push", "--set-upstream", "origin", branch)
            return True

        if not has_uncommitted:
            log.info("No changes to commit and no unpushed commits.")
            return False

        return True

    def cleanup(self) -> None:
        """Return to main branch."""
        self.run("checkout", "main")

    def branch_exists(self, branch: str) -> bool:
        """
        Check if a branch exists locally.

        Args:
            branch: Branch name

        Returns:
            True if branch exists
        """
        result = self.run("rev-parse", "--verify", branch)
        return result.returncode == 0

    def get_current_branch(self) -> Optional[str]:
        """
        Get the currently checked out branch name.

        Returns:
            Branch name or None if detached HEAD
        """
        result = self.run("rev-parse", "--abbrev-ref", "HEAD")
        if result.returncode == 0:
            return result.stdout.strip()
        return None
