"""Rolling 5-hour / 7-day usage guardrail for the Claude subscription.

Anthropic's subscription limits (a 5-hour rolling window and a weekly window)
are NOT queryable — there's no CLI/API for remaining quota. So this component:

1. **Proactive** — tracks the agent's OWN token consumption in rolling 5h and 7d
   windows and reports when a configured budget is exceeded, so the poll loop can
   pause picking up new issues (reserving headroom for the operator's own use).
2. **Reactive** — records a "paused until" timestamp when the Claude CLI actually
   reports a limit was hit, so the loop backs off instead of hammering a capped
   account.

The ledger is a small JSON file (list of ``[epoch, tokens]`` events + an optional
``paused_until``). ``now`` is injectable on every method so behaviour is fully
deterministic under test.
"""

import json
import logging
import time
from pathlib import Path
from typing import List, Optional

log = logging.getLogger("agent")

WINDOW_5H = 5 * 3600
WINDOW_7D = 7 * 24 * 3600


class UsageLimiter:
    """Persistent rolling-window token budget + reactive backoff."""

    def __init__(self, path: Path, limit_5h_tokens: int, limit_7d_tokens: int):
        """
        Args:
            path: JSON ledger file (created on first write).
            limit_5h_tokens: token budget for the rolling 5h window; 0 disables it.
            limit_7d_tokens: token budget for the rolling 7d window; 0 disables it.
        """
        self.path = path
        self.limit_5h = max(0, int(limit_5h_tokens))
        self.limit_7d = max(0, int(limit_7d_tokens))
        self._events: List[List[float]] = []   # [[epoch, tokens], ...]
        self._paused_until: float = 0.0
        self._load()

    @property
    def budgets_enabled(self) -> bool:
        return self.limit_5h > 0 or self.limit_7d > 0

    # ---- persistence -------------------------------------------------------

    def _load(self) -> None:
        try:
            if self.path.exists():
                data = json.loads(self.path.read_text())
                self._events = [[float(ts), int(tok)] for ts, tok in data.get("events", [])]
                self._paused_until = float(data.get("paused_until", 0.0))
        except Exception as e:
            log.warning(f"UsageLimiter: could not read ledger {self.path}: {e}")

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"events": self._events, "paused_until": self._paused_until}))
            tmp.replace(self.path)
        except Exception as e:
            log.warning(f"UsageLimiter: could not write ledger {self.path}: {e}")

    # ---- recording ---------------------------------------------------------

    def _prune(self, now: float) -> None:
        cutoff = now - WINDOW_7D
        self._events = [e for e in self._events if e[0] >= cutoff]

    def record(self, tokens: int, now: Optional[float] = None) -> None:
        """Append one Claude run's token consumption to the ledger."""
        if not tokens or tokens <= 0:
            return
        now = time.time() if now is None else now
        self._events.append([now, int(tokens)])
        self._prune(now)
        self._save()

    def _sum(self, window: int, now: float) -> int:
        cutoff = now - window
        return sum(int(tok) for ts, tok in self._events if ts >= cutoff)

    def tokens_5h(self, now: Optional[float] = None) -> int:
        return self._sum(WINDOW_5H, time.time() if now is None else now)

    def tokens_7d(self, now: Optional[float] = None) -> int:
        return self._sum(WINDOW_7D, time.time() if now is None else now)

    # ---- reactive backoff --------------------------------------------------

    def pause_until(self, reset_at: float) -> None:
        """The CLI reported a real limit — pause new work until ``reset_at``."""
        self._paused_until = max(self._paused_until, float(reset_at))
        self._save()

    # ---- the check ---------------------------------------------------------

    def blocked(self, now: Optional[float] = None) -> Optional[str]:
        """Return a human-readable reason if new pickups should pause, else None.

        Precedence: reactive pause first, then the 5h budget, then the 7d budget.
        """
        now = time.time() if now is None else now

        if now < self._paused_until:
            mins = int((self._paused_until - now) / 60) + 1
            return f"Claude reported a usage limit — paused ~{mins} min until reset"

        if self.limit_5h > 0:
            used = self._sum(WINDOW_5H, now)
            if used >= self.limit_5h:
                free_in = self._seconds_until_under(WINDOW_5H, self.limit_5h, now)
                return (f"5h token budget reached ({used:,}/{self.limit_5h:,}) — "
                        f"frees in ~{int(free_in / 60) + 1} min")

        if self.limit_7d > 0:
            used = self._sum(WINDOW_7D, now)
            if used >= self.limit_7d:
                free_in = self._seconds_until_under(WINDOW_7D, self.limit_7d, now)
                return (f"7d token budget reached ({used:,}/{self.limit_7d:,}) — "
                        f"frees in ~{int(free_in / 3600) + 1} h")

        return None

    def _seconds_until_under(self, window: int, limit: int, now: float) -> float:
        """Seconds until enough events roll off ``window`` to drop under ``limit``.

        Events exit the window oldest-first; the moment the last-needed event
        exits (its ``ts + window``) is when the windowed sum falls below limit.
        """
        cutoff = now - window
        recent = sorted([e for e in self._events if e[0] >= cutoff], key=lambda e: e[0])
        total = sum(int(tok) for _, tok in recent)
        for ts, tok in recent:
            total -= int(tok)
            if total < limit:
                return max(0.0, (ts + window) - now)
        return 0.0
