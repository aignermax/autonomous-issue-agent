"""Tests for shared poll-loop backoff (src/backoff.py)."""
from src.backoff import backoff_seconds


def test_no_failures_returns_base():
    assert backoff_seconds(0, 15) == 15
    assert backoff_seconds(-1, 15) == 15


def test_exponential_growth_with_cap():
    assert backoff_seconds(1, 15) == 30
    assert backoff_seconds(2, 15) == 60
    assert backoff_seconds(3, 15) == 120
    assert backoff_seconds(6, 15) == 900   # capped (15*64=960 > 900)
    assert backoff_seconds(100, 15) == 900  # no overflow


def test_custom_cap():
    assert backoff_seconds(10, 15, cap=60) == 60
