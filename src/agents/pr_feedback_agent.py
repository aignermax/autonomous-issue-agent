"""
PR-feedback agent: turns human PR comments into fixes + fresh screenshots.

Polls ALL open PRs for comments containing a trigger marker (default
`@agent`) — the marker is the opt-in, so human-authored PRs work too. For
each trigger it checks out the PR branch, runs a Claude Code worker with
the feedback, pushes the result, re-publishes the visual walkthrough and
replies to the comment with a mini report + updated screenshots.

Guardrails — all marker-based, because agent comments are posted with the
same GitHub token as the human's (author filtering can't tell them apart):
- Only comments containing the trigger marker fire.
- Agent replies embed REPLY_MARKER (an HTML comment, invisible on GitHub)
  and are never treated as triggers.
- Processed comment ids are persisted so a comment fires at most once;
  failures are retried once, then surfaced as a reply instead of looping.
- Per-PR round cap (config.pr_feedback_max_rounds) with a one-time notice.

Per-repo opt-in via `.agent.toml`: `agents_enabled` must contain
"pr-feedback".
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Callable, List, Optional

from ..config import Config
from ..git_repo import GitRepo
from ..github_client import GitHubClient
from ..pr_media import publish_walkthrough
from .agent_config import ProjectConfig, load_project_config_from_text

log = logging.getLogger("agent")

REPLY_MARKER = "<!-- pr-feedback-agent -->"
STATE_FILENAME = "pr-feedback-state.json"
MAX_ATTEMPTS_PER_COMMENT = 2
REPORT_RE = re.compile(
    r"===\s*FEEDBACK REPORT\s*===\s*(.*?)\s*===\s*END\s*===", re.DOTALL
)


# ---------------------------------------------------------------------------
# Pure helpers (unit-tested without GitHub)
# ---------------------------------------------------------------------------

def extract_issue_number(pr_body: str, fallback: int) -> int:
    """Issue number from the PR body's `... for #<n>` link; else fallback."""
    m = re.search(r"#(\d+)", pr_body or "")
    return int(m.group(1)) if m else fallback


def extract_feedback_report(output: str, max_fallback_chars: int = 800) -> str:
    """Pull the `=== FEEDBACK REPORT ===` block out of worker output.

    Falls back to the output tail so the reply is never empty.
    """
    if not output:
        return "(worker produced no output)"
    m = REPORT_RE.search(output)
    if m and m.group(1).strip():
        return m.group(1).strip()
    tail = output.strip()
    if len(tail) > max_fallback_chars:
        tail = "...\n" + tail[-max_fallback_chars:]
    return tail


def is_trigger_comment(body: str, marker: str) -> bool:
    """A trigger mentions the marker and is not one of our own replies."""
    if not body:
        return False
    return marker in body and REPLY_MARKER not in body


def find_trigger_comments(comments, marker: str, processed_ids) -> List:
    """Unprocessed trigger comments, oldest first (feedback handled in order)."""
    processed = set(processed_ids)
    hits = [
        c for c in comments
        if is_trigger_comment(getattr(c, "body", ""), marker)
        and c.id not in processed
    ]
    hits.sort(key=lambda c: c.created_at)
    return hits


# ---------------------------------------------------------------------------
# Persistent per-comment state
# ---------------------------------------------------------------------------

