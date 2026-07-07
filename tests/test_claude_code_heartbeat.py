"""Tests for the Worker heartbeat callback in ClaudeCode.execute.

The callback must:
  - fire at most once per heartbeat_interval_sec while the subprocess is alive
  - never fire before heartbeat_interval_sec has elapsed
  - swallow exceptions from the callback (a flaky observer must not crash the agent)
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src import claude_code


def _build_runner(tmp_path: Path) -> claude_code.ClaudeCode:
    # Bypass the real CLI verification (no `claude` binary needed in tests).
    with patch.object(claude_code.ClaudeCode, "_verify_installation", return_value=None), \
         patch.object(claude_code, "find_claude_cli", return_value="/usr/bin/true"):
        return claude_code.ClaudeCode(working_dir=tmp_path, max_turns=10)


class _FakeProcess:
    """Mimics subprocess.Popen enough for execute()'s polling loop.

    Stays "alive" for `ticks` polls (poll() returns None), then exits
    cleanly with a JSON Claude response on stdout.
    """
    def __init__(self, ticks_alive: int):
        self.pid = 12345
        self._ticks_left = ticks_alive
        self.returncode = None

    def poll(self):
        if self._ticks_left > 0:
            self._ticks_left -= 1
            return None
        self.returncode = 0
        return 0

    def communicate(self):
        return ('{"result": "ok", "num_turns": 3, "usage": {}}', "")

    def kill(self):
        self.returncode = -9

    def wait(self, timeout=None):
        return self.returncode or 0


def test_heartbeat_fires_after_interval(tmp_path):
    """First callback fires when elapsed time crosses heartbeat_interval_sec.

    Simulated wall time advances by check_interval (60 s) per poll. With
    heartbeat_interval_sec=300, the callback should fire on the 5th poll
    (300 s elapsed), and again on the 10th (600 s elapsed).
    """
    runner = _build_runner(tmp_path)

    fake_process = _FakeProcess(ticks_alive=12)
    seen_calls = []

    def fake_heartbeat(elapsed_sec, idle_sec):
        seen_calls.append(elapsed_sec)

    # Drive time deterministically: each call to time.time() during the poll
    # loop advances by `check_interval` (60s). We also need a no-op time.sleep.
    fake_now = [1_000_000.0]

    def fake_time():
        return fake_now[0]

    def fake_sleep(_):
        fake_now[0] += 60  # one minute per poll tick

    with patch.object(claude_code.subprocess, "Popen", return_value=fake_process), \
         patch.object(claude_code, "time", MagicMock(time=fake_time, sleep=fake_sleep)), \
         patch.object(runner, "_get_repo_last_modified_time", return_value=0.0):
        runner.execute(
            "prompt",
            on_heartbeat=fake_heartbeat,
            heartbeat_interval_sec=300,
        )

    # Expect heartbeats at roughly 300s and 600s elapsed. Allow slack for the
    # exact loop boundary (the check happens after `time.sleep`, so first tick
    # may register 60s, second 120s, etc.; 5th tick = 300s).
    assert len(seen_calls) >= 2, f"expected ≥2 heartbeats, got {seen_calls}"
    assert seen_calls[0] >= 300, f"first heartbeat must be >= interval, got {seen_calls[0]}"
    assert seen_calls[1] >= seen_calls[0] + 300, (
        f"second heartbeat must be >= one interval after first; got {seen_calls}"
    )


def test_heartbeat_callback_exceptions_are_swallowed(tmp_path):
    """A raising callback must NOT abort the run — the agent logs and continues."""
    runner = _build_runner(tmp_path)
    fake_process = _FakeProcess(ticks_alive=8)

    def angry_heartbeat(elapsed_sec, idle_sec):
        raise RuntimeError("github is down")

    fake_now = [1_000_000.0]

    def fake_time():
        return fake_now[0]

    def fake_sleep(_):
        fake_now[0] += 60

    with patch.object(claude_code.subprocess, "Popen", return_value=fake_process), \
         patch.object(claude_code, "time", MagicMock(time=fake_time, sleep=fake_sleep)), \
         patch.object(runner, "_get_repo_last_modified_time", return_value=0.0):
        # Should NOT raise: the callback's RuntimeError must be swallowed inside execute()
        runner.execute(
            "prompt",
            on_heartbeat=angry_heartbeat,
            heartbeat_interval_sec=300,
        )


def test_no_heartbeat_when_callback_is_none(tmp_path):
    """Backwards-compat: with no callback, execute behaves as before."""
    runner = _build_runner(tmp_path)
    fake_process = _FakeProcess(ticks_alive=8)
    fake_now = [1_000_000.0]

    with patch.object(claude_code.subprocess, "Popen", return_value=fake_process), \
         patch.object(claude_code, "time",
                      MagicMock(time=lambda: fake_now[0],
                                sleep=lambda _: fake_now.__setitem__(0, fake_now[0] + 60))), \
         patch.object(runner, "_get_repo_last_modified_time", return_value=0.0):
        # Just confirm it returns cleanly — no on_heartbeat passed.
        output, _, _ = runner.execute("prompt")
    assert output == "ok"
