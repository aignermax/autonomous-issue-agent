"""
QA agent: verifies PRs created by the coder agent.

Polls each configured repository for open PRs that look like coder output
(title prefix `Agent:` by default), checks them out into an isolated
workspace, runs the project's build / test / ui-test commands as declared
in the per-repo `.agent.toml`, and posts a verdict comment plus a
qa-passed / qa-failed label.

This agent is intentionally mechanical — it does NOT call Claude Code and
does NOT modify the PR. Failures stay for the coder agent (or a human) to
fix.
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..config import Config
from ..git_repo import GitRepo
from ..github_client import GitHubClient
from .agent_config import ProjectConfig, load_project_config

log = logging.getLogger("agent")


PR_TITLE_PREFIX = "Agent:"
LABEL_PASSED = "qa-passed"
LABEL_FAILED = "qa-failed"
LABEL_RUNNING = "qa-running"


@dataclass
class StepResult:
    """Outcome of one shell step (build / test / ui-test)."""

    name: str
    ran: bool
    exit_code: int = 0
    stdout_tail: str = ""
    stderr_tail: str = ""

    @property
    def passed(self) -> bool:
        return self.ran and self.exit_code == 0


@dataclass
class QAResult:
    """Aggregated verdict for a single PR."""

    pr_number: int
    branch: str
    steps: list[StepResult]
    overall_passed: bool
    error: str = ""


class QAAgent:
    """Polling QA worker. Mirrors the structure of the coder Agent class."""

    def __init__(self, config: Config):
        self.config = config
        self.github: Optional[GitHubClient] = None
        self.git: Optional[GitRepo] = None
        self.current_repo_name: Optional[str] = None
        self._last_repo_index = -1

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _setup_for_repo(self, repo_name: str) -> None:
        """Wire GitHub + Git for one repository, using a QA-specific clone path."""
        self.current_repo_name = repo_name
        self.github = GitHubClient(repo_name)

        token = os.environ["GITHUB_TOKEN"]
        remote = f"https://{token}@github.com/{repo_name}.git"

        # Separate clone from the coder so the two never fight over the
        # working tree.
        repo_slug = repo_name.replace("/", "_")
        local_path = self.config.local_path.parent / f"repo_qa_{repo_slug}"
        self.git = GitRepo(local_path, remote, self.github.default_branch)

        log.info(f"[qa] setup complete for {repo_name} → {local_path}")

    # ------------------------------------------------------------------
    # PR discovery
    # ------------------------------------------------------------------

    def _find_next_pr(self):
        """Find the oldest open coder-style PR that has not yet been verified."""
        assert self.github is not None
        for pr in self.github.repo.get_pulls(state="open", sort="created", direction="asc"):
            if not pr.title.startswith(PR_TITLE_PREFIX):
                continue

            label_names = {label.name.lower() for label in pr.labels}
            if LABEL_PASSED in label_names or LABEL_FAILED in label_names:
                continue
            if LABEL_RUNNING in label_names:
                # Another QA worker is already on it.
                continue

            return pr
        return None

    # ------------------------------------------------------------------
    # PR verification
    # ------------------------------------------------------------------

    def verify_pr(self, pr) -> QAResult:
        """Check out a PR's branch and run the configured QA commands."""
        assert self.git is not None and self.github is not None
        branch = pr.head.ref
        log.info(f"[qa] verifying PR #{pr.number} on branch {branch}")

        self._claim_pr(pr)

        try:
            self._checkout_pr_branch(branch)
        except Exception as e:
            log.exception(f"[qa] could not check out branch {branch}")
            return QAResult(
                pr_number=pr.number,
                branch=branch,
                steps=[],
                overall_passed=False,
                error=f"checkout failed: {e}",
            )

        project_cfg = load_project_config(self.git.path)
        if not project_cfg.is_agent_enabled("qa"):
            log.info(f"[qa] disabled for {self.current_repo_name} via .agent.toml — skipping")
            self._release_pr(pr, verdict_label=None)
            return QAResult(
                pr_number=pr.number,
                branch=branch,
                steps=[],
                overall_passed=True,
                error="qa disabled for repo",
            )

        steps = self._run_steps(project_cfg)
        overall_passed = all(s.passed or not s.ran for s in steps) and any(s.ran for s in steps)

        verdict_label = LABEL_PASSED if overall_passed else LABEL_FAILED
        self._post_verdict(pr, steps, overall_passed)
        self._release_pr(pr, verdict_label=verdict_label)

        return QAResult(
            pr_number=pr.number,
            branch=branch,
            steps=steps,
            overall_passed=overall_passed,
        )

    def _claim_pr(self, pr) -> None:
        """Mark the PR as in-flight so concurrent QA workers skip it."""
        try:
            pr.add_to_labels(LABEL_RUNNING)
        except Exception as e:
            log.warning(f"[qa] could not add running label to PR #{pr.number}: {e}")

    def _release_pr(self, pr, verdict_label: Optional[str]) -> None:
        try:
            pr.remove_from_labels(LABEL_RUNNING)
        except Exception:
            pass
        if verdict_label:
            try:
                pr.add_to_labels(verdict_label)
            except Exception as e:
                log.warning(f"[qa] could not add verdict label to PR #{pr.number}: {e}")

    def _checkout_pr_branch(self, branch: str) -> None:
        """Clone if needed, fetch the PR branch, check it out clean."""
        assert self.git is not None
        self.git.ensure_cloned()

        # Always fetch the latest state of the PR branch from origin.
        fetch = self.git.run("fetch", "origin", branch)
        if fetch.returncode != 0:
            raise RuntimeError(f"fetch failed: {fetch.stderr.strip()}")

        if self.git.branch_exists(branch):
            self.git.run("checkout", branch)
            # Discard any local cruft and align with origin.
            self.git.run("reset", "--hard", f"origin/{branch}")
        else:
            self.git.run("checkout", "-b", branch, f"origin/{branch}")

        self.git.run("clean", "-fdx")

    # ------------------------------------------------------------------
    # Command execution
    # ------------------------------------------------------------------

    def _run_steps(self, cfg: ProjectConfig) -> list[StepResult]:
        steps: list[StepResult] = []
        if cfg.has_build:
            steps.append(self._run_step("build", cfg.build_cmd, cfg.command_timeout_sec))
        else:
            steps.append(StepResult(name="build", ran=False))

        # Stop early on build failure — running tests on a broken build is noise.
        if steps[-1].ran and not steps[-1].passed:
            steps.append(StepResult(name="test", ran=False))
            steps.append(StepResult(name="ui_test", ran=False))
            return steps

        if cfg.has_tests:
            steps.append(self._run_step("test", cfg.test_cmd, cfg.command_timeout_sec))
        else:
            steps.append(StepResult(name="test", ran=False))

        if cfg.has_ui_tests:
            steps.append(self._run_step("ui_test", cfg.ui_test_cmd, cfg.command_timeout_sec))
        else:
            steps.append(StepResult(name="ui_test", ran=False))

        return steps

    def _run_step(self, name: str, cmd: str, timeout_sec: int) -> StepResult:
        assert self.git is not None
        log.info(f"[qa] step '{name}': {cmd}")
        try:
            proc = subprocess.run(
                cmd,
                cwd=self.git.path,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
            )
        except subprocess.TimeoutExpired as e:
            log.error(f"[qa] step '{name}' timed out after {timeout_sec}s")
            return StepResult(
                name=name,
                ran=True,
                exit_code=-1,
                stdout_tail=_tail(getattr(e, "stdout", b"") or b""),
                stderr_tail=f"timeout after {timeout_sec}s",
            )

        return StepResult(
            name=name,
            ran=True,
            exit_code=proc.returncode,
            stdout_tail=_tail(proc.stdout),
            stderr_tail=_tail(proc.stderr),
        )

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def _post_verdict(self, pr, steps: list[StepResult], passed: bool) -> None:
        header = "[qa-agent] **PASSED**" if passed else "[qa-agent] **FAILED**"
        lines = [header, ""]
        for step in steps:
            if not step.ran:
                lines.append(f"- `{step.name}`: skipped (no command configured)")
                continue
            status = "ok" if step.passed else f"failed (exit {step.exit_code})"
            lines.append(f"- `{step.name}`: {status}")
            if not step.passed:
                tail = step.stderr_tail or step.stdout_tail
                if tail:
                    lines.append("")
                    lines.append("```")
                    lines.append(tail)
                    lines.append("```")

        try:
            pr.create_issue_comment("\n".join(lines))
        except Exception as e:
            log.warning(f"[qa] could not post verdict comment on PR #{pr.number}: {e}")

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    def run_once(self) -> None:
        """Round-robin one repository per cycle, mirroring the coder."""
        num_repos = len(self.config.repo_names)
        if num_repos == 0:
            log.warning("[qa] no repositories configured — nothing to do")
            return

        self._last_repo_index = (self._last_repo_index + 1) % num_repos
        repo_name = self.config.repo_names[self._last_repo_index]

        log.info(f"[qa] checking repository: {repo_name}")
        self._setup_for_repo(repo_name)

        pr = self._find_next_pr()
        if not pr:
            log.info(f"[qa] no PRs awaiting verification in {repo_name}")
            return

        log.info(f"[qa] found PR #{pr.number} in {repo_name}: {pr.title}")
        result = self.verify_pr(pr)
        if result.overall_passed:
            log.info(f"[qa] PR #{result.pr_number} PASSED")
        else:
            log.error(f"[qa] PR #{result.pr_number} FAILED: {result.error or 'see comment'}")

    def run_forever(self) -> None:
        log.info(
            f"[qa] agent started. Polling every {self.config.poll_interval}s. "
            f"Repositories: {', '.join(self.config.repo_names)}"
        )
        while True:
            try:
                self.run_once()
            except Exception:
                log.exception("[qa] unexpected error in poll loop")
            log.info(f"[qa] sleeping {self.config.poll_interval}s ...")
            time.sleep(self.config.poll_interval)


def _tail(text: str | bytes, max_chars: int = 2000) -> str:
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="replace")
    if len(text) <= max_chars:
        return text
    return "...\n" + text[-max_chars:]
