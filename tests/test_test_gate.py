"""Tests for TestGate."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.test_gate import TestGate


def _config(tmp_path, *, enabled=True, test_cmd=None, timeout=60,
            tools_dir=None, tools_python="python3"):
    c = MagicMock()
    c.test_gate_enabled = enabled
    c.test_cmd = test_cmd
    c.test_timeout = timeout
    c.tools_dir = tools_dir if tools_dir is not None else tmp_path
    c.tools_python = tools_python
    return c


class TestResolveCommand:
    def test_explicit_cmd_is_split(self, tmp_path):
        gate = TestGate(_config(tmp_path, test_cmd="pytest -q tests"))
        assert gate._resolve_command() == ["pytest", "-q", "tests"]

    def test_disabled_returns_none(self, tmp_path):
        gate = TestGate(_config(tmp_path, enabled=False, test_cmd="pytest"))
        assert gate._resolve_command() is None

    def test_smart_test_used_when_present(self, tmp_path):
        (tmp_path / "smart_test.py").write_text("# stub")
        gate = TestGate(_config(tmp_path, tools_dir=tmp_path,
                                tools_python="/venv/python3"))
        assert gate._resolve_command() == [
            "/venv/python3", str(tmp_path / "smart_test.py")
        ]

    def test_none_when_no_cmd_and_no_smart_test(self, tmp_path):
        gate = TestGate(_config(tmp_path, tools_dir=tmp_path))
        assert gate._resolve_command() is None

    def test_is_available_reflects_resolution(self, tmp_path):
        assert TestGate(_config(tmp_path, test_cmd="pytest")).is_available() is True
        assert TestGate(_config(tmp_path)).is_available() is False

    def test_malformed_cmd_returns_none(self, tmp_path):
        gate = TestGate(_config(tmp_path, test_cmd='pytest "unclosed'))
        assert gate._resolve_command() is None

    def test_none_when_tools_dir_falsy(self, tmp_path):
        c = _config(tmp_path)
        c.tools_dir = None
        assert TestGate(c)._resolve_command() is None

    def test_explicit_cmd_preserves_windows_path(self, tmp_path):
        import os
        gate = TestGate(_config(tmp_path, test_cmd=r"C:\tools\py.exe -q"))
        parts = gate._resolve_command()
        if os.name == "nt":
            assert parts == [r"C:\tools\py.exe", "-q"]
        else:
            # POSIX parsing strips backslashes; just assert it splits into 2 tokens
            assert len(parts) == 2


class TestRun:
    def test_skipped_returns_none_and_no_subprocess(self, tmp_path):
        gate = TestGate(_config(tmp_path))  # no cmd, no smart_test → unavailable
        with patch("src.test_gate.subprocess.run") as run:
            assert gate.run(tmp_path) is None
            run.assert_not_called()

    def test_exit_zero_is_ok(self, tmp_path):
        gate = TestGate(_config(tmp_path, test_cmd="pytest"))
        with patch("src.test_gate.subprocess.run") as run:
            run.return_value = MagicMock(returncode=0, stdout="all passed")
            result = gate.run(tmp_path)
        assert result.verdict == "OK"
        assert result.has_blocking is False

    def test_nonzero_is_blocking_with_output_tail(self, tmp_path):
        gate = TestGate(_config(tmp_path, test_cmd="pytest"))
        with patch("src.test_gate.subprocess.run") as run:
            run.return_value = MagicMock(returncode=1, stdout="FAILED test_foo",
                                         stderr="traceback XYZ")
            result = gate.run(tmp_path)
        assert result.has_blocking is True
        assert len(result.findings) == 1
        assert "FAILED test_foo" in result.findings[0].text
        assert "traceback XYZ" in result.findings[0].text
        assert result.raw_output == "FAILED test_footraceback XYZ"

    def test_timeout_is_blocking(self, tmp_path):
        gate = TestGate(_config(tmp_path, test_cmd="pytest", timeout=1))
        with patch("src.test_gate.subprocess.run",
                   side_effect=subprocess.TimeoutExpired(cmd="pytest", timeout=1)):
            result = gate.run(tmp_path)
        assert result.has_blocking is True
        assert "timed out" in result.summary.lower()

    def test_launch_failure_is_blocking(self, tmp_path):
        gate = TestGate(_config(tmp_path, test_cmd="nope-xyz"))
        with patch("src.test_gate.subprocess.run",
                   side_effect=FileNotFoundError("not found")):
            result = gate.run(tmp_path)
        assert result.has_blocking is True
        assert "could not be launched" in result.summary.lower()
