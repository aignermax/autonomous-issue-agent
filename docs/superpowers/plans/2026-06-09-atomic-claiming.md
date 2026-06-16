# Atomic Issue Claiming Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make concurrent issue claiming safe by adding a claim-comment marker plus an earliest-comment-id tiebreak, so two agents (same or different GitHub user) cannot both process one issue.

**Architecture:** Each agent has a unique per-process `agent_id`. On claim it removes the label, assigns the issue, and posts a parseable marker comment. `GitHubClient.claim_winner` returns the agent id of the earliest claim comment (lowest server comment id). `process_issue` verifies it won before creating a worktree; the loser backs off. A `None` winner (marker mechanism unavailable) is treated as won (degrades to current behavior).

**Tech Stack:** Python, pytest, `unittest.mock`, PyGithub.

**Spec:** `docs/superpowers/specs/2026-06-09-atomic-claiming-design.md`

## Test-runner notes

- `tests/test_github_client.py` imports `src.github_client` only (no `termios` chain) → run with native `py -m pytest tests/test_github_client.py`. PyGithub is installed in native python. **Known pre-existing baseline:** this file has 2 FAILING tests (`test_find_next_issue`, `test_find_next_issue_skips_prs`) from broken mocks unrelated to this work — leave them, do not fix, just confirm you add no NEW failures.
- `tests/test_claiming.py` (new) imports `src.agent` (pulls in Unix-only `termios`) → run under **WSL**: `wsl python3 -m pytest tests/test_claiming.py -v`.

---

### Task 1: GitHubClient claim marker — `post_claim` + `claim_winner`

**Files:**
- Modify: `src/github_client.py` (add `import re`; add two methods to `GitHubClient`)
- Test: `tests/test_github_client.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_github_client.py` (it already imports `from src.github_client import GitHubClient`; ensure `from unittest.mock import MagicMock` is imported at the top — add it if missing):

```python
class TestClaimMarker:
    def _client(self):
        # Bypass __init__ (which needs a token + network); these methods
        # operate on the passed-in issue, not on client state.
        return GitHubClient.__new__(GitHubClient)

    def test_post_claim_posts_marker_comment(self):
        client = self._client()
        issue = MagicMock()
        client.post_claim(issue, "host:abcd1234")
        issue.create_comment.assert_called_once()
        body = issue.create_comment.call_args[0][0]
        assert "<!-- AIA-CLAIM:host:abcd1234 -->" in body

    def test_claim_winner_returns_lowest_id_marker(self):
        client = self._client()
        issue = MagicMock()
        issue.get_comments.return_value = [
            MagicMock(id=200, body="just a normal comment"),
            MagicMock(id=150, body="hi\n<!-- AIA-CLAIM:host:aaaaaaaa -->"),
            MagicMock(id=140, body="<!-- AIA-CLAIM:host:bbbbbbbb -->\nworking"),
        ]
        assert client.claim_winner(issue) == "host:bbbbbbbb"

    def test_claim_winner_none_when_no_markers(self):
        client = self._client()
        issue = MagicMock()
        issue.get_comments.return_value = [
            MagicMock(id=1, body="nothing here"),
            MagicMock(id=2, body="still nothing"),
        ]
        assert client.claim_winner(issue) is None

    def test_claim_winner_ignores_non_marker_comments(self):
        client = self._client()
        issue = MagicMock()
        issue.get_comments.return_value = [
            MagicMock(id=5, body="<!-- AIA-CLAIM:host:only -->"),
            MagicMock(id=3, body="unrelated lower-id comment"),
        ]
        assert client.claim_winner(issue) == "host:only"

    def test_claim_winner_none_on_github_error(self):
        client = self._client()
        issue = MagicMock()
        issue.get_comments.side_effect = Exception("api down")
        assert client.claim_winner(issue) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/test_github_client.py::TestClaimMarker -v`
Expected: FAIL with `AttributeError: ... 'post_claim'` (and the 2 pre-existing failures elsewhere in the file are unrelated).

- [ ] **Step 3: Write minimal implementation**

In `src/github_client.py`, add `import re` to the imports at the top (after `import logging`). Then add these two methods to the `GitHubClient` class (e.g. after `add_issue_comment`):

```python
    _CLAIM_MARKER = re.compile(r"<!--\s*AIA-CLAIM:(.+?)\s*-->")

    def post_claim(self, issue, agent_id: str) -> None:
        """Post a machine-parseable claim marker comment for race resolution.

        Args:
            issue: GitHub Issue object.
            agent_id: Unique per-process identity of the claiming agent.
        """
        issue.create_comment(
            f"🤖 Agent claim — `{agent_id}`\n\n<!-- AIA-CLAIM:{agent_id} -->"
        )

    def claim_winner(self, issue) -> Optional[str]:
        """Return the agent id that won the claim race for this issue.

        The winner is the agent whose claim marker comment has the lowest
        server-assigned comment id (earliest creation). Returns None if no
        claim markers exist or the comments cannot be read.

        Args:
            issue: GitHub Issue object.

        Returns:
            Winning agent id, or None.
        """
        try:
            comments = list(issue.get_comments())
        except Exception as e:
            log.warning(f"Could not read comments for issue #{issue.number}: {e}")
            return None

        winner_id = None
        winner_comment_id = None
        for comment in comments:
            match = self._CLAIM_MARKER.search(comment.body or "")
            if not match:
                continue
            if winner_comment_id is None or comment.id < winner_comment_id:
                winner_comment_id = comment.id
                winner_id = match.group(1)
        return winner_id
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests/test_github_client.py::TestClaimMarker -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/github_client.py tests/test_github_client.py
git commit -m "(+) Add GitHub claim marker post + winner resolution"
```

---

### Task 2: Wire atomic claim-verify into the agent

