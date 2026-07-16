"""Deterministic build/test gate.

Runs a configurable test command inside a worktree and returns a ReviewResult
so the existing review loop can treat a red test run as a BLOCKING finding.
The gate performs no GitHub calls — the loop posts any PR comment.
"""

import logging
import os
import shlex
import subprocess
from pathlib import Path
from typing import List, Optional

from .reviewer import ReviewResult, Finding

log = logging.getLogger("agent")

_OUTPUT_TAIL_CHARS = 1500


class TestGate:
    """Runs the project's test command and reports pass/fail as a ReviewResult."""

    __test__ = False

    def __init__(self, config):
        """
        Args:
            config: Config instance. Reads test_gate_enabled, test_cmd,
                    test_timeout, tools_dir, tools_python.
        """
        self.config = config

    def _resolve_command(self) -> Optional[List[str]]:
        """Resolve the test command, or None if none is available.

        Resolution order:
          1. config.test_cmd (explicit AGENT_TEST_CMD override, split with
             platform-appropriate quoting: POSIX off Windows, Windows-mode on Windows)
          2. {tools_python} {tools_dir}/smart_test.py if that file exists
          3. None
        """
        if not self.config.test_gate_enabled:
            return None
        if self.config.test_cmd:
            try:
                return shlex.split(self.config.test_cmd, posix=(os.name != "nt"))
            except ValueError as exc:
                log.error(
                    f"AGENT_TEST_CMD is not a parseable command ({exc}); "
                    f"value={self.config.test_cmd!r}. Disabling gate this run."
                )
                return None
        tools_dir = self.config.tools_dir
        tools_python = self.config.tools_python
        if tools_dir and tools_python:
            smart_test = Path(tools_dir) / "smart_test.py"
            if smart_test.is_file():
                return [str(tools_python), str(smart_test)]
        return None

    def is_available(self) -> bool:
        """True if a test command can be resolved."""
        return self._resolve_command() is not None

    def run(self, worktree_path: Path) -> Optional[ReviewResult]:
        """Run the test command in worktree_path.

        Returns:
            None if the gate is unavailable/disabled (skipped),
            ReviewResult(OK) on exit 0,
            ReviewResult(BLOCKING) on non-zero exit (combined stdout+stderr tail),
            timeout, or launch failure.
        """
        cmd = self._resolve_command()
        if cmd is None:
            log.info("Test gate skipped: no test command available")
            return None

        log.info(f"Test gate running: {' '.join(cmd)} (cwd={worktree_path})")
        try:
            result = subprocess.run(
                cmd,
                cwd=worktree_path,
                capture_output=True,
                text=True,
                timeout=self.config.test_timeout,
            )
        except subprocess.TimeoutExpired:
            log.warning(f"Test gate timed out after {self.config.test_timeout}s")
            return ReviewResult(
                verdict="BLOCKING",
                summary=f"Test command timed out after {self.config.test_timeout}s.",
                findings=[Finding(
                    severity="BLOCKING",
                    text=f"Command `{' '.join(cmd)}` did not finish within {self.config.test_timeout}s.",
                )],
            )
        except (FileNotFoundError, OSError) as exc:
            log.error(f"Test gate command could not be launched: {exc}")
            return ReviewResult(
                verdict="BLOCKING",
                summary=f"Test command could not be launched: {exc}",
                findings=[Finding(severity="BLOCKING", text=str(exc))],
            )

        if result.returncode == 0:
            log.info("Test gate: PASS")
            return ReviewResult(verdict="OK", summary="Tests passed.")

        combined = (result.stdout or "") + (result.stderr or "")
        tail = combined[-_OUTPUT_TAIL_CHARS:]
        log.warning(f"Test gate: FAIL (exit {result.returncode})")
        return ReviewResult(
            verdict="BLOCKING",
            summary=f"Test command failed (exit {result.returncode}).",
            findings=[Finding(
                severity="BLOCKING",
                text=f"Test command exited {result.returncode}. Output tail:\n{tail}",
            )],
            raw_output=combined,
        )
