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
        # Initialize github client, git repo, etc. per repository (done in run methods)
        self.github = None
        self.git = None
        self.claude = None
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

    def _get_base_branch(self) -> str:
        """
        Get the base branch for the next PR.

        If stacked PRs enabled, finds the most recently created open PR
        created by the agent and uses its head branch as the base.

        Returns:
            - If stacked PRs enabled and recent agent PR found: that PR's head branch
            - Otherwise: repository's default branch (e.g., "main", "dev", "master")
        """
        default = self.github.default_branch

        if not self.config.enable_stacked_prs:
            return default

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

            log.info(f"No recent agent PRs found, using {default} as base")
            return default

        except Exception as e:
            log.warning(f"Failed to fetch recent PRs for stacking: {e}")
            return default

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
        is_feature_branch = state and not state.branch_name.startswith(self.config.branch_prefix)
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
5. Complete the implementation (if it's a new feature, include all vertical slice layers)

**Do not give up!** Take as many attempts as needed to get tests passing.

Read CLAUDE.md for all project conventions."""
        else:
            # Initial prompt
            prompt = f"""You are a senior C# / Avalonia developer implementing issue #{issue.number}: {issue.title}
{branch_note}

## CRITICAL: Read CLAUDE.md First

The repository contains `CLAUDE.md` with complete architecture guidelines. **Read it immediately.**

## Architecture Guidelines

**For NEW FEATURES:** Follow Vertical Slice Architecture:
1. Core logic (Connect-A-Pic-Core/)
2. ViewModel (CAP.Avalonia/ViewModels/) with [ObservableProperty] and [RelayCommand]
3. View/AXAML (MainWindow.axaml or new view)
4. DI wiring (App.axaml.cs if needed)
5. Unit tests (UnitTests/)
6. Integration tests (Core + ViewModel)

**For TESTS-ONLY or BUGFIXES:** UI is NOT required. Focus on:
- Writing comprehensive tests
- Fixing the specific bug
- No need for ViewModel/View if not adding user-facing features

**Important:** Read the issue description to determine which category this is.

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

1. **First:** Read `CLAUDE.md` for architecture patterns and `CODEBASE_MAP.md` for codebase overview
2. **Search efficiently:** Use glob patterns to find relevant files instead of reading everything
   - Example: Use `**/*ViewModel.cs` to find all ViewModels
   - Example: Use `**/MainWindow.axaml` to find the main UI
3. **Find similar features:** Search for existing features similar to what you're building
   - Example: For analysis features, check `Analysis/ParameterSweep*` files
   - Example: For UI features, check existing ViewModel patterns
4. **Implement complete solution:**
   - For NEW FEATURES: Core → ViewModel → View → Tests (full vertical slice)
   - For TESTS/BUGFIXES: Just write tests or fix the bug (no UI needed)
5. **Build and test iteratively:** Fix errors immediately, don't accumulate them
6. **PERSISTENCE:** Complex issues may take many attempts - keep trying until tests pass!

## EFFICIENCY TIPS

- Don't read entire files unless necessary - use grep/search first
- Reuse existing patterns from similar features
- Test early and often (dotnet build && dotnet test)
- Keep files under 250 lines (split if needed)

## 🔍 SEMANTIC SEARCH TOOL

You have access to a semantic code search tool that uses AI embeddings to find relevant code.

**IMPORTANT:** The tools are in a separate Python venv. Use the full path to the venv Python:

```bash
/home/aigner/connect-a-pic-agent/venv/bin/python3 /home/aigner/connect-a-pic-agent/tools/semantic_search.py "your search query"
```

**Examples:**
- `/home/aigner/connect-a-pic-agent/venv/bin/python3 /home/aigner/connect-a-pic-agent/tools/semantic_search.py "ViewModel for analysis features"`
- `/home/aigner/connect-a-pic-agent/venv/bin/python3 /home/aigner/connect-a-pic-agent/tools/semantic_search.py "where is bounding box calculation?"`
- `/home/aigner/connect-a-pic-agent/venv/bin/python3 /home/aigner/connect-a-pic-agent/tools/semantic_search.py "test files for parameter sweeping"`

This is MUCH better than grep for finding relevant code! Use it early and often.

## 🧪 SMART TEST TOOL

**IMPORTANT:** Do NOT use `dotnet test` directly! Use the smart test tool instead.

The tool is in a separate location - use the full path:

```bash
/home/aigner/connect-a-pic-agent/venv/bin/python3 /home/aigner/connect-a-pic-agent/tools/smart_test.py [optional-filter]
```

This filters output to show only summary instead of all 1193 test results!

**Examples:**
- `/home/aigner/connect-a-pic-agent/venv/bin/python3 /home/aigner/connect-a-pic-agent/tools/smart_test.py` - Run all tests, show compact summary
- `/home/aigner/connect-a-pic-agent/venv/bin/python3 /home/aigner/connect-a-pic-agent/tools/smart_test.py ParameterSweeper` - Run only ParameterSweeper tests
- `/home/aigner/connect-a-pic-agent/venv/bin/python3 /home/aigner/connect-a-pic-agent/tools/smart_test.py BoundingBox` - Run only BoundingBox-related tests
- `/home/aigner/connect-a-pic-agent/venv/bin/python3 /home/aigner/connect-a-pic-agent/tools/smart_test.py --file MyFeatureTests.cs` - Run specific test file

The tool shows:
- [OK]/[FAIL] Pass/Fail status
- Number of tests (passed/failed/skipped)
- Duration
- Failed test names (if any)

Much cleaner than raw dotnet output!"""

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
                    self.git.run("pull", "--no-rebase", "origin", branch)
            else:
                # Check if branch exists on remote
                remote_exists = self.git.run("ls-remote", "--heads", "origin", branch)
                if remote_exists.returncode == 0 and branch in remote_exists.stdout:
                    log.info(f"Fetching and checking out remote branch: {branch}")
                    self.git.run("fetch", "origin", branch)
                    self.git.run("checkout", "-b", branch, f"origin/{branch}")
                else:
                    # Get base branch for stacking
                    base_branch = self._get_base_branch()
                    log.info(f"Creating new branch: {branch} from {base_branch}")

                    # Checkout base branch first (with fallback to default if it doesn't exist)
                    checkout_result = self.git.run("checkout", base_branch)
                    if checkout_result.returncode != 0:
                        default_branch = self.github.default_branch
                        log.warning(f"Base branch {base_branch} doesn't exist, falling back to {default_branch}")
                        base_branch = default_branch
                        self.git.run("checkout", base_branch)

                    # Pull with merge strategy to avoid divergent branches error
                    self.git.run("pull", "--no-rebase", "origin", base_branch)

                    # Create new branch from base
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

            # Try to commit and push
            committed = self.git.commit_and_push(
                branch,
                f"Agent: implement #{issue_num} — {issue.title}",
                base_branch=self.github.default_branch,
            )

            if not committed:
                # Check if issue was already solved (e.g., merged in another PR)
                log.info("No code changes were made. Checking if issue was already solved...")

                # Comment on issue and close it
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
                    log.info(f"Issue #{issue_num} closed - already resolved")
                except Exception as e:
                    log.warning(f"Could not close issue: {e}")

                state.add_note("No file changes - issue already resolved, closed automatically")
                state.completed = True
                self.session_manager.save_state(state)
                self.session_manager.delete_state(issue_num)  # Clean up session

                return IssueResult(
                    success=True,  # Changed to True since issue was handled
                    branch=branch,
                    pr_url="",  # No PR needed
                )

            # Create PR with cost information
            pr_body_suffix = (
                f"\n## [AGENT] Agent Stats\n\n"
                f"- **Sessions:** {state.session_count}\n"
                f"- **Total turns:** {state.total_turns_used}\n"
                f"- **Total tokens:** {state.total_tokens:,}\n"
                f"- **Estimated cost:** ${state.total_cost_usd:.4f} USD\n"
            )

            # Determine base branch and previous PR for stacking
            base_branch = self._get_base_branch()
            previous_pr_number = None

            default_branch = self.github.default_branch

            if self.config.enable_stacked_prs and base_branch != default_branch:
                # Find PR number for the base branch
                previous_pr = self.github.get_pr_by_branch(base_branch)
                if previous_pr:
                    previous_pr_number = previous_pr.number
                    log.info(f"Stacking on PR #{previous_pr_number} ({base_branch})")

            # Try to create PR with stacked base, fallback to default if base branch was deleted
            try:
                pr_url = self.github.create_pull_request(
                    branch, issue,
                    body_suffix=pr_body_suffix,
                    summary=output,  # Include Claude Code's summary
                    base=base_branch,
                    previous_pr_number=previous_pr_number
                )
            except Exception as e:
                error_str = str(e).lower()

                # Handle "PR already exists" error
                if "pull request already exists" in error_str or ("422" in str(e) and "already exists" in error_str):
                    log.warning(f"PR already exists for branch {branch}, checking if it's ours...")

                    # Try to find the existing PR
                    existing_pr = self.github.get_pr_by_branch(branch)
                    if existing_pr:
                        pr_url = existing_pr.html_url
                        log.info(f"Found existing PR #{existing_pr.number}: {pr_url}")
                        log.info("Work is already complete, marking as done")
                    else:
                        log.error(f"PR exists but couldn't find it for branch {branch}")
                        raise

                # Handle invalid base branch
                elif "base" in error_str and "invalid" in error_str:
                    log.warning(f"Base branch {base_branch} is invalid (probably deleted), falling back to {default_branch}")
                    # Create PR targeting default branch instead
                    pr_url = self.github.create_pull_request(
                        branch, issue,
                        body_suffix=pr_body_suffix,
                        summary=output,
                        base=default_branch,
                        previous_pr_number=None
                    )
                else:
                    raise

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

    def _setup_for_repo(self, repo_name: str) -> None:
        """
        Setup GitHub client, Git repo, and Claude Code for a specific repository.

        Args:
            repo_name: Repository in format "owner/repo"
        """
        self.github = GitHubClient(repo_name)
        remote = f"https://github.com/{repo_name}.git"
        # Use repo-specific local path to avoid conflicts
        repo_slug = repo_name.replace("/", "_")
        local_path = self.config.local_path.parent / f"repo_{repo_slug}"
        self.git = GitRepo(local_path, remote)
        self.claude = ClaudeCode(local_path, self.config.max_turns)
        log.info(f"Setup complete for {repo_name} → {local_path}")

    def run_once(self) -> None:
        """Check for one issue across all repositories and process it (with auto-continuation)."""
        # Iterate through all configured repositories
        for repo_name in self.config.repo_names:
            log.info(f"Checking repository: {repo_name}")
            self._setup_for_repo(repo_name)

            issue = self.github.find_next_issue(self.config.issue_label)
            if not issue:
                log.info(f"No open {self.config.issue_label} issues found in {repo_name}")
                continue

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

            # Only process one issue per run_once call
            return

        log.info(f"No {self.config.issue_label} issues found in any repository")

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

    def run_forever(self) -> None:
        """Poll loop — runs until killed."""
        log.info(f"Agent started. Polling every {self.config.poll_interval}s.")
        log.info(f"Repositories: {', '.join(self.config.repo_names)} | Label: {self.config.issue_label}")

        while True:
            try:
                self.run_once()
            except Exception as e:
                log.exception("Unexpected error in poll loop")

            log.info(f"Sleeping {self.config.poll_interval}s ...")
            time.sleep(self.config.poll_interval)
