# Atomic Issue Claiming — Design Spec

**Date:** 2026-06-09
**Status:** Approved (design), pending implementation plan
**Branch:** `feat/atomic-claiming`

## Problem

When multiple agent instances poll the same repository (different machines, or
the same person on two machines), two agents can claim the same issue. The
current claim is a read-then-write with a TOCTOU window:

1. `find_next_issue` (`github_client.py:44`) returns the oldest open labelled
   issue, skipping PRs and already-assigned issues.
2. `_claim_issue_and_create_branch` (`agent.py:255`) then removes the label,
   assigns the issue to the **repo owner**, and posts a hostname comment.

Two agents that both pass step 1 before either completes step 2 will both
proceed. Crucially, they assign the **same** user (the repo owner), so a
"verify I'm the assignee" check cannot distinguish winner from loser. The
result is duplicate branches, duplicate PRs, and duplicate cost.

GitHub provides no atomic compare-and-swap, so atomic claiming is necessarily
**claim → verify → loser backs off** with a deterministic tiebreak.

## Goal

Make issue claiming safe when N agents poll the same repo concurrently,
regardless of whether they authenticate as the same or different GitHub users.

Non-goals: in-process parallel worker pool (that is the separate
parallelisation step), re-verification before PR creation, deleting a loser's
claim comment.

## Approach (chosen: A — claim-comment + earliest-comment-id tiebreak)

Each agent posts a machine-parseable claim comment carrying a unique agent id.
The winner is the claim comment with the lowest server-assigned comment id
(GitHub assigns monotonically increasing ids in creation order). This works for
both the same-user and different-user cases, needs no external infrastructure.

Rejected:
- **B — assignee-only verify:** breaks when agents share a GitHub user (both
  see the same shared assignee). Fails the "robust for both" requirement.
- **C — external lock** (gist lockfile, Projects field): unnecessary infra.

## Components

### Agent identity

In `Agent.__init__`, generate once per process:

```python
self.agent_id = f"{socket.gethostname()}:{uuid.uuid4().hex[:8]}"
```

Stable for the process lifetime; traceable in logs.

### `GitHubClient.post_claim(issue, agent_id)`

Posts a single comment with human-readable text plus a parseable marker:

```
🤖 Agent claim — `{agent_id}`
<!-- AIA-CLAIM:{agent_id} -->
```

### `GitHubClient.claim_winner(issue) -> Optional[str]`

Iterates `issue.get_comments()`, extracts agent ids from bodies matching
`<!-- AIA-CLAIM:(.+?) -->`, and returns the agent id of the comment with the
lowest `comment.id`. Returns `None` if no claim comments exist.

## Data flow (`Agent.process_issue`, new issues only)

```
branch = _claim_issue_and_create_branch(issue)   # remove label + assign + post_claim
if not self._claim_won(issue):
    log "lost claim race for #{n}; backing off"
    return IssueResult(success=False, branch=branch, error="lost claim race")
worktree = worktrees.create(...)                  # only the winner proceeds
```

Factoring:
- Inside `_claim_issue_and_create_branch`, the existing plain hostname comment
  (`issue.create_comment(...)`) is replaced by a call to
  `self.github.post_claim(issue, self.agent_id)`. Label removal and assignment
  stay as they are.
- A new verify seam `Agent._claim_won(issue) -> bool` returns
  `winner is None or winner == self.agent_id`, where
  `winner = self.github.claim_winner(issue)`. This isolates the verdict so it is
  unit-testable without the full `process_issue` pipeline.

Resumed sessions (existing session state) skip claiming entirely — the agent
already owns the branch — so the verify only runs on first claim.

### Loser behavior

The loser simply backs off. Nothing has been created yet (worktree and branch
are created **after** the verify), so there is nothing to clean up. Label
removal and assignment remain (the winner owns them; both are idempotent). The
loser's claim comment is left in place — harmless noise, no delete round-trip.

### Fail-safe: `winner is None`

If the marker mechanism fails (e.g. `post_claim` raised, or no markers parse),
`claim_winner` returns `None` and the agent treats the claim as **won** and
proceeds. Rationale: a permanently unprocessed issue (stall) is worse than the
rare duplicate; this degrades to today's non-atomic "just process it" behavior.

## Error handling

- `post_claim` failure: log a warning; `_attempt_claim` still calls
  `claim_winner`. If the comment never posted, the agent may or may not find a
  winner — the `None`-means-won fallback keeps it moving.
- `claim_winner` GitHub error: caught, logged, returns `None` (→ won, fail-safe).

## Testing

- `GitHubClient.claim_winner`: mocked `issue.get_comments()` returning comments
  with marker bodies and ids → lowest id wins; `None` when no markers;
  non-marker comments ignored; out-of-order ids handled (lowest id, not list
  order).
- `GitHubClient.post_claim`: asserts `issue.create_comment` called with a body
  containing the marker and the agent id.
- `Agent._claim_won`: mocked github → returns True when winner == own id,
  True when winner is None (fail-safe), False when winner is another id.

## Scope estimate

- `src/agent.py`: `agent_id` field, `_claim_won` helper, `post_claim` call
  replacing the plain comment, claim-verify branch in `process_issue` (~20 lines)
- `src/github_client.py`: `post_claim`, `claim_winner` (~25 lines)
- tests: `tests/test_github_client.py` (extend), `tests/test_review_loop.py` or
  a new `tests/test_claiming.py` for `_attempt_claim`
