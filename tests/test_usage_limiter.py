"""Tests for the rolling 5h/7d usage guardrail (UsageLimiter)."""

from src.usage_limiter import UsageLimiter, WINDOW_5H, WINDOW_7D

T0 = 1_000_000_000.0  # fixed base epoch; all tests inject `now` for determinism


def _limiter(tmp_path, l5h=100, l7d=1000):
    return UsageLimiter(tmp_path / "ledger.json", l5h, l7d)


class TestBudgets:
    def test_under_budget_not_blocked(self, tmp_path):
        lim = _limiter(tmp_path)
        lim.record(50, now=T0)
        assert lim.blocked(now=T0) is None

    def test_5h_budget_blocks(self, tmp_path):
        lim = _limiter(tmp_path, l5h=100, l7d=1000)
        lim.record(60, now=T0)
        lim.record(50, now=T0 + 10)          # 110 in 5h window ≥ 100
        reason = lim.blocked(now=T0 + 20)
        assert reason is not None and "5h" in reason

    def test_5h_rolls_off_after_window(self, tmp_path):
        lim = _limiter(tmp_path, l5h=100, l7d=100000)
        lim.record(120, now=T0)
        assert lim.blocked(now=T0 + 60) is not None          # still inside 5h
        # Once the event is older than 5h it no longer counts toward the 5h sum.
        assert lim.blocked(now=T0 + WINDOW_5H + 1) is None

    def test_7d_budget_blocks_even_when_5h_clear(self, tmp_path):
        lim = _limiter(tmp_path, l5h=1_000_000, l7d=100)
        # Spread usage so no single 5h window trips, but the 7d total does.
        lim.record(60, now=T0)
        lim.record(60, now=T0 + WINDOW_5H + 100)   # long after the 5h window
        reason = lim.blocked(now=T0 + WINDOW_5H + 200)
        assert reason is not None and "7d" in reason

    def test_zero_limits_disable_budgets(self, tmp_path):
        lim = _limiter(tmp_path, l5h=0, l7d=0)
        lim.record(10_000_000, now=T0)
        assert lim.blocked(now=T0) is None
        assert lim.budgets_enabled is False

    def test_seconds_until_under_points_to_rolloff(self, tmp_path):
        lim = _limiter(tmp_path, l5h=100, l7d=100000)
        lim.record(120, now=T0)
        free = lim._seconds_until_under(WINDOW_5H, 100, now=T0 + 100)
        # The single event exits the window at T0 + WINDOW_5H.
        assert abs(free - (WINDOW_5H - 100)) < 1.0


class TestReactiveBackoff:
    def test_pause_until_blocks_then_frees(self, tmp_path):
        lim = _limiter(tmp_path, l5h=0, l7d=0)   # budgets off; only reactive
        lim.pause_until(T0 + 3600)
        assert lim.blocked(now=T0 + 10) is not None
        assert lim.blocked(now=T0 + 3601) is None

    def test_pause_takes_precedence_over_budget(self, tmp_path):
        lim = _limiter(tmp_path, l5h=100, l7d=1000)
        lim.pause_until(T0 + 3600)
        reason = lim.blocked(now=T0 + 10)
        assert "usage limit" in reason.lower()


class TestPersistence:
    def test_ledger_survives_reload(self, tmp_path):
        path = tmp_path / "ledger.json"
        a = UsageLimiter(path, 100, 1000)
        a.record(80, now=T0)
        a.pause_until(T0 + 500)
        b = UsageLimiter(path, 100, 1000)        # fresh instance, same file
        assert b.tokens_5h(now=T0 + 10) == 80
        assert b.blocked(now=T0 + 10) is not None

    def test_prune_drops_events_older_than_7d(self, tmp_path):
        lim = _limiter(tmp_path, l5h=1_000_000, l7d=1_000_000)
        lim.record(10, now=T0)
        lim.record(10, now=T0 + WINDOW_7D + 100)   # triggers prune of the first
        assert lim.tokens_7d(now=T0 + WINDOW_7D + 100) == 10


class TestDetectUsageLimit:
    def test_detects_limit_messages(self):
        from src.claude_code import detect_usage_limit
        for msg in [
            "You've reached your usage limit reached for the 5-hour window",
            "Weekly limit will reset soon",
            "429 Too Many Requests",
            "quota exceeded",
        ]:
            assert detect_usage_limit(msg) is not None

    def test_ignores_normal_output(self):
        from src.claude_code import detect_usage_limit
        assert detect_usage_limit("Implemented the feature; all tests pass.") is None
        assert detect_usage_limit("") is None

    def test_parses_reset_in_minutes(self):
        from src.claude_code import detect_usage_limit
        reset = detect_usage_limit("usage limit reached — resets in 30 minutes")
        assert reset is not None and reset > 0  # future epoch, not the 0.0 sentinel
