"""
Claude Code CLI integration.
"""

import subprocess
import logging
import re
import os
import shutil
import platform
from pathlib import Path
from typing import Optional, Tuple
from dataclasses import dataclass

log = logging.getLogger("agent")


@dataclass
class UsageStats:
    """Token usage and cost statistics."""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens + self.cache_read_tokens + self.cache_creation_tokens

    @property
    def estimated_cost_usd(self) -> float:
        """
        Calculate cost based on Claude Sonnet 4 pricing (as of March 2025):
        - Input: $3.00 / 1M tokens
        - Output: $15.00 / 1M tokens
        - Cache reads: $0.30 / 1M tokens
        - Cache writes: $3.75 / 1M tokens
        """
        cost = 0.0
        cost += (self.input_tokens / 1_000_000) * 3.00
        cost += (self.output_tokens / 1_000_000) * 15.00
        cost += (self.cache_read_tokens / 1_000_000) * 0.30
        cost += (self.cache_creation_tokens / 1_000_000) * 3.75
        return cost


def find_claude_cli() -> str:
    """
    Find Claude CLI executable in PATH or common install locations.
    
    Returns:
        Path to claude executable
        
    Raises:
        RuntimeError: If Claude CLI cannot be found
    """
    # Allow override via environment variable
    if os.environ.get("CLAUDE_CLI_PATH"):
        path = os.environ["CLAUDE_CLI_PATH"]
        if os.path.exists(path):
            return path
        log.warning(f"CLAUDE_CLI_PATH set but file not found: {path}")
    
    # Try PATH first
    claude_cmd = shutil.which("claude")
    if claude_cmd:
        return claude_cmd

    # Windows: npm global modules
    if platform.system() == "Windows":
        npm_path = os.path.expanduser("~/AppData/Roaming/npm/claude.cmd")
        if os.path.exists(npm_path):
            return npm_path

    # Unix-like: common npm global locations
    unix_paths = [
        os.path.expanduser("~/.npm-global/bin/claude"),
        "/usr/local/bin/claude",
        os.path.expanduser("~/.local/bin/claude"),
        "/opt/homebrew/bin/claude",  # Homebrew on Apple Silicon
    ]
    for path in unix_paths:
        if os.path.exists(path):
            return path

    raise RuntimeError(
        "Claude Code CLI not found. Install with:\n"
        "  npm install -g @anthropic-ai/claude-code\n\n"
        "Or set CLAUDE_CLI_PATH environment variable to the claude executable path."
    )


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
        self.claude_cli = find_claude_cli()
        self._verify_installation()

    def _verify_installation(self) -> None:
        """Verify that Claude Code CLI is installed and working."""
        try:
            result = subprocess.run(
                [self.claude_cli, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                log.info(f"Claude Code version: {result.stdout.strip()}")
            else:
                raise RuntimeError(f"Claude CLI returned error: {result.stderr}")
        except FileNotFoundError:
            raise RuntimeError(
                f"Claude CLI not found at: {self.claude_cli}\n"
                "Install: npm install -g @anthropic-ai/claude-code"
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError("Claude CLI verification timed out")

    def execute(self, prompt: str, resume_file: Optional[Path] = None) -> Tuple[str, bool, UsageStats]:
        """
        Run a prompt through Claude Code headless mode.

        Args:
            prompt: The prompt to execute
            resume_file: Optional state file to resume from previous session

        Returns:
            Tuple of (output string, reached_max_turns, usage_stats)
        """
        cmd = [
            self.claude_cli,
            "-p", prompt,
            "--dangerously-skip-permissions",
            "--output-format", "json",
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

        # Parse JSON response to extract result and usage
        try:
            import json
            response = json.loads(output)
            actual_output = response.get("result", output)
            reached_max_turns = response.get("num_turns", 0) >= self.max_turns
            usage = self._parse_json_usage(response)
        except (json.JSONDecodeError, KeyError) as e:
            log.warning(f"Failed to parse JSON output: {e}")
            actual_output = output
            reached_max_turns = "Reached max turns" in output or "max turns" in output.lower()
            usage = UsageStats()

        log.info(
            f"Token usage: {usage.total_tokens} tokens, "
            f"Estimated cost: ${usage.estimated_cost_usd:.4f}"
        )
        return actual_output, reached_max_turns, usage

    def _parse_json_usage(self, response: dict) -> UsageStats:
        """Parse usage statistics from JSON response."""
        usage_data = response.get("usage", {})
        return UsageStats(
            input_tokens=usage_data.get("input_tokens", 0),
            output_tokens=usage_data.get("output_tokens", 0),
            cache_read_tokens=usage_data.get("cache_read_tokens", 0),
            cache_creation_tokens=usage_data.get("cache_creation_tokens", 0),
        )