**Files:**
- Modify: `src/agent.py` (add `import socket`, `import uuid`; add `agent_id` in `__init__`; replace the claim body in `_claim_issue_and_create_branch`; add `_claim_won`; add the verify branch in `process_issue`)
- Test: `tests/test_claiming.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_claiming.py`:

```python
"""Tests for Agent._claim_won (atomic claim verification)."""

from unittest.mock import MagicMock


def _make_agent(agent_id="host:me123456"):
    from src.agent import Agent
    agent = Agent.__new__(Agent)
    agent.agent_id = agent_id
    agent.github = MagicMock()
    return agent


class TestClaimWon:
    def test_won_when_winner_is_self(self):
        agent = _make_agent("host:me123456")
        agent.github.claim_winner.return_value = "host:me123456"
        issue = MagicMock(number=1)
        assert agent._claim_won(issue) is True

    def test_won_when_winner_is_none_failsafe(self):
        agent = _make_agent()
        agent.github.claim_winner.return_value = None
        issue = MagicMock(number=1)
        assert agent._claim_won(issue) is True

    def test_lost_when_winner_is_other(self):
        agent = _make_agent("host:me123456")
        agent.github.claim_winner.return_value = "other:zzzz9999"
        issue = MagicMock(number=1)
        assert agent._claim_won(issue) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `wsl python3 -m pytest tests/test_claiming.py -v`
Expected: FAIL with `AttributeError: ... '_claim_won'`.

- [ ] **Step 3a: Add imports + agent_id**

In `src/agent.py`, add `import socket` and `import uuid` to the stdlib imports near the top (after `import re`). Then in `__init__`, immediately after the line `self._last_repo_index = -1`, add:

```python
        # Unique per-process identity used to win/lose issue claim races.
        self.agent_id = f"{socket.gethostname()}:{uuid.uuid4().hex[:8]}"
```

- [ ] **Step 3b: Replace the claim body to post the marker + drop dead code**

In `_claim_issue_and_create_branch`, replace this exact block:

```python
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
```

with:

```python
        # LOCK the issue: remove the activation label, assign for a human-visible
        # lock, and post a claim marker (the authoritative race tiebreak).
        try:
            log.info(f"Claiming issue #{issue_num} by removing '{self.config.issue_label}' label")
            issue.remove_from_labels(self.config.issue_label)
            log.info(f"Issue #{issue_num} locked (label removed)")

            # Assign to the repo owner as a persistent, human-visible lock.
            # Idempotent across agents; the claim marker resolves who actually won.
            try:
                issue.add_to_assignees(self.github.repo.owner.login)
                log.info(f"Assigned issue #{issue_num} to {self.github.repo.owner.login}")
            except Exception as assign_error:
                log.warning(f"Could not assign issue #{issue_num}: {assign_error}")

            self.github.post_claim(issue, self.agent_id)
            log.info(f"Posted claim for issue #{issue_num} as {self.agent_id}")
        except Exception as e:
            log.warning(f"Could not claim issue #{issue_num}: {e}")
            log.warning("Continuing anyway, but other agents might pick this up too")
```

- [ ] **Step 3c: Add the `_claim_won` helper**

Add this method to the `Agent` class, immediately before `_claim_issue_and_create_branch`:

```python
    def _claim_won(self, issue) -> bool:
        """Return True if this agent won the claim race for the issue.

        Winner is the earliest claim marker (lowest server comment id). A None
        winner (marker mechanism unavailable) is treated as won, because a
        permanently unprocessed issue is worse than a rare duplicate.
        """
        winner = self.github.claim_winner(issue)
        if winner is None or winner == self.agent_id:
            return True
        log.info(f"Lost claim race for issue #{issue.number} to {winner}; backing off")
        return False
```

- [ ] **Step 3d: Add the verify branch in `process_issue`**

In `process_issue`, replace this exact block:

```python
        existing_state = self.session_manager.load_state(issue_num)
        if existing_state:
            branch = existing_state.branch_name
        else:
            branch = self._claim_issue_and_create_branch(issue)
```

with:

```python
        existing_state = self.session_manager.load_state(issue_num)
        if existing_state:
            branch = existing_state.branch_name
        else:
            branch = self._claim_issue_and_create_branch(issue)
            # Atomic-claim verify: only the winner of the claim race proceeds.
            if not self._claim_won(issue):
                return IssueResult(
                    success=False,
                    branch=branch,
                    error="Lost claim race to another agent",
                )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `wsl python3 -m pytest tests/test_claiming.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Run the full suite under WSL (regression check)**

Run: `wsl python3 -m pytest tests/ -q`
Expected: only the 2 pre-existing `test_github_client.py` failures, plus no new failures. (Net: the new claim-marker and claiming tests pass.)

- [ ] **Step 6: Commit**

```bash
git add src/agent.py tests/test_claiming.py
git commit -m "(+) Wire atomic claim-verify into issue processing"
```

---

## Self-Review Notes

- **Spec coverage:** `post_claim` + `claim_winner` (Task 1), `agent_id` field + `_claim_won` verify + `post_claim` wiring + `process_issue` back-off branch + dead-code removal (Task 2). Fail-safe `None`→won covered in both `_claim_won` test and `claim_winner` None paths. Loser-backs-off-before-worktree covered by the early `return` placed before `worktrees.create`.
- **Type/name consistency:** `post_claim(issue, agent_id)`, `claim_winner(issue) -> Optional[str]`, `Agent.agent_id`, `Agent._claim_won(issue) -> bool` are used identically across tasks. `Optional` is already imported in `github_client.py`.
- **Placeholder scan:** none.
- **Out of scope (unchanged):** the 2 pre-existing `test_github_client.py` mock failures are intentionally not touched.
