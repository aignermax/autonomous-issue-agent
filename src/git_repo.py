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

    def __init__(self, path: Path, remote_url: str, default_branch: str = "main",
                 author_name: Optional[str] = None, author_email: Optional[str] = None):
        """
        Initialize Git repository handler.

        Args:
            path: Local path to the repository
            remote_url: Git remote URL (HTTPS or SSH)
            default_branch: Default branch name (e.g., "dev", "main", "master")
            author_name: Author name to set on the local clone (for `git commit`).
                Falls back to env AGENT_GIT_USER_NAME, then "Autonomous Issue Agent".
            author_email: Author email to set on the local clone.
                Falls back to env AGENT_GIT_USER_EMAIL, then "aia-bot@local".
        """
        import os
        self.path = path
        self.remote_url = remote_url
        self.default_branch = default_branch
        self.author_name = (author_name
                            or os.environ.get("AGENT_GIT_USER_NAME")
                            or "Autonomous Issue Agent")
        self.author_email = (author_email
                             or os.environ.get("AGENT_GIT_USER_EMAIL")
                             or "aia-bot@local")

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

    @property
    def _masked_remote(self) -> str:
        """remote_url with any embedded HTTP basic-auth credentials masked.

        Used in logs so that GitHub PATs embedded in `https://<token>@…` clone
        URLs do not end up in agent.log / journalctl / conversation transcripts.
        """
        import re
        return re.sub(r'(https?://)[^@/\s]+@', r'\1***@', self.remote_url)

    def ensure_cloned(self) -> None:
        """
        Clone repository if not exists, otherwise pull latest changes.

        Ensures repository is in clean state before pulling to avoid conflicts.
        """
        if not (self.path / ".git").exists():
            log.info(f"Cloning {self._masked_remote} ...")
            subprocess.run(
                ["git", "clone", self.remote_url, str(self.path)],
                check=True,
                capture_output=True,
                text=True,
            )
        else:
            # Re-sync the remote URL with the current env token. The token is
            # embedded in remote.origin.url at clone time; if the user later
            # rotates the PAT, every fetch fails with "could not read Password"
            # until we update it. set-url is idempotent and cheap.
            self.run("remote", "set-url", "origin", self.remote_url)

            # CRITICAL: Clean any uncommitted changes first to avoid conflicts
            self._ensure_clean_state()

            working_branch = self.get_working_branch()
            checkout_result = self.run("checkout", working_branch)
            if checkout_result.returncode != 0:
                log.error(f"Failed to checkout {working_branch}, attempting to clean and retry")
                self._ensure_clean_state()
                self.run("checkout", working_branch)

            # Fetch latest changes first
            fetch_result = self.run("fetch", "origin")
            if fetch_result.returncode != 0:
                log.error(f"Failed to fetch from origin")
                raise RuntimeError(f"Failed to fetch: {fetch_result.stderr}")

            # Try fast-forward pull first
            pull_result = self.run("pull", "--ff-only")
            if pull_result.returncode != 0:
                # If fast-forward fails (diverging branches), reset to remote state
                log.warning(f"Fast-forward pull failed (diverging branches), resetting to origin/{working_branch}")
                reset_result = self.run("reset", "--hard", f"origin/{working_branch}")
                if reset_result.returncode != 0:
                    log.error(f"Failed to reset to origin/{working_branch}")
                    raise RuntimeError(f"Failed to reset to remote: {reset_result.stderr}")
                log.info(f"Successfully reset local repository to origin/{working_branch}")

        # Always (re-)set local author identity so `git commit` can succeed
        # without a system-wide user.name/user.email. Idempotent.
        self._configure_identity()

    def _configure_identity(self) -> None:
        """Set local user.name and user.email on this clone so `git commit`
        does not fail with 'Author identity unknown'. Local config only — does
        not touch the user's global git config."""
        self.run("config", "user.name", self.author_name)
        self.run("config", "user.email", self.author_email)

    def _ensure_clean_state(self) -> None:
        """
        Ensure repository is in clean state by resetting any uncommitted changes.

        This prevents git operations from failing due to dirty working directory.
        """
        # Check if there are any uncommitted changes
        status_result = self.run("status", "--porcelain")
        if status_result.stdout.strip():
            log.warning(f"Repository has uncommitted changes, cleaning...")
            log.warning(f"Uncommitted files:\n{status_result.stdout[:500]}")

            # Reset all tracked files
            self.run("reset", "--hard", "HEAD")

            # Remove all untracked files and directories
            self.run("clean", "-fd")

            log.info("Repository cleaned: all uncommitted changes removed")

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
            # Commit the changes. CRITICAL: check returncode — git can fail
            # silently (e.g. "Author identity unknown") and we must not push
            # nothing-new and then create a doomed PR.
            commit_result = self.run("commit", "-m", message)
            if commit_result.returncode != 0:
                raise RuntimeError(
                    f"git commit failed (exit {commit_result.returncode}): "
                    f"{commit_result.stderr.strip() or commit_result.stdout.strip()}"
                )
            log.info("Changes committed.")
        else:
            log.info("No uncommitted changes in working directory.")

        # Decide whether there's anything new to push. Compare against the
        # base branch (origin/<base>) — that's the right reference for "does
        # this branch carry commits worth pushing?". We deliberately do NOT
        # fall back to `unpushed_count = 1` when origin/<branch> is missing:
        # that historically caused empty branches to be pushed (and PRs to
        # 422 with "No commits between") whenever a commit failed silently.
        ahead = self.run("rev-list", "--count", f"origin/{base_branch}..{branch}")
        if ahead.returncode != 0:
            raise RuntimeError(
                f"git rev-list origin/{base_branch}..{branch} failed "
                f"(exit {ahead.returncode}): {ahead.stderr.strip()}"
            )
        unpushed_count = int(ahead.stdout.strip() or "0")

        if unpushed_count > 0:
            log.info(f"Found {unpushed_count} unpushed commit(s), pushing to origin...")

            # Try to push - if rejected due to diverging branches, fetch and handle conflict
            push_result = self.run("push", "--set-upstream", "origin", branch)

            if push_result.returncode != 0:
                # Push failed - check if it's because of diverging branches
                if "rejected" in push_result.stderr and "fetch first" in push_result.stderr:
                    log.warning(f"Push rejected - remote branch has diverged")

                    # Fetch latest remote state
                    self.run("fetch", "origin", branch)

                    # Check if we have diverging commits
                    behind_result = self.run("rev-list", "--count", f"{branch}..origin/{branch}")
                    ahead_result = self.run("rev-list", "--count", f"origin/{branch}..{branch}")

                    commits_behind = int(behind_result.stdout.strip() or "0") if behind_result.returncode == 0 else 0
                    commits_ahead = int(ahead_result.stdout.strip() or "0") if ahead_result.returncode == 0 else 0

                    log.info(f"Branch status: {commits_ahead} ahead, {commits_behind} behind remote")

                    # If we're only ahead (remote has no new commits we don't have), force push is safe
                    # This handles the case where Claude Code created commits locally that differ from remote
                    if commits_behind == 0 and commits_ahead > 0:
                        log.info("Local has new commits, remote hasn't diverged - force pushing")
                        force_push = self.run("push", "--force-with-lease", "origin", branch)
                        if force_push.returncode != 0:
                            log.error(f"Force push failed: {force_push.stderr}")
                            raise RuntimeError(f"Failed to push branch {branch}: {force_push.stderr}")
                    else:
                        # True divergence - remote has commits we don't have
                        log.error(f"Branch has truly diverged - cannot safely push")
                        log.error(f"Remote has {commits_behind} commits we don't have locally")
                        raise RuntimeError(
                            f"Branch {branch} has diverged: {commits_ahead} ahead, {commits_behind} behind. "
                            "Manual intervention required."
                        )
                else:
                    # Different push error
                    log.error(f"Push failed: {push_result.stderr}")
                    raise RuntimeError(f"Failed to push branch {branch}: {push_result.stderr}")

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
        """Return to working branch — no-op if already there or if branch is
        checked out in another worktree (git would refuse with a fatal error)."""
        if not (self.path / ".git").exists():
            return
        working_branch = self.get_working_branch()
        if self.get_current_branch() == working_branch:
            return  # already on it
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
