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

    def __init__(self, path: Path, remote_url: str, default_branch: str = "main"):
        """
        Initialize Git repository handler.

        Args:
            path: Local path to the repository
            remote_url: Git remote URL (HTTPS or SSH)
            default_branch: Default branch name (e.g., "dev", "main", "master")
        """
        self.path = path
        self.remote_url = remote_url
        self.default_branch = default_branch

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
            working_branch = self.get_working_branch()
            self.run("checkout", working_branch)
            self.run("pull", "--ff-only")

    def create_branch(self, name: str) -> None:
        """
        Create and checkout a new branch.

        Args:
            name: Branch name
        """
        self.run("checkout", "-b", name)

    def commit_and_push(self, branch: str, message: str, base_branch: str = None) -> bool:
        """
        Stage all changes, commit, and push to remote.

        Args:
            branch: Branch name to push
            message: Commit message
            base_branch: Base branch to compare against (defaults to repository's default branch)

        Returns:
            True if changes were committed/pushed, False if no changes at all
        """
        if base_branch is None:
            base_branch = self.default_branch
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

        # IMPORTANT: Check if branch has commits that differ from base branch
        # (handles case where Claude Code already pushed, but we still need to create PR)
        base_result = self.run("rev-list", "--count", f"{base_branch}..{branch}")
        if base_result.returncode == 0:
            commits_ahead = int(base_result.stdout.strip() or "0")
            if commits_ahead > 0:
                log.info(f"Branch has {commits_ahead} commit(s) ahead of {base_branch} (already pushed)")
                return True

        if not has_uncommitted:
            log.info("No changes to commit and no unpushed commits.")
            return False

        return True

    def cleanup(self) -> None:
        """Return to working branch."""
        working_branch = self.get_working_branch()
        self.run("checkout", working_branch)

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

    def remote_branch_exists(self, branch: str) -> bool:
        """
        Check if a branch exists on the remote.

        Args:
            branch: Branch name

        Returns:
            True if remote branch exists
        """
        result = self.run("ls-remote", "--heads", "origin", branch)
        return result.returncode == 0 and bool(result.stdout.strip())

    def get_working_branch(self) -> str:
        """
        Get the preferred working branch for development.
        Prefers 'dev' if it exists on remote, otherwise uses default branch.

        Returns:
            Branch name to use for creating PRs and branching from
        """
        if self.remote_branch_exists("dev"):
            log.info("Using 'dev' branch as working branch (exists on remote)")
            return "dev"
        log.info(f"Using '{self.default_branch}' as working branch (no 'dev' branch found)")
        return self.default_branch

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
