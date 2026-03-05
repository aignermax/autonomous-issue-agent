"""
Autonomous GitHub Issue Agent
Uses Claude Code CLI in headless mode to implement issues with full repo awareness.
"""

import os
import sys
import subprocess
import time
import json
import logging
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path

from github import Github, Auth

# ==============================
# CONFIG
# ==============================

REPO_NAME = os.environ.get("AGENT_REPO", "aignermax/Connect-A-PIC-Pro")
LOCAL_PATH = Path(os.environ.get("AGENT_REPO_PATH", "./repo"))
BRANCH_PREFIX = "agent/"
POLL_INTERVAL = int(os.environ.get("AGENT_POLL_INTERVAL", "300"))
ISSUE_LABEL = os.environ.get("AGENT_ISSUE_LABEL", "agent-task")
MAX_TURNS = int(os.environ.get("AGENT_MAX_TURNS", "30"))

# ==============================
# LOGGING
# ==============================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("agent.log"),
    ],
)
log = logging.getLogger("agent")


# ==============================
# DATA
# ==============================

@dataclass
class IssueResult:
    success: bool
    branch: str
    pr_url: str = ""
    error: str = ""


# ==============================
# GIT OPERATIONS
# ==============================

class GitRepo:
    """Handles all local git operations."""

    def __init__(self, path: Path, remote_url: str):
        self.path = path
        self.remote_url = remote_url

    def run(self, *args: str) -> subprocess.CompletedProcess:
        result = subprocess.run(
            ["git", *args],
            cwd=self.path,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            log.warning(f"git {' '.join(args)}: {result.stderr.strip()}")
        return result

    def ensure_cloned(self):
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

    def create_branch(self, name: str):
        self.run("checkout", "-b", name)

    def commit_and_push(self, branch: str, message: str):
        self.run("add", ".")
        # Check if there are changes to commit
        status = self.run("status", "--porcelain")
        if not status.stdout.strip():
            log.info("No changes to commit.")
            return False
        self.run("commit", "-m", message)
        self.run("push", "--set-upstream", "origin", branch)
        return True

    def cleanup(self):
        """Return to main and delete working branch."""
        self.run("checkout", "main")


# ==============================
# CLAUDE CODE INTEGRATION
# ==============================

class ClaudeCode:
    """Runs Claude Code CLI in headless mode."""

    def __init__(self, working_dir: Path, max_turns: int = 30):
        self.working_dir = working_dir
        self.max_turns = max_turns
        self._verify_installation()

    def _verify_installation(self):
        result = subprocess.run(
            ["claude", "--version"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                "Claude Code CLI not found. "
                "Install: npm install -g @anthropic-ai/claude-code"
            )
        log.info(f"Claude Code version: {result.stdout.strip()}")

    def execute(self, prompt: str) -> str:
        """Run a prompt through Claude Code headless mode."""
        cmd = [
            "claude", "-p", prompt,
            "--dangerously-skip-permissions",
            "--output-format", "text",
            "--max-turns", str(self.max_turns),
        ]

        log.info("Invoking Claude Code ...")
        result = subprocess.run(
            cmd,
            cwd=self.working_dir,
            capture_output=True,
            text=True,
            timeout=600,  # 10 min safety timeout
        )

        if result.returncode != 0:
            log.error(f"Claude Code failed: {result.stderr[:500]}")
            raise RuntimeError(f"Claude Code exit code {result.returncode}")

        return result.stdout


# ==============================
# GITHUB OPERATIONS
# ==============================

class GitHubClient:
    """Handles GitHub API interactions."""

    def __init__(self, repo_name: str):
        token = os.environ["GITHUB_TOKEN"]
        self.gh = Github(auth=Auth.Token(token))
        self.repo = self.gh.get_repo(repo_name)

    def find_next_issue(self, label: str):
        for issue in self.repo.get_issues(state="open", labels=[label]):
            if not issue.pull_request:
                return issue
        return None

    def create_pull_request(self, branch: str, issue) -> str:
        pr = self.repo.create_pull(
            title=f"Agent: {issue.title}",
            body=(
                f"Automated implementation for #{issue.number}\n\n"
                f"---\n"
                f"*Generated by autonomous agent using Claude Code.*"
            ),
            head=branch,
            base="main",
        )
        return pr.html_url

    def close_issue(self, issue, pr_url: str):
        issue.create_comment(
            f"Implementation complete. PR: {pr_url}"
        )
        issue.edit(state="closed")


# ==============================
# PROMPT BUILDER
# ==============================

def build_prompt(issue) -> str:
    """Build the implementation prompt for Claude Code."""
    return f"""You are a senior C# / Avalonia developer implementing a GitHub issue for Connect-A-PIC-Pro.

## CRITICAL: Read CLAUDE.md First

The repository contains a `CLAUDE.md` file with complete architecture guidelines. **Read it immediately.**

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

- **Max 250 lines per NEW file** (existing large files are OK)
- SOLID principles strictly
- Methods max ~20 lines
- Use CommunityToolkit.Mvvm patterns
- XML documentation for all public members
- No magic numbers, use named constants

## Build & Verification

Before finishing:
1. `dotnet build` — must succeed
2. `dotnet test` — all tests must pass
3. Fix all errors and warnings
4. **Do not stop until everything works**

## ISSUE #{issue.number}: {issue.title}

{issue.body or 'No description provided.'}

## YOUR TASK

1. Read `CLAUDE.md` for architecture patterns
2. Explore repository structure (MainViewModel, ParameterSweepViewModel as examples)
3. Implement complete vertical slice (Core → ViewModel → View → Tests)
4. Build and test until everything passes
5. Verify the feature is testable in the UI
"""


# ==============================
# MAIN AGENT
# ==============================

class Agent:
    """Orchestrates the full issue-to-PR pipeline."""

    def __init__(self):
        self.github = GitHubClient(REPO_NAME)
        remote = f"https://github.com/{REPO_NAME}.git"
        self.git = GitRepo(LOCAL_PATH, remote)
        self.claude = ClaudeCode(LOCAL_PATH, MAX_TURNS)

    def process_issue(self, issue) -> IssueResult:
        branch = f"{BRANCH_PREFIX}issue-{issue.number}-{int(time.time())}"

        try:
            self.git.ensure_cloned()
            self.git.create_branch(branch)

            prompt = build_prompt(issue)
            output = self.claude.execute(prompt)
            log.info(f"Claude Code output:\n{output[:1000]}...")

            committed = self.git.commit_and_push(
                branch,
                f"Agent: implement #{issue.number} — {issue.title}",
            )

            if not committed:
                return IssueResult(
                    success=False,
                    branch=branch,
                    error="No file changes produced.",
                )

            pr_url = self.github.create_pull_request(branch, issue)
            self.github.close_issue(issue, pr_url)

            log.info(f"PR created: {pr_url}")
            return IssueResult(success=True, branch=branch, pr_url=pr_url)

        except Exception as e:
            log.exception(f"Failed processing issue #{issue.number}")
            return IssueResult(success=False, branch=branch, error=str(e))

        finally:
            self.git.cleanup()

    def run_once(self):
        """Check for one issue and process it."""
        issue = self.github.find_next_issue(ISSUE_LABEL)
        if not issue:
            log.info("No open agent-task issues found.")
            return

        log.info(f"Found issue #{issue.number}: {issue.title}")
        result = self.process_issue(issue)

        if result.success:
            log.info(f"Issue #{issue.number} done → {result.pr_url}")
        else:
            log.error(f"Issue #{issue.number} failed: {result.error}")

    def run_forever(self):
        """Poll loop — runs until killed."""
        log.info(f"Agent started. Polling every {POLL_INTERVAL}s.")
        log.info(f"Repo: {REPO_NAME} | Label: {ISSUE_LABEL}")

        while True:
            try:
                self.run_once()
            except Exception as e:
                log.exception("Unexpected error in poll loop")

            log.info(f"Sleeping {POLL_INTERVAL}s ...")
            time.sleep(POLL_INTERVAL)


# ==============================
# ENTRY POINT
# ==============================

def main():
    # Validate required env vars
    missing = []
    if not os.environ.get("GITHUB_TOKEN"):
        missing.append("GITHUB_TOKEN")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        missing.append("ANTHROPIC_API_KEY")
    if missing:
        log.error(f"Missing environment variables: {', '.join(missing)}")
        log.error("Please create a .env file with your credentials:")
        log.error("  cp .env.example .env")
        log.error("Then add your tokens to .env and run ./run_agent.sh")
        sys.exit(1)

    agent = Agent()

    if "--once" in sys.argv:
        agent.run_once()
    else:
        agent.run_forever()


if __name__ == "__main__":
    main()
