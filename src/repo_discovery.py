"""
Org-wide repo auto-discovery via the agent-task label.

Workshop users label issues `agent-task` in arbitrary org repos. Instead of
maintaining AGENT_REPOS by hand (or scanning ~200 repos one by one), the
coder runs ONE GitHub search per interval:

    org:<org> label:<label> is:issue is:open

Repos that show up are added to a persistent registry
(.sessions/discovered-repos.json) with a last-seen timestamp; repos whose
label activity is older than the expiry (default 8 days) drop out again.
All three agent roles read the effective repo list from this registry —
only the coder writes it.

Manual repos from AGENT_REPOS are never expired; non-org repos can only be
added manually.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Set

log = logging.getLogger("agent")

REGISTRY_FILENAME = "discovered-repos.json"
_TS_FORMAT = "%Y-%m-%d %H:%M:%S"


class RepoRegistry:
    """Persistent {repo_full_name: {first_seen, last_seen}} store."""

    def __init__(self, session_dir: Path):
        self.path = session_dir / REGISTRY_FILENAME
        self._data: dict = {}
        try:
            if self.path.exists():
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning(f"[discovery] registry unreadable ({e}); starting fresh")
            self._data = {}

    def update(self, found_repos: Set[str], now: datetime = None) -> List[str]:
        """Refresh last-seen for found repos; returns newly added ones."""
        now_s = (now or datetime.now()).strftime(_TS_FORMAT)
        added = []
        for repo in sorted(found_repos):
            entry = self._data.get(repo)
            if entry is None:
                self._data[repo] = {"first_seen": now_s, "last_seen": now_s}
                added.append(repo)
            else:
                entry["last_seen"] = now_s
        self._save()
        return added

    def remove(self, repo: str) -> None:
        if repo in self._data:
            del self._data[repo]
            self._save()

    def active_repos(self, expiry_days: int, now: datetime = None) -> List[str]:
        """Repos whose label activity is within the expiry window.

        Expired entries are pruned from the store as a side effect.
        """
        now = now or datetime.now()
        cutoff = now - timedelta(days=expiry_days)
        active, expired = [], []
        for repo, entry in self._data.items():
            try:
                last_seen = datetime.strptime(entry["last_seen"], _TS_FORMAT)
            except (KeyError, ValueError):
                expired.append(repo)
                continue
            (active if last_seen >= cutoff else expired).append(repo)
        if expired:
            for repo in expired:
                log.info(f"[discovery] expiring {repo} (no agent-task activity within window)")
                del self._data[repo]
            self._save()
        return sorted(active)

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
        except Exception as e:
            log.warning(f"[discovery] could not persist registry: {e}")


def _search_repo_set(gh, query: str) -> Set[str]:
    """Collect the repo full names behind one issue-search query."""
    repos: Set[str] = set()
    # PyGithub paginates lazily; iterating pulls further pages only when
    # more than 100 hits exist.
    for issue in gh.search_issues(query):
        repos.add(issue.repository.full_name)
    return repos


def search_repos_with_label(gh, org: str, label: str) -> Set[str]:
    """One search-API call: org repos having open issues with `label`."""
    return _search_repo_set(gh, f'org:{org} label:"{label}" is:issue is:open')


def search_repos_with_agent_prs(gh, org: str) -> Set[str]:
    """Org repos with open agent PRs (title prefix) — counts as 'usage'.

    Keeps a repo alive in the registry while QA / @agent follow-ups on its
    PRs are still possible, even after all labeled issues are closed.
    """
    return _search_repo_set(gh, f'org:{org} is:pr is:open in:title "Agent:"')


def search_repos_with_qa_failed(gh, org: str) -> Set[str]:
    """Org repos with open qa-failed PRs (the coder's fix queue)."""
    return _search_repo_set(gh, f'org:{org} is:pr is:open label:qa-failed')


def search_manual_repos_with_label(gh, repos: List[str], label: str) -> Set[str]:
    """Same as the org sweep but for the manual (non-org) repo list."""
    if not repos:
        return set()
    scope = " ".join(f"repo:{r}" for r in repos)
    return _search_repo_set(gh, f'{scope} label:"{label}" is:issue is:open')


HINTS_FILENAME = "work-hints.json"


def save_work_hints(session_dir: Path, issue_repos: Set[str],
                    qa_failed_repos: Set[str]) -> None:
    """Persist which repos currently have work (written by the coder sweep)."""
    try:
        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / HINTS_FILENAME).write_text(json.dumps({
            "issues": sorted(issue_repos),
            "qa_failed": sorted(qa_failed_repos),
            "ts": datetime.now().strftime(_TS_FORMAT),
        }, indent=2), encoding="utf-8")
    except Exception as e:
        log.warning(f"[discovery] could not persist work hints: {e}")


def load_work_hints(session_dir: Path, max_age_sec: int) -> Set[str]:
    """Repos with known work, or empty set when hints are missing/stale.

    An empty result makes callers fall back to plain round-robin, so a
    broken sweep degrades to the old behavior instead of starving repos.
    """
    path = session_dir / HINTS_FILENAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        ts = datetime.strptime(data["ts"], _TS_FORMAT)
        if (datetime.now() - ts).total_seconds() > max_age_sec:
            return set()
        return set(data.get("issues", [])) | set(data.get("qa_failed", []))
    except Exception:
        return set()


def effective_repo_names(config) -> List[str]:
    """Manual AGENT_REPOS plus active auto-discovered org repos (deduped).

    Read-only view — safe for every role in every process.
    """
    manual = list(config.repo_names)
    if not config.discovery_org:
        return manual
    registry = RepoRegistry(config.session_dir)
    seen = {r.lower() for r in manual}
    for repo in registry.active_repos(config.discovery_expiry_days):
        if repo.lower() not in seen:
            manual.append(repo)
            seen.add(repo.lower())
    return manual