class FeedbackState:
    """Tiny JSON store: which comment ids were handled, per repo#pr."""

    def __init__(self, path: Path):
        self.path = path
        self._data = {}
        try:
            if path.exists():
                self._data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning(f"[pr-feedback] state file unreadable ({e}); starting fresh")
            self._data = {}

    def _entry(self, key: str) -> dict:
        return self._data.setdefault(
            key, {"processed": [], "attempts": {}, "cap_notified": False})

    def last_seen_update(self, key: str) -> str:
        return str(self._entry(key).get("last_update", ""))

    def set_last_seen_update(self, key: str, updated_at: str) -> None:
        self._entry(key)["last_update"] = updated_at
        self._save()

    def processed_ids(self, key: str) -> List[int]:
        return list(self._entry(key)["processed"])

    def rounds(self, key: str) -> int:
        return len(self._entry(key)["processed"])

    def mark_processed(self, key: str, comment_id: int) -> None:
        entry = self._entry(key)
        if comment_id not in entry["processed"]:
            entry["processed"].append(comment_id)
        entry["attempts"].pop(str(comment_id), None)
        self._save()

    def bump_attempts(self, key: str, comment_id: int) -> int:
        entry = self._entry(key)
        n = entry["attempts"].get(str(comment_id), 0) + 1
        entry["attempts"][str(comment_id)] = n
        self._save()
        return n

    def cap_notified(self, key: str) -> bool:
        return bool(self._entry(key)["cap_notified"])

    def set_cap_notified(self, key: str) -> None:
        self._entry(key)["cap_notified"] = True
        self._save()

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(self._data, indent=2), encoding="utf-8")
        except Exception as e:
            log.warning(f"[pr-feedback] could not persist state: {e}")


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class PRFeedbackAgent:
    """Polling watcher. Mirrors the QAAgent structure (own clone per repo)."""

    def __init__(self, config: Config,
                 claude_factory: Optional[Callable] = None):
        self.config = config
        if claude_factory is None:
            from ..claude_code import ClaudeCode
            claude_factory = ClaudeCode
        self.claude_factory = claude_factory
        self.github: Optional[GitHubClient] = None
        self.git: Optional[GitRepo] = None
        self.current_repo_name: Optional[str] = None
        self._last_repo_index = -1
        self.state = FeedbackState(self.config.session_dir / STATE_FILENAME)

    # -- setup ----------------------------------------------------------

    def _setup_for_repo(self, repo_name: str) -> None:
        self.current_repo_name = repo_name
        self.github = GitHubClient(repo_name)
        token = os.environ["GITHUB_TOKEN"]
        remote = f"https://{token}@github.com/{repo_name}.git"
        repo_slug = repo_name.replace("/", "_")
        # Own clone — never fight the coder or QA over a working tree.
        local_path = self.config.local_path.parent / f"repo_fb_{repo_slug}"
        self.git = GitRepo(local_path, remote, self.github.default_branch)
        log.info(f"[pr-feedback] setup complete for {repo_name} → {local_path}")

    # -- polling --------------------------------------------------------

    def run_once(self) -> None:
        num_repos = len(self.config.repo_names)
        if num_repos == 0:
            log.warning("[pr-feedback] no repositories configured")
            return
        self._last_repo_index = (self._last_repo_index + 1) % num_repos
        repo_name = self.config.repo_names[self._last_repo_index]
        log.info(f"[pr-feedback] checking repository: {repo_name}")
        self._setup_for_repo(repo_name)

        assert self.github is not None
        marker = self.config.pr_feedback_marker
        for pr in self.github.repo.get_pulls(
                state="open", sort="created", direction="asc"):
            # Any open PR is eligible — the marker itself is the opt-in
            # (comments post under the human's token, so a marker comment is
            # always an explicit human request, agent replies carry
            # REPLY_MARKER and are filtered). No Agent:-title requirement.
            key = f"{repo_name}#{pr.number}"

            # API budget: only list comments when the PR changed since our
            # last look. A new comment bumps updated_at, so nothing is missed;
            # with dozens of open PRs per repo this collapses steady-state
            # polling from N comment-listings per cycle to ~zero.
            updated_at = (pr.updated_at.isoformat()
                          if getattr(pr, "updated_at", None) else "")
            if updated_at and updated_at == self.state.last_seen_update(key):
                continue

            try:
                comments = list(pr.get_issue_comments())
            except Exception as e:
                log.warning(f"[pr-feedback] could not list comments on PR #{pr.number}: {e}")
                continue
            triggers = find_trigger_comments(
                comments, marker, self.state.processed_ids(key))
            if not triggers:
                self.state.set_last_seen_update(key, updated_at)
                continue

            if self.state.rounds(key) >= self.config.pr_feedback_max_rounds:
                self._notify_cap(pr, key)
                continue

            # One comment per cycle keeps rounds observable and interruptible.
            self._handle_feedback(pr, key, triggers[0])
            return

        log.info(f"[pr-feedback] nothing to do in {repo_name}")

    def run_forever(self) -> None:
        log.info(
            f"[pr-feedback] agent started. Marker: '{self.config.pr_feedback_marker}'. "
            f"Polling every {self.config.poll_interval}s. "
            f"Repositories: {', '.join(self.config.repo_names)}"
        )
        while True:
            try:
                self.run_once()
            except Exception:
                log.exception("[pr-feedback] unexpected error in poll loop")
            log.info(f"[pr-feedback] sleeping {self.config.poll_interval}s ...")
            time.sleep(self.config.poll_interval)

    # -- feedback handling ------------------------------------------------

    def _handle_feedback(self, pr, key: str, comment) -> None:
        branch = pr.head.ref
        log.info(
            f"[pr-feedback] PR #{pr.number}: handling comment {comment.id} "
            f"(round {self.state.rounds(key) + 1}/{self.config.pr_feedback_max_rounds})"
        )
        try:
            # Fork PRs: the head branch lives in another repo — we can neither
            # fetch it from origin nor push back. Decline explicitly instead
            # of failing twice with a cryptic fetch error.
            head_repo = getattr(getattr(pr, "head", None), "repo", None)
            head_full_name = getattr(head_repo, "full_name", None)
            if head_full_name and head_full_name != self.current_repo_name:
                log.info(f"[pr-feedback] PR #{pr.number} is from fork {head_full_name} — declining")
                self._safe_comment(
                    pr,
                    f"{REPLY_MARKER}\n[pr-feedback] This PR's branch lives in a "
                    f"fork (`{head_full_name}`), which I can't push to — please "
                    "apply the request manually or move the branch into this repo.",
                )
                self.state.mark_processed(key, comment.id)
                return

            # Role opt-in is repo POLICY: read .agent.toml from the DEFAULT
            # branch, never from the PR branch — old branches predate the
            # opt-in and would silently disable the role (this once swallowed
            # 19 walkthrough requests without any reply).
            project_cfg = self._load_repo_policy()
            if not project_cfg.is_agent_enabled("pr-feedback"):
                log.info(
                    f"[pr-feedback] disabled for {self.current_repo_name} via "
                    ".agent.toml — declining with reply")
                self._safe_comment(
                    pr,
                    f"{REPLY_MARKER}\n[pr-feedback] The pr-feedback role is not "
                    "enabled for this repository (`agents_enabled` in "
                    "`.agent.toml` on the default branch).",
                )
                self.state.mark_processed(key, comment.id)
                return

            self._checkout_pr_branch(branch)

            issue_number = extract_issue_number(pr.body or "", pr.number)
            prompt = self._build_prompt(pr, branch, comment, issue_number)

            worker = self.claude_factory(
                working_dir=self.git.path,
                max_turns=self.config.pr_feedback_max_turns,
                model=self.config.coder_model,
            )
            output, reached_max, _usage = worker.execute(prompt)
            if reached_max:
                log.warning(f"[pr-feedback] worker hit max turns on PR #{pr.number}")

            pushed = self.git.commit_and_push(
                branch=branch,
                message=f"PR feedback: address comment on #{pr.number}",
                base_branch=self.github.default_branch,
            )

            walkthrough = publish_walkthrough(
                self.git, self.current_repo_name, branch, issue_number)
            if walkthrough:
                # Keep the PR body's walkthrough current too, not just the reply.
                from ..pr_media import merge_walkthrough_into_body
                try:
                    pr.edit(body=merge_walkthrough_into_body(pr.body, walkthrough))
                except Exception as e:
                    log.warning(f"[pr-feedback] could not refresh PR body: {e}")

            self._reply(pr, comment, extract_feedback_report(output),
                        walkthrough, pushed)
            self.state.mark_processed(key, comment.id)
        except Exception as e:
            attempts = self.state.bump_attempts(key, comment.id)
            log.exception(
                f"[pr-feedback] failed on PR #{pr.number} comment {comment.id} "
                f"(attempt {attempts}/{MAX_ATTEMPTS_PER_COMMENT})")
            if attempts >= MAX_ATTEMPTS_PER_COMMENT:
                self.state.mark_processed(key, comment.id)
                self._safe_comment(
                    pr,
                    f"{REPLY_MARKER}\n[pr-feedback] I couldn't complete this "
                    f"request after {attempts} attempts (last error: `{e}`). "
                    "Leaving it for a human.",
                )

    def _build_prompt(self, pr, branch: str, comment, issue_number: int) -> str:
        from ..prompt_template import build_pr_feedback_prompt
        tools_dir = str(self.config.tools_dir) if self.config.tools_dir else "tools"
        tools_python = (
            str(self.config.tools_python) if self.config.tools_python else "python3")
        return build_pr_feedback_prompt(
            pr, branch=branch, comment_body=comment.body,
            issue_number=issue_number,
            tools_dir=tools_dir, tools_python=tools_python,
        )

    def _load_repo_policy(self) -> ProjectConfig:
        """Read .agent.toml from origin's DEFAULT branch (current repo policy)."""
        assert self.git is not None and self.github is not None
        self.git.ensure_cloned()
        default = self.github.default_branch
        self.git.run("fetch", "origin", f"+{default}:refs/remotes/origin/{default}")
        show = self.git.run("show", f"origin/{default}:.agent.toml")
        if show.returncode != 0:
            # No .agent.toml on the default branch → defaults (role disabled).
            return ProjectConfig()
        return load_project_config_from_text(show.stdout)

    def _checkout_pr_branch(self, branch: str) -> None:
        """Same discipline as the QA agent: explicit refspec, hard reset, clean."""
        assert self.git is not None
        self.git.ensure_cloned()
        fetch = self.git.run(
            "fetch", "origin", f"+{branch}:refs/remotes/origin/{branch}")
        if fetch.returncode != 0:
            raise RuntimeError(f"fetch failed: {fetch.stderr.strip()}")
        if self.git.branch_exists(branch):
            self.git.run("checkout", branch)
            self.git.run("reset", "--hard", f"origin/{branch}")
        else:
            self.git.run("checkout", "-b", branch, f"origin/{branch}")
        self.git.run("clean", "-fdx")

    # -- replies ----------------------------------------------------------

    def _reply(self, pr, comment, report: str, walkthrough: str,
               pushed: bool) -> None:
        parts = [
            REPLY_MARKER,
            f"[pr-feedback] Done — addressed the feedback from comment "
            f"[above](#issuecomment-{comment.id}).",
            "",
            "### What changed",
            report,
        ]
        if not pushed:
            parts.append(
                "\n_Note: no new commits were pushed — the request may have "
                "required no code change (or the change failed to apply)._")
        if walkthrough:
            parts.append(walkthrough)
        else:
            parts.append("\n_No UI screenshots were produced for this round._")
        self._safe_comment(pr, "\n".join(parts))

    def _notify_cap(self, pr, key: str) -> None:
        if self.state.cap_notified(key):
            return
        self._safe_comment(
            pr,
            f"{REPLY_MARKER}\n[pr-feedback] Reached the maximum of "
            f"{self.config.pr_feedback_max_rounds} feedback rounds on this PR. "
            "Further marker comments will be ignored — please handle the rest "
            "manually or merge and open a follow-up issue.",
        )
        self.state.set_cap_notified(key)
        log.info(f"[pr-feedback] round cap reached for {key}")

    def _safe_comment(self, pr, body: str) -> None:
        try:
            pr.create_issue_comment(body)
        except Exception as e:
            log.warning(f"[pr-feedback] could not comment on PR #{pr.number}: {e}")
