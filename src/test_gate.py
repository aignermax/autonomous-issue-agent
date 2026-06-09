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
          1. config.test_cmd (explicit AGENT_TEST_CMD override, POSIX-split)
          2. {tools_python} {tools_dir}/smart_test.py if that file exists
          3. None
        """
        if not self.config.test_gate_enabled:
            return None
        if self.config.test_cmd:
            return shlex.split(self.config.test_cmd, posix=(os.name != "nt"))
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
