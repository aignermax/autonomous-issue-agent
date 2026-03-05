"""
Claude Code CLI integration.
"""

import subprocess
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger("agent")


class ClaudeCode:
    """Runs Claude Code CLI in headless mode."""

    def __init__(self, working_dir: Path, max_turns: int = 300):
        """
        Initialize Claude Code runner.

        Args:
            working_dir: Directory where Claude Code should execute
            max_turns: Maximum number of tool call turns
        """
        self.working_dir = working_dir
        self.max_turns = max_turns
        self._verify_installation()

    def _verify_installation(self) -> None:
        """Verify that Claude Code CLI is installed."""
        result = subprocess.run(
            ["claude", "--version"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                "Claude Code CLI not found. "
                "Install: npm install -g @anthropic-ai/claude-code"
            )
        log.info(f"Claude Code version: {result.stdout.strip()}")

    def execute(self, prompt: str, resume_file: Optional[Path] = None) -> tuple[str, bool]:
        """
        Run a prompt through Claude Code headless mode.

        Args:
            prompt: The prompt to execute
            resume_file: Optional state file to resume from previous session

        Returns:
            Tuple of (output string, reached_max_turns)
        """
        cmd = [
            "claude", "-p", prompt,
            "--dangerously-skip-permissions",
            "--output-format", "text",
            "--max-turns", str(self.max_turns),
        ]

        # Add resume flag if continuing from previous session
        if resume_file and resume_file.exists():
            cmd.extend(["--resume", str(resume_file)])
            log.info(f"Resuming from session file: {resume_file}")

        log.info("Invoking Claude Code ...")
        result = subprocess.run(
            cmd,
            cwd=self.working_dir,
            capture_output=True,
            text=True,
            timeout=3600,  # 1 hour safety timeout
        )

        if result.returncode != 0:
            log.error(f"Claude Code failed: {result.stderr[:500]}")
            raise RuntimeError(f"Claude Code exit code {result.returncode}")

        output = result.stdout
        reached_max_turns = "Reached max turns" in output or "max turns" in output.lower()

        return output, reached_max_turns
