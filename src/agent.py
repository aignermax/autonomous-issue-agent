"""
Autonomous Issue Agent - Main orchestration with multi-session support.
"""

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
        self.github = GitHubClient(config.repo_name)
        remote = f"https://github.com/{config.repo_name}.git"
        self.git = GitRepo(config.local_path, remote)
        self.claude = ClaudeCode(config.local_path, config.max_turns)
        self.session_manager = SessionManager(config.session_dir)

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
        patterns = [
            r'(?:work\s+on\s+)?branch:\s*([^\s\n]+)',
            r'(?:use\s+)?branch\s*=\s*([^\s\n]+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, issue.body, re.IGNORECASE)
            if match:
                branch_name = match.group(1).strip()
                log.info(f"Found target branch in issue body: {branch_name}")
                return branch_name

        return None

    def _build_prompt(self, issue, state: Optional[SessionState] = None) -> str:
        """
        Build the implementation prompt for Claude Code.

        Args:
            issue: GitHub Issue object
            state: Optional session state for continuation

        Returns:
            Formatted prompt string
        """
        # Determine if working on existing feature branch
        is_feature_branch = not state.branch_name.startswith(self.config.branch_prefix)
        branch_note = f"\n**IMPORTANT:** You are working on existing branch: `{state.branch_name}`\nDo NOT create a new branch. All work must be on this branch." if is_feature_branch else ""

        if state and state.session_count > 0:
            # Continuation prompt
            prompt = f"""You are continuing work on issue #{issue.number}: {issue.title}

## Progress So Far

Session {state.session_count + 1} - Total turns used: {state.total_turns_used}
Branch: {state.branch_name}{branch_note}

{chr(10).join(state.notes[-5:])}  # Last 5 notes

## Your Task

Continue where you left off. Review what's been done, then:
1. Check build status: `dotnet build`
2. Check test status: `dotnet test`
3. Continue implementing missing pieces
4. Fix any failing tests
5. Complete the vertical slice (Core + ViewModel + View + Tests)

Read CLAUDE.md for all project conventions."""
        else:
            # Initial prompt
            prompt = f"""You are a senior C# / Avalonia developer implementing issue #{issue.number}: {issue.title}
{branch_note}

## CRITICAL: Read CLAUDE.md First

The repository contains `CLAUDE.md` with complete architecture guidelines. **Read it immediately.**

## MANDATORY: Vertical Slice Architecture

**EVERY feature MUST include ALL layers:**
1. Core logic (Connect-A-Pic-Core/)
2. ViewModel (CAP.Avalonia/ViewModels/) with [ObservableProperty] and [RelayCommand]
3. View/AXAML (MainWindow.axaml or new view)
4. DI wiring (App.axaml.cs if needed)
5. Unit tests (UnitTests/)
6. Integration tests (Core + ViewModel)

**Do NOT create backend-only code. The PR must be testable in the UI.**

## Code Quality Rules

- **Max 250 lines per NEW file**
- SOLID principles strictly
- Methods max ~20 lines
- Use CommunityToolkit.Mvvm patterns
- XML documentation for all public members
- No magic numbers

## Build & Verification

Before finishing:
1. `dotnet build` — must succeed
2. `dotnet test` — all tests must pass
3. Fix all errors and warnings
4. **Do not stop until everything works**

## Issue #{issue.number}: {issue.title}

{issue.body or 'No description provided.'}

## YOUR TASK

1. Read `CLAUDE.md` for architecture patterns
2. Explore repository structure
3. Implement complete vertical slice (Core → ViewModel → View → Tests)
4. Build and test until everything passes
5. Verify the feature is testable in the UI"""

        return prompt

    def process_issue(self, issue) -> IssueResult:
        """
        Process an issue with multi-session support.

        Args:
            issue: GitHub Issue object

        Returns:
            IssueResult with outcome
        """
        issue_num = issue.number

        # Check for existing session
        state = self.session_manager.load_state(issue_num)

        if state:
            log.info(f"Resuming session for issue #{issue_num} (session {state.session_count + 1})")
            branch = state.branch_name
        else:
            # New session - check if issue specifies a branch
            target_branch = self._extract_branch_from_issue(issue)

            if target_branch:
                branch = target_branch
                log.info(f"Using existing branch from issue: {branch}")
            else:
                # Create new branch
                branch = f"{self.config.branch_prefix}issue-{issue_num}-{int(time.time())}"
                log.info(f"Creating new branch: {branch}")

            state = self.session_manager.create_state(issue_num, branch)
            log.info(f"Starting new session for issue #{issue_num}")

        try:
            # Ensure repo is up to date
            self.git.ensure_cloned()

            # Handle branch: checkout existing or create new
            if self.git.branch_exists(branch):
                log.info(f"Checking out existing branch: {branch}")
                self.git.run("checkout", branch)
                # Pull latest changes if it's a feature branch
                if not branch.startswith(self.config.branch_prefix):
                    self.git.run("pull", "origin", branch)
            else:
                # Check if branch exists on remote
                remote_exists = self.git.run("ls-remote", "--heads", "origin", branch)
                if remote_exists.returncode == 0 and branch in remote_exists.stdout:
                    log.info(f"Fetching and checking out remote branch: {branch}")
                    self.git.run("fetch", "origin", branch)
                    self.git.run("checkout", "-b", branch, f"origin/{branch}")
                else:
                    log.info(f"Creating new branch: {branch}")
                    self.git.create_branch(branch)

            # Build prompt
            prompt = self._build_prompt(issue, state if state.session_count > 0 else None)

            # Execute Claude Code
            output, reached_max_turns, usage = self.claude.execute(prompt)
            log.info(f"Claude Code output:\n{output[:1000]}...")

            # Update session state with usage stats
            state.increment_session(
                turns_used=self.config.max_turns if reached_max_turns else 0,
                tokens=usage.total_tokens,
                cost=usage.estimated_cost_usd
            )
            state.last_output = output[:5000]  # Keep last 5k chars

            if reached_max_turns:
                state.add_note(f"Session {state.session_count}: Reached max turns, needs continuation")
                self.session_manager.save_state(state)

                # Add GitHub comment with cost
                self.github.add_issue_comment(
                    issue,
                    f"🤖 **Session {state.session_count} completed**\n\n"
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

            # Try to commit and push
            committed = self.git.commit_and_push(
                branch,
                f"Agent: implement #{issue_num} — {issue.title}",
            )

            if not committed:
                state.add_note("No file changes produced")
                self.session_manager.save_state(state)
                return IssueResult(
                    success=False,
                    branch=branch,
                    error="No file changes produced.",
                )

            # Create PR with cost information
            pr_body_suffix = (
                f"\n## 🤖 Agent Stats\n\n"
                f"- **Sessions:** {state.session_count}\n"
                f"- **Total turns:** {state.total_turns_used}\n"
                f"- **Total tokens:** {state.total_tokens:,}\n"
                f"- **Estimated cost:** ${state.total_cost_usd:.4f} USD\n"
            )
            pr_url = self.github.create_pull_request(branch, issue, pr_body_suffix)
            self.github.close_issue(issue, pr_url)

            # Mark session as completed
            state.completed = True
            state.pr_url = pr_url
            state.add_note(f"PR created: {pr_url}")
            self.session_manager.save_state(state)

            # Cleanup after success
            self.session_manager.delete_state(issue_num)

            log.info(f"PR created: {pr_url}")
            return IssueResult(success=True, branch=branch, pr_url=pr_url)

        except Exception as e:
            log.exception(f"Failed processing issue #{issue_num}")
            state.add_note(f"Error: {str(e)[:200]}")
            self.session_manager.save_state(state)
            return IssueResult(success=False, branch=branch, error=str(e))

        finally:
            self.git.cleanup()

    def run_once(self) -> None:
        """Check for one issue and process it (with auto-continuation)."""
        issue = self.github.find_next_issue(self.config.issue_label)
        if not issue:
            log.info("No open agent-task issues found.")
            return

        log.info(f"Found issue #{issue.number}: {issue.title}")

        # Process with auto-continuation
        max_sessions = 10  # Prevent infinite loops
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

    def run_forever(self) -> None:
        """Poll loop — runs until killed."""
        log.info(f"Agent started. Polling every {self.config.poll_interval}s.")
        log.info(f"Repo: {self.config.repo_name} | Label: {self.config.issue_label}")

        while True:
            try:
                self.run_once()
            except Exception as e:
                log.exception("Unexpected error in poll loop")

            log.info(f"Sleeping {self.config.poll_interval}s ...")
            time.sleep(self.config.poll_interval)
