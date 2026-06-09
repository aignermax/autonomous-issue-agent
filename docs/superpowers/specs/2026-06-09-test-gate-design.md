# Test-Gate — Design Spec

**Date:** 2026-06-09
**Status:** Approved (design), pending implementation plan
**Branch:** `feat/test-gate`

## Problem

The agent's only quality control before closing an issue is the LLM reviewer
(`src/reviewer.py`), which *reads the PR diff*. Nothing runs the build/tests
deterministically. The worker claims "tests pass" and the reviewer believes it
from the diff. A PR with red tests can therefore be created, reviewed as OK,
and the issue closed — without anyone executing the tests.

We want a **deterministic** gate: run the project's tests, and treat failure as
a blocking condition that forces the worker to fix before the issue is closed.

## Goal

Add a test gate that executes a configurable test command in the worktree and
blocks completion on failure, reusing the existing Worker→Reviewer retry and
`needs-human` escalation machinery. The gate is effectively "Reviewer #0":
deterministic, runs before the LLM reviewer each round.

Non-goals: per-repo test-command mapping (single default + override is enough
for now), CI integration, parsing smart_test's specific output format,
distinguishing build-failure from test-failure.

## Approach (chosen: A)

Integrate the gate **inside the existing `_run_review_loop`**, before the LLM
reviewer, rather than as a separate pre-PR gate. This maximises reuse: the
retry loop, `build_retry_prompt`, and `_flag_for_human` escalation all stay as
they are. A (transiently) red PR is the natural "under review" state.

Rejected alternatives:
- **B — hard gate before PR creation:** would duplicate the retry loop.
- **C — reviewer runs tests itself (status quo):** non-deterministic; the very
  problem we are fixing.

## Component: `TestGate` (`src/test_gate.py`)

A small, network-free class with one responsibility: run the test command in a
worktree and return a `ReviewResult` (reuse the dataclass from `reviewer.py` —
no new type). Being pure (no GitHub calls) keeps it trivially unit-testable;
the loop posts the PR comment.

```python
class TestGate:
    def __init__(self, config): ...
    def is_available(self) -> bool: ...          # is there a runnable command?
    def run(self, worktree_path: Path) -> ReviewResult | None: ...
```

### Command resolution

1. `config.test_cmd` (from `AGENT_TEST_CMD`) if set — explicit override.
2. else `{tools_python} {tools_dir}/smart_test.py` if that file exists.
3. else **no command** → gate is unavailable.

### Return contract

| Situation | Return |
|---|---|
| No command available (resolution falls through) | `None` (gate skipped) |
| Command exits 0 | `ReviewResult(verdict="OK", summary="Tests passed")` |
| Command exits non-zero | `ReviewResult(verdict="BLOCKING", findings=[Finding("BLOCKING", <stdout tail>)])` |
| Timeout (`AGENT_TEST_TIMEOUT`) | `ReviewResult(verdict="BLOCKING", summary="test command timed out")` |
| Explicit `AGENT_TEST_CMD` not launchable (FileNotFoundError) | `ReviewResult(verdict="BLOCKING", summary="test command could not be launched")` |

Notes:
- The blocking `Finding` text carries a truncated stdout tail (~1500 chars),
  **not** a parse of smart_test's format — so any test command works.
- Timeout and launch-failure are fail-safe BLOCKING, mirroring the reviewer's
  existing "unparseable output → BLOCKING" philosophy (escalate to a human
  rather than silently pass).
- Auto-detected-but-missing tool → falls through to `None` (skip), so a missing
  .NET tool never blocks a non-.NET repo. An *explicit* command that fails to
  launch is a config error → BLOCKING (visible, not silently skipped).

## Data flow — `_run_review_loop` (`src/agent.py`)

Per round: **gate first, then LLM reviewer.**

```
gate = TestGate(config)
for round in 1..max_review_rounds:
    gate_result = gate.run(worktree_path)            # None = skipped
    if gate_result and gate_result.has_blocking:
        blocking = gate_result                       # skip LLM reviewer (save cost)
        post short "tests red" comment on PR
    else:
        review = reviewer.review(...)                # only when tests green/skipped
        if not review.has_blocking:
            return False                             # fully approved → done
        blocking = review
    if round == max_review_rounds:
        _flag_for_human(issue, pr, blocking)
        return True
    worker.execute(build_retry_prompt(review=blocking))   # existing retry
    commit_and_push(...)
return False
```

Test-block and review-block funnel through the **same** retry/escalation path.
`build_retry_prompt` already accepts a `ReviewResult`, so a synthesised gate
result feeds it unchanged.

The gate is disabled entirely when `config.test_gate_enabled` is false, in which
case the loop behaves exactly as today.

## Config additions (`src/config.py`)

```
AGENT_TEST_GATE     = "true"      # opt-out switch
AGENT_TEST_CMD      = None        # explicit override; default resolves to smart_test.py
AGENT_TEST_TIMEOUT  = 1800        # seconds (30 min), guards against hangs
```

## Edge cases (deliberately handled)

- **Non-.NET repo / no tool:** resolution → `None` → loop unchanged. Preserves
  "works with any repository".
- **Test-only / investigation issues:** gate still applies; `dotnet test` with
  no tests typically exits 0 → green.
- **First round already red:** PR exists briefly "red", worker fixes — the
  natural review state.
- **Worker retry hits max turns:** existing warning logged; next round re-runs
  the gate (or escalates if it was the last round).
- **WiX-in-WSL (cannot build):** residual false-red risk; mitigated by
  `AGENT_TEST_CMD` override or the opt-out switch. No special-casing in code
  (YAGNI).

## Testing

`tests/test_test_gate.py` (new) — fake commands, no network:
- exit 0 → `ReviewResult(OK)`
- exit 1 → `BLOCKING`, stdout tail present in a finding
- no command available → `None`
- timeout → `BLOCKING`
- explicit command not launchable → `BLOCKING`

`tests/test_review_loop.py` (extend):
- gate red on round 1 → worker retried, LLM reviewer **not** called that round
- gate green → LLM reviewer called
- gate red through all rounds → `needs-human` escalation
- gate disabled / skipped → behaves like today

## Scope estimate

- `src/test_gate.py` — new, ~80 lines
- `src/agent.py` `_run_review_loop` — ~15 changed lines
- `src/config.py` — 3 new fields
- tests — two files
