"""
Autonomous Issue Agent - Main orchestration with multi-session support.
"""

import os
import time
import logging
import re
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

from .config import Config
from .git_repo import GitRepo
from .claude_code import ClaudeCode
from .github_client import GitHubClient
from .session_state import SessionManager, SessionState
from .tools_bootstrap import ensure_tools_installed

log = logging.getLogger("agent")


@dataclass
class IssueResult:
    """Result of processing an issue."""
    success: bool
    branch: str
    pr_url: str = ""
    error: str = ""
    needs_continuation: bool = False


class Agent:
    """
    Orchestrates the full issue-to-PR pipeline with multi-session support.

    Enables handling of complex tasks by:
    - Tracking state across multiple Claude Code sessions
    - Auto-continuing when max turns reached
    - Preserving progress and resuming work
    """

    def __init__(self, config: Config):
        """Initialize agent with configuration."""
        self.config = config
        # Initialize github client, git repo, etc. per repository (done in run methods)
        self.github = None
        self.git = None
        self.claude = None
        self.session_manager = SessionManager(config.session_dir)
        # Bootstrap python-dev-tools and expose path for prompts
        try:
            install = ensure_tools_installed()
            self.config.tools_dir = install.dir
            self.config.tools_python = install.python
        except RuntimeError as e:
            log.warning(f"Tools bootstrap failed: {e}. Prompts will reference relative 'tools/'.")
        # Round-robin state: track which repo was checked last
        self._last_repo_index = -1

    def _count_tool_usage(self, output: str) -> dict:
        """
        Count usage of semantic_search.py and smart_test.py tools in Claude Code output.

        Args:
            output: Claude Code output text

        Returns:
            Dictionary with tool names and counts
        """
        import re

        tool_counts = {}

        # Count semantic_search.py usage
        semantic_pattern = r'\S*python\S*\s+\S*(?:tools|\.cap-tools)/semantic_search\.py'
        semantic_matches = re.findall(semantic_pattern, output)
        if semantic_matches:
            tool_counts['semantic_search'] = len(semantic_matches)

        # Count smart_test.py usage
        smart_test_pattern = r'\S*python\S*\s+\S*(?:tools|\.cap-tools)/smart_test\.py'
        smart_test_matches = re.findall(smart_test_pattern, output)
        if smart_test_matches:
            tool_counts['smart_test'] = len(smart_test_matches)

        return tool_counts

    def _detect_issue_complexity(self, issue) -> tuple[int, int, str]:
        """
        Detect issue complexity based on presence of complexity modifier tag.

        Args:
            issue: GitHub Issue object

        Returns:
            Tuple of (max_turns, max_tokens, complexity_level)
        """
        labels = [label.name.lower() for label in issue.labels]

        # Check for complexity modifier tag
        if self.config.complexity_tag.lower() in labels:
            log.info(f"Issue #{issue.number} has '{self.config.complexity_tag}' tag → COMPLEX mode: {self.config.max_turns_complex} turns, {self.config.max_tokens_complex:,} tokens")
            return self.config.max_turns_complex, self.config.max_tokens_complex, "COMPLEX"

        # Default: regular task
        log.info(f"Issue #{issue.number} without complexity tag → REGULAR mode: {self.config.max_turns_regular} turns, {self.config.max_tokens_regular:,} tokens")
        return self.config.max_turns_regular, self.config.max_tokens_regular, "REGULAR"

    def _extract_branch_from_issue(self, issue) -> Optional[str]:
        """
        Extract target branch name from issue body.

        Looks for patterns like:
        - "branch: feature/xyz"
        - "Work on branch: feature/xyz"
        - "Please work on branch: feature/xyz"

        Args:
            issue: GitHub Issue object

        Returns:
            Branch name if found, None otherwise
        """
        if not issue.body:
            return None

        # Pattern: matches "branch: something" or "branch:something"
        # Order matters: try most specific patterns first
        patterns = [
            # Match branch name in code block after "branch:" heading
            r'branch:\s*\n\s*```\s*\n\s*([a-zA-Z0-9/_-]+)',
            r'(?:work\s+on\s+)?branch:\s*([^\s\n`]+)',
            r'(?:use\s+)?branch\s*=\s*([^\s\n]+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, issue.body, re.IGNORECASE | re.DOTALL)
            if match:
                branch_name = match.group(1).strip()
                # Clean up markdown formatting: **`branch`** -> branch
                branch_name = re.sub(r'[*`]+', '', branch_name).strip()
                log.info(f"Found target branch in issue body: {branch_name}")
                return branch_name

        return None

    def _find_pr_for_issue(self, issue_num: int):
        """
        Find an open PR that addresses this issue.

        Args:
            issue_num: Issue number to search for

        Returns:
            PR object if found, None otherwise
        """
        try:
            for pr in self.github.repo.get_pulls(state="open"):
                # Check if PR title or body references this issue
                # Common patterns: "Fix #123", "Fixes #123", "Closes #123", etc.
                if f"#{issue_num}" in pr.title or f"#{issue_num}" in (pr.body or ""):
                    log.info(f"Found existing PR #{pr.number} for issue #{issue_num}")
                    return pr
        except Exception as e:
            log.warning(f"Error searching for existing PR: {e}")
        return None

    def _get_base_branch(self) -> str:
        """
        Get the base branch for the next PR.

        If stacked PRs enabled, finds the most recently created open PR
        created by the agent and uses its head branch as the base.

        Returns:
            - If stacked PRs enabled and recent agent PR found: that PR's head branch
            - Otherwise: working branch (prefers 'dev' if exists, falls back to default branch)
        """
        if not self.config.enable_stacked_prs:
            # When stacked PRs disabled, always use the main working branch (dev or main)
            return self.git.get_working_branch()

        # Find the most recent agent PR (sorted by created date, newest first)
        try:
            prs = list(self.github.repo.get_pulls(
                state="open",
                sort="created",
                direction="desc"
            ))

            # Look for the most recent PR created by the agent
            for pr in prs:
                # Check if it's an agent PR (title starts with "Agent:")
                if pr.title.startswith("Agent:"):
                    log.info(f"Found recent agent PR #{pr.number}: {pr.title}")
                    log.info(f"Using stacked PR - base branch: {pr.head.ref}")
                    return pr.head.ref

            log.info(f"No recent agent PRs found, using {working_branch} as base")
            return working_branch

        except Exception as e:
            log.warning(f"Failed to fetch recent PRs for stacking: {e}")
            return working_branch

    def _validate_and_setup_session(self, issue) -> tuple[Optional[SessionState], str]:
        """
        Validate issue and setup/resume session.

        Args:
            issue: GitHub Issue object

        Returns:
            Tuple of (session_state, branch_name)
            Raises IssueResult exception if issue should be skipped
        """
        issue_num = issue.number

        # Check if issue is still open
        if issue.state != "open":
            log.warning(f"Issue #{issue_num} is closed (state: {issue.state})")
            state = self.session_manager.load_state(issue_num)
            if state:
                log.info(f"Deleting session for closed issue #{issue_num}")
                self.session_manager.delete_state(issue_num)
            raise IssueResult(success=False, branch="", error=f"Issue is closed")

        # Check for existing session
        state = self.session_manager.load_state(issue_num)

        if state:
            # Resume existing session
            log.info(f"Resuming session for issue #{issue_num} (session {state.session_count + 1})")
            branch = state.branch_name
            # Remove activation label if it still exists (might have been re-added for retry)
            try:
                issue.remove_from_labels(self.config.issue_label)
                log.info(f"Removed '{self.config.issue_label}' label from resumed issue #{issue_num}")
            except Exception as e:
                log.warning(f"Could not remove label from issue #{issue_num}: {e}")
        else:
            # New session - claim the issue
            branch = self._claim_issue_and_create_branch(issue)
            state = self.session_manager.create_state(issue_num, branch)
            log.info(f"Starting new session for issue #{issue_num}")

        return state, branch

    def _claim_issue_and_create_branch(self, issue) -> str:
        """
        Claim an issue by removing label, assigning to bot user, and determine branch name.

        Args:
            issue: GitHub Issue object

        Returns:
            Branch name to use
        """
        issue_num = issue.number

        # LOCK the issue by removing the activation label AND assigning to self
        try:
            log.info(f"Claiming issue #{issue_num} by removing '{self.config.issue_label}' label")
            issue.remove_from_labels(self.config.issue_label)
            log.info(f"Issue #{issue_num} locked (label removed)")

            import socket
            hostname = socket.gethostname()

            # Try to assign issue to current user (persistent lock across agents)
            try:
                # Get current authenticated user
                user = self.github.repo.organization or self.github.repo.owner
                username = self.github.repo._requester._Requester__auth._Auth__token  # Get auth info
                # Assign to current user - this persists even if agent crashes
                issue.add_to_assignees(self.github.repo.owner.login)
                log.info(f"Assigned issue #{issue_num} to {self.github.repo.owner.login} for persistent lock")
            except Exception as assign_error:
                log.warning(f"Could not assign issue #{issue_num}: {assign_error}")
                log.warning("Lock will only be via label removal (less reliable for multi-agent)")

            issue.create_comment(f"🤖 Agent `{hostname}` is now working on this issue...")
            log.info(f"Posted claim comment with hostname: {hostname}")
        except Exception as e:
            log.warning(f"Could not remove label or post comment on issue #{issue_num}: {e}")
            log.warning("This might indicate expired GitHub token or permission issue")
            log.warning("Continuing anyway, but other agents might pick this up too")

        # Determine branch name
        target_branch = self._extract_branch_from_issue(issue)
        if target_branch:
            log.info(f"Using existing branch from issue: {target_branch}")
            return target_branch

        # Check for existing PR
        existing_pr = self._find_pr_for_issue(issue_num)
        if existing_pr:
            branch = existing_pr.head.ref
            log.info(f"Found existing PR #{existing_pr.number} for issue #{issue_num}, reusing branch: {branch}")
            return branch

        # Create new branch name
        branch = f"{self.config.branch_prefix}issue-{issue_num}-{int(time.time())}"
        log.info(f"Creating new branch: {branch}")
        return branch

    def _prepare_branch(self, branch: str) -> None:
        """
        Ensure repository is ready and branch is checked out.

        Args:
            branch: Branch name to prepare
        """
        self.git.ensure_cloned()

        if self.git.branch_exists(branch):
            self._checkout_existing_branch(branch)
        else:
            self._create_new_branch(branch)

    def _checkout_existing_branch(self, branch: str) -> None:
        """Checkout existing branch and clean uncommitted changes."""
        log.info(f"Checking out existing branch: {branch}")

        # Clean any uncommitted changes before checkout
        status_result = self.git.run("status", "--porcelain")
        if status_result.stdout.strip():
            log.warning("Repository has uncommitted changes, cleaning before checkout...")
            self.git.run("reset", "--hard", "HEAD")
            self.git.run("clean", "-fd")

        self.git.run("checkout", branch)

        # Clean the feature branch too if needed
        status_result = self.git.run("status", "--porcelain")
        if status_result.stdout.strip():
            log.warning(f"Feature branch {branch} has uncommitted changes, cleaning...")
            self.git.run("reset", "--hard", "HEAD")
            self.git.run("clean", "-fd")

        # Pull latest changes if it's not an agent branch
        if not branch.startswith(self.config.branch_prefix):
            self.git.run("pull", "--no-rebase", "origin", branch)

    def _create_new_branch(self, branch: str) -> None:
        """Create new branch from base or fetch from remote."""
        # Check if branch exists on remote
        remote_exists = self.git.run("ls-remote", "--heads", "origin", branch)
        if remote_exists.returncode == 0 and branch in remote_exists.stdout:
            log.info(f"Fetching and checking out remote branch: {branch}")
            self.git.run("fetch", "origin", branch)
            self.git.run("checkout", "-b", branch, f"origin/{branch}")
            return

        # Create new branch from base
        base_branch = self._get_base_branch()
        log.info(f"Creating new branch: {branch} from {base_branch}")

        # Checkout base branch with fallback to default
        checkout_result = self.git.run("checkout", base_branch)
        if checkout_result.returncode != 0:
            default_branch = self.github.default_branch
            log.warning(f"Base branch {base_branch} doesn't exist, falling back to {default_branch}")
            base_branch = default_branch
            self.git.run("checkout", base_branch)

        # Pull with merge strategy
        self.git.run("pull", "--no-rebase", "origin", base_branch)

        # Create new branch
        self.git.create_branch(branch)

    def _handle_max_turns_reached(self, issue, state: SessionState, branch: str) -> IssueResult:
        """Handle case where Claude Code reached max turns."""
        state.add_note(f"Session {state.session_count}: Reached max turns, needs continuation")
        self.session_manager.save_state(state)

        # Add GitHub comment with cost
        self.github.add_issue_comment(
            issue,
            f"[AGENT] **Session {state.session_count} completed**\n\n"
            f"- Turns used: {state.total_turns_used}\n"
            f"- Tokens: {state.total_tokens:,}\n"
            f"- Cost so far: ${state.total_cost_usd:.4f}\n\n"
            f"_Continuing work in next session..._"
        )

        return IssueResult(
            success=False,
            branch=branch,
            needs_continuation=True,
            error="Reached max turns, will continue"
        )

    def _handle_no_changes(self, issue, state: SessionState, branch: str) -> IssueResult:
        """Handle case where no code changes were made (issue already resolved)."""
        log.info("No code changes were made. Checking if issue was already solved...")

        comment = (
            f"[OK] This issue appears to be already resolved.\n\n"
            f"The agent attempted to implement this but found no code changes were necessary, "
            f"which typically means the fix was already merged in a previous PR.\n\n"
            f"**Agent Stats:**\n"
            f"- Sessions: {state.session_count}\n"
            f"- Total tokens: {state.total_tokens:,}\n"
            f"- Cost: ${state.total_cost_usd:.4f} USD\n\n"
            f"Closing as already resolved."
        )

        try:
            issue.create_comment(comment)
            issue.edit(state="closed")
            log.info(f"Issue #{issue.number} closed - already resolved")
        except Exception as e:
            log.warning(f"Could not close issue: {e}")

        state.add_note("No file changes - issue already resolved, closed automatically")
        state.completed = True
        self.session_manager.save_state(state)
        self.session_manager.delete_state(issue.number)

        return IssueResult(success=True, branch=branch, pr_url="")

    def _create_or_find_pr(self, issue, state: SessionState, branch: str, output: str) -> str:
        """
        Create PR or find existing one.

        Args:
            issue: GitHub Issue object
            state: Session state
            branch: Branch name
            output: Claude Code output

        Returns:
            PR URL
        """
        issue_num = issue.number

        # Build PR body suffix with stats
        tool_usage = self._count_tool_usage(state.last_output if state.last_output else output)
        pr_body_suffix = (
            f"\n## [AGENT] Agent Stats\n\n"
            f"- **Sessions:** {state.session_count}\n"
            f"- **Total turns:** {state.total_turns_used}\n"
            f"- **Total tokens:** {state.total_tokens:,}\n"
            f"- **Estimated cost:** ${state.total_cost_usd:.4f} USD\n"
        )

        if tool_usage:
            pr_body_suffix += "\n**Custom Tools Used:**\n"
            for tool, count in tool_usage.items():
                if tool == 'semantic_search':
                    pr_body_suffix += f"- `semantic_search.py`: {count} searches (AI-powered code search)\n"
                elif tool == 'smart_test':
                    pr_body_suffix += f"- `smart_test.py`: {count} test runs (filtered test output)\n"
        else:
            pr_body_suffix += "\n**Custom Tools Used:** None\n"

        # Check if Claude Code already created a PR
        import re
        pr_url_match = re.search(r'https://github\.com/[^/]+/[^/]+/pull/\d+', output)
        if pr_url_match:
            pr_url = pr_url_match.group(0)
            log.info(f"Claude Code already created PR: {pr_url}")
            return pr_url

        # Check if PR already exists for this branch
        existing_pr = self.github.get_pr_by_branch(branch)
        if existing_pr:
            pr_url = existing_pr.html_url
            log.info(f"Found existing PR #{existing_pr.number}: {pr_url}")
            return pr_url

        # Create new PR
        base_branch = self._get_base_branch()
        previous_pr_number = None
        default_branch = self.github.default_branch

        if self.config.enable_stacked_prs and base_branch != default_branch:
            previous_pr = self.github.get_pr_by_branch(base_branch)
            if previous_pr:
                previous_pr_number = previous_pr.number
                log.info(f"Stacking on PR #{previous_pr_number} ({base_branch})")

        try:
            pr_url = self.github.create_pull_request(
                branch, issue,
                body_suffix=pr_body_suffix,
                summary=output,
                base=base_branch,
                previous_pr_number=previous_pr_number
            )
        except Exception as e:
            error_str = str(e).lower()

            if "pull request already exists" in error_str or ("422" in str(e) and "already exists" in error_str):
                log.warning(f"PR already exists for branch {branch}, fetching it...")
                existing_pr = self.github.get_pr_by_branch(branch)
                if existing_pr:
                    pr_url = existing_pr.html_url
                    log.info(f"Found existing PR #{existing_pr.number}: {pr_url}")
                else:
                    log.error(f"PR exists but couldn't find it for branch {branch}")
                    raise
            elif "base" in error_str and "invalid" in error_str:
                log.warning(f"Base branch {base_branch} invalid, falling back to {default_branch}")
                pr_url = self.github.create_pull_request(
                    branch, issue,
                    body_suffix=pr_body_suffix,
                    summary=output,
                    base=default_branch,
                    previous_pr_number=None
                )
            else:
                raise

        return pr_url

    def _handle_error(self, issue, state: SessionState, branch: str, error: Exception) -> IssueResult:
        """Handle errors during issue processing."""
        issue_num = issue.number
        log.exception(f"Failed processing issue #{issue_num}")
        state.add_note(f"Error: {str(error)[:200]}")
        self.session_manager.save_state(state)

        # Re-add label for retry (max 3 attempts)
        if state.session_count < 3:
            try:
                log.info(f"Re-adding agent-task label to issue #{issue_num} after failure (attempt {state.session_count}/3)")
                issue.add_to_labels(self.config.issue_label)
            except Exception as label_error:
                log.warning(f"Could not re-add label: {label_error}")
        else:
            log.error(f"Issue #{issue_num} failed {state.session_count} times, giving up.")
            log.error(f"Manual intervention required. Last error: {str(error)[:500]}")
            try:
                import socket
                hostname = socket.gethostname()
                issue.create_comment(
                    f"❌ Agent `{hostname}` failed to complete this issue after {state.session_count} attempts.\n\n"
                    f"Last error: `{str(error)[:300]}`\n\n"
                    f"Please investigate manually."
                )
            except:
                pass

        return IssueResult(success=False, branch=branch, error=str(error))

    def _build_prompt(self, issue, state: Optional[SessionState] = None) -> str:
        """
        Build the implementation prompt for Claude Code.

        Args:
            issue: GitHub Issue object
            state: Optional session state for continuation

        Returns:
            Formatted prompt string
        """
        from .prompt_template import build_prompt
        tools_dir = str(self.config.tools_dir) if self.config.tools_dir else "tools"
        tools_python = str(self.config.tools_python) if self.config.tools_python else "python3"
        return build_prompt(issue, state=state, tools_dir=tools_dir, tools_python=tools_python)

    def process_issue(self, issue) -> IssueResult:
        """
        Process an issue with multi-session support.

        This is the main orchestrator that delegates to smaller, focused methods.

        Args:
            issue: GitHub Issue object

        Returns:
            IssueResult with outcome
        """
        issue_num = issue.number
        state = None
        branch = None

        try:
            # Step 0: Detect issue complexity and set appropriate limits
            max_turns, max_tokens, complexity = self._detect_issue_complexity(issue)
            self.config.max_turns = max_turns
            self.config.max_tokens_per_issue = max_tokens
            # Reinitialize ClaudeCode with new turn limit
            self.claude = ClaudeCode(self.git.path, max_turns)

            # Step 1: Validate issue and setup/resume session
            state, branch = self._validate_and_setup_session(issue)

            # Step 2: Prepare branch (checkout or create)
            self._prepare_branch(branch)

            # Step 3: Build prompt and execute Claude Code
            prompt = self._build_prompt(issue, state if state.session_count > 0 else None)
            output, reached_max_turns, usage = self.claude.execute(prompt)
            log.info(f"Claude Code output:\n{output[:1000]}...")

            # Update session stats
            state.increment_session(
                turns_used=self.config.max_turns if reached_max_turns else 0,
                tokens=usage.total_tokens,
                cost=usage.estimated_cost_usd
            )
            state.last_output = output[:5000]

            # Step 4a: Check if token budget exceeded
            if state.total_tokens > self.config.max_tokens_per_issue:
                log.warning(f"Issue #{issue_num} exceeded token budget: {state.total_tokens:,} > {self.config.max_tokens_per_issue:,}")
                self.github.add_issue_comment(
                    issue,
                    f"⚠️ **Token budget exceeded**\n\n"
                    f"This issue has consumed {state.total_tokens:,} tokens "
                    f"(limit: {self.config.max_tokens_per_issue:,}).\n\n"
                    f"Cost so far: ${state.total_cost_usd:.2f}\n\n"
                    f"The agent is stopping to prevent excessive costs. "
                    f"Please review the issue complexity or increase the budget limit if needed."
                )
                state.add_note(f"Stopped: Token budget exceeded ({state.total_tokens:,} tokens)")
                self.session_manager.save_state(state)
                return IssueResult(
                    success=False,
                    branch=branch,
                    error=f"Token budget exceeded: {state.total_tokens:,} tokens"
                )

            # Step 4b: Handle max turns reached
            if reached_max_turns:
                return self._handle_max_turns_reached(issue, state, branch)

            # Step 5: Commit and push changes
            committed = self.git.commit_and_push(
                branch,
                f"Agent: implement #{issue_num} — {issue.title}",
                base_branch=self.github.default_branch,
            )

            # Step 6: Handle no changes (issue already resolved)
            if not committed:
                return self._handle_no_changes(issue, state, branch)

            # Step 7: Create or find PR
            pr_url = self._create_or_find_pr(issue, state, branch, output)

            # Step 8: Close issue and cleanup
            self.github.close_issue(issue, pr_url)
            state.completed = True
            state.pr_url = pr_url
            state.add_note(f"PR created: {pr_url}")
            self.session_manager.save_state(state)
            self.session_manager.delete_state(issue_num)

            log.info(f"PR created: {pr_url}")
            return IssueResult(success=True, branch=branch, pr_url=pr_url)

        except Exception as e:
            # Handle any errors
            return self._handle_error(issue, state, branch, e)
        finally:
            self.git.cleanup()

    def _setup_for_repo(self, repo_name: str) -> None:
        """
        Setup GitHub client, Git repo, and Claude Code for a specific repository.

        Args:
            repo_name: Repository in format "owner/repo"
        """
        self.github = GitHubClient(repo_name)
        # Use HTTPS with token authentication
        token = os.getenv("GITHUB_TOKEN")
        if not token:
            raise ValueError(
                "GITHUB_TOKEN not found in environment!\n\n"
                "Please set your GitHub Personal Access Token:\n"
                "1. Create a token at: https://github.com/settings/tokens\n"
                "2. Add to .env file: GITHUB_TOKEN=ghp_your_token_here\n"
                "3. Token needs 'repo' scope for private repos, 'public_repo' for public repos"
            )
        remote = f"https://{token}@github.com/{repo_name}.git"
        # Use repo-specific local path to avoid conflicts
        repo_slug = repo_name.replace("/", "_")
        local_path = self.config.local_path.parent / f"repo_{repo_slug}"
        self.git = GitRepo(local_path, remote, self.github.default_branch)
        self.claude = ClaudeCode(local_path, self.config.max_turns)
        log.info(f"Setup complete for {repo_name} → {local_path}")

    def run_once(self) -> None:
        """
        Check ONE repository for issues and process if found (with auto-continuation).

        Uses round-robin strategy to ensure fair distribution of work across repositories:
        - Each poll cycle checks only ONE repository (reduces API calls)
        - Rotates through repos: Repo1 → Repo2 → Repo3 → Repo1...
        - If issue found: process it, then next cycle checks next repo
        - If no issue found: next cycle checks next repo anyway

        Example with 3 repos (A, B, C):
        - Cycle 1: Check A → no issue → sleep
        - Cycle 2: Check B → found issue → process → sleep
        - Cycle 3: Check C → no issue → sleep
        - Cycle 4: Check A → ...

        This reduces API calls from N repos/cycle to 1 repo/cycle.
        """
        num_repos = len(self.config.repo_names)

        # Round-robin: check ONLY the next repo in rotation
        self._last_repo_index = (self._last_repo_index + 1) % num_repos
        repo_name = self.config.repo_names[self._last_repo_index]

        log.info(f"Checking repository: {repo_name}")
        self._setup_for_repo(repo_name)

        issue = self.github.find_next_issue(self.config.issue_label)
        if not issue:
            log.info(f"No open issues found in {repo_name} with label: {self.config.issue_label}")
            return  # Done for this cycle, next cycle will check next repo

        log.info(f"Found issue #{issue.number} in {repo_name}: {issue.title}")

        # Process with auto-continuation
        max_sessions = 20  # Prevent infinite loops (20 sessions × 500 turns = 10,000 turns max)
        for session in range(max_sessions):
            result = self.process_issue(issue)

            if result.success:
                log.info(f"Issue #{issue.number} done → {result.pr_url}")
                break

            if result.needs_continuation:
                log.info(f"Session {session + 1} done, continuing...")
                time.sleep(3)  # Brief pause between sessions
                continue

            # Failed without continuation
            log.error(f"Issue #{issue.number} failed: {result.error}")
            break

        # Done processing (or no issue found)
        # Next run_once() will check next repo in rotation

    def run_single_issue(self, issue_number: int) -> None:
        """Process a specific issue by number (for benchmarking).

        Note: Uses first repository in config for backwards compatibility.
        """
        # Use first repo for single issue mode
        repo_name = self.config.repo_names[0]
        log.info(f"Single issue mode - using repository: {repo_name}")
        self._setup_for_repo(repo_name)

        try:
            issue = self.github.repo.get_issue(issue_number)
        except Exception as e:
            log.error(f"Could not fetch issue #{issue_number}: {e}")
            return

        if issue.state != "open":
            log.warning(f"Issue #{issue_number} is not open (state: {issue.state})")
            # Continue anyway for benchmarking purposes

        log.info(f"Processing issue #{issue.number}: {issue.title}")

        # Process with auto-continuation
        max_sessions = 20
        for session in range(max_sessions):
            result = self.process_issue(issue)

            if result.success:
                log.info(f"Issue #{issue.number} done → {result.pr_url}")
                break

            if result.needs_continuation:
                log.info(f"Session {session + 1} done, continuing...")
                time.sleep(3)
                continue

            # Failed without continuation
            log.error(f"Issue #{issue.number} failed: {result.error}")
            break

    def restart_current_issue(self) -> bool:
        """
        Automatically detect and restart the most recent active issue.

        This is a simplified version that:
        1. Finds the most recent active session
        2. Fetches fresh issue data from GitHub
        3. Updates base branch
        4. Deletes session state and old branch
        5. Agent will start fresh on next run

        Returns:
            True if restart successful, False otherwise
        """
        try:
            # Find all active sessions
            session_files = list(self.config.session_dir.glob("issue-*.json"))
            if not session_files:
                log.warning("No active sessions found")
                return False

            # Get the most recently modified session
            latest_session = max(session_files, key=lambda p: p.stat().st_mtime)
            issue_number = int(latest_session.stem.split('-')[1])

            log.info(f"Found active session for issue #{issue_number}")

            # Load the session to get branch and determine which repo
            state = self.session_manager.load_state(issue_number)
            if not state:
                log.error(f"Failed to load session state for issue #{issue_number}")
                return False

            # Try to determine which repository this issue belongs to
            # We'll check all configured repos
            found_repo = None
            for repo_name in self.config.repo_names:
                try:
                    self._setup_for_repo(repo_name)
                    issue = self.github.repo.get_issue(issue_number)
                    found_repo = repo_name
                    log.info(f"Issue #{issue_number} found in repository: {repo_name}")
                    log.info(f"Issue title: {issue.title}")
                    break
                except Exception:
                    continue

            if not found_repo:
                log.error(f"Could not find issue #{issue_number} in any configured repository")
                return False

            # Now restart with the found repository
            log.info(f"Restarting issue #{issue_number} from scratch...")
            return self.restart_issue(found_repo, issue_number, update_base=True, delete_branch=True)

        except Exception as e:
            log.error(f"Failed to restart current issue: {e}")
            return False

    def restart_issue(self, repo_name: str, issue_number: int, update_base: bool = True, delete_branch: bool = False) -> bool:
        """
        Restart work on an issue from scratch.

        This will:
        1. Delete the session state (so agent starts fresh)
        2. Optionally update base branch (pull latest main/dev)
        3. Optionally delete the old feature branch

        Args:
            repo_name: Repository name (e.g., "aignermax/Lunima")
            issue_number: GitHub issue number
            update_base: Whether to pull latest changes on base branch (default: True)
            delete_branch: Whether to delete the old feature branch (default: False)

        Returns:
            True if restart successful, False otherwise
        """
        try:
            # Setup for the specific repository
            self._setup_for_repo(repo_name)

            # Load existing state to get branch name
            state = self.session_manager.load_state(issue_number)
            old_branch = state.branch_name if state else None

            # Delete session state
            self.session_manager.delete_state(issue_number)
            log.info(f"Deleted session state for issue #{issue_number}")

            # Update base branch if requested
            if update_base:
                self.update_base_branch(repo_name)

            # Delete old feature branch if requested and exists
            if delete_branch and old_branch:
                # Switch to base branch first
                base_branch = self._get_base_branch()
                self.git.run("checkout", base_branch)

                # Delete local branch
                if self.git.branch_exists(old_branch):
                    result = self.git.run("branch", "-D", old_branch)
                    if result.returncode == 0:
                        log.info(f"Deleted local branch: {old_branch}")
                    else:
                        log.warning(f"Failed to delete local branch {old_branch}: {result.stderr}")

                # Also try to delete ALL remote branches for this issue
                # (there might be multiple from previous restarts)
                log.info(f"Checking for remote branches for issue #{issue_number}")
                remote_branches_result = self.git.run("ls-remote", "--heads", "origin")
                if remote_branches_result.returncode == 0:
                    # Parse remote branches and find all matching issue-{number}-*
                    for line in remote_branches_result.stdout.splitlines():
                        if f"issue-{issue_number}-" in line:
                            # Extract branch name from: "hash\trefs/heads/branch-name"
                            parts = line.split("refs/heads/")
                            if len(parts) == 2:
                                remote_branch = parts[1].strip()
                                log.info(f"Deleting remote branch: {remote_branch}")
                                delete_result = self.git.run("push", "origin", "--delete", remote_branch)
                                if delete_result.returncode == 0:
                                    log.info(f"✓ Deleted remote branch: {remote_branch}")
                                else:
                                    log.warning(f"Failed to delete remote branch {remote_branch}: {delete_result.stderr}")

            log.info(f"✓ Issue #{issue_number} ready to restart from scratch")
            return True

        except Exception as e:
            log.error(f"Failed to restart issue #{issue_number}: {e}")
            return False

    def update_base_branch(self, repo_name: str, rebase_feature_branch: bool = True) -> bool:
        """
        Update the base branch (main/dev) with latest changes from remote.
        If currently on a feature branch, rebase it onto the updated base.

        Args:
            repo_name: Repository name (e.g., "aignermax/Lunima")
            rebase_feature_branch: If True and on feature branch, rebase it onto updated base

        Returns:
            True if update successful, False otherwise
        """
        try:
            # Setup for the specific repository
            self._setup_for_repo(repo_name)

            # Ensure repo is cloned
            self.git.ensure_cloned()

            # Get current branch before switching
            current_branch_result = self.git.run("branch", "--show-current")
            current_branch = current_branch_result.stdout.strip() if current_branch_result.returncode == 0 else None

            # Get working branch (dev or main)
            working_branch = self.git.get_working_branch()

            # Check if we're on a feature branch
            is_feature_branch = current_branch and current_branch.startswith(self.config.branch_prefix)

            # Checkout and pull base branch
            log.info(f"Updating base branch: {working_branch}")
            self.git.run("checkout", working_branch)
            result = self.git.run("pull", "--ff-only", "origin", working_branch)

            if result.returncode != 0:
                log.error(f"Failed to update {working_branch}: {result.stderr}")
                return False

            log.info(f"✓ Base branch {working_branch} updated successfully")

            # Rebase feature branch if requested and applicable
            if rebase_feature_branch and is_feature_branch and current_branch:
                log.info(f"Rebasing feature branch {current_branch} onto {working_branch}")
                self.git.run("checkout", current_branch)
                rebase_result = self.git.run("rebase", working_branch)

                if rebase_result.returncode != 0:
                    log.warning(f"Rebase had conflicts or failed: {rebase_result.stderr}")
                    log.warning(f"You may need to resolve conflicts manually")
                    # Try to abort the rebase
                    self.git.run("rebase", "--abort")
                    return False
                else:
                    log.info(f"✓ Feature branch {current_branch} rebased successfully")

            return True

        except Exception as e:
            log.error(f"Failed to update base branch: {e}")
            return False

    def run_forever(self) -> None:
        """Poll loop — runs until killed."""
        log.info(f"Agent started. Polling every {self.config.poll_interval}s.")
        log.info(f"Repositories: {', '.join(self.config.repo_names)} | Activation Label: {self.config.issue_label} | Complexity Tag: {self.config.complexity_tag}")

        while True:
            try:
                self.run_once()
            except Exception as e:
                log.exception("Unexpected error in poll loop")

            log.info(f"Sleeping {self.config.poll_interval}s ...")
            time.sleep(self.config.poll_interval)
