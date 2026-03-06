"""
Claude Code CLI integration.
"""

import subprocess
import logging
import re
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
            "claude", "-p", prompt,
            "--dangerously-skip-permissions",
            "--output-format", "json",  # Changed to JSON to parse usage stats
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

        log.info(f"Token usage: {usage.total_tokens:,} tokens, Estimated cost: ${usage.estimated_cost_usd:.4f}")

        return actual_output, reached_max_turns, usage

    def _parse_json_usage(self, response: dict) -> UsageStats:
        """
        Parse token usage from Claude Code JSON response.

        Args:
            response: Parsed JSON response from Claude Code

        Returns:
            UsageStats object
        """
        usage = UsageStats()

        # Extract from usage object
        usage_obj = response.get("usage", {})
        usage.input_tokens = usage_obj.get("input_tokens", 0)
        usage.output_tokens = usage_obj.get("output_tokens", 0)
        usage.cache_read_tokens = usage_obj.get("cache_read_input_tokens", 0)
        usage.cache_creation_tokens = usage_obj.get("cache_creation_input_tokens", 0)

        return usage

    def _parse_usage(self, output: str) -> UsageStats:
        """
        Parse token usage from Claude Code output.

        Claude Code outputs usage stats like:
        "Usage: input=12345 output=6789 cache_read=1234 cache_creation=5678"

        Args:
            output: Claude Code stdout

        Returns:
            UsageStats object
        """
        usage = UsageStats()

        # Try to find usage pattern in output
        patterns = {
            'input_tokens': r'input[_\s]*tokens?[:\s=]+(\d+)',
            'output_tokens': r'output[_\s]*tokens?[:\s=]+(\d+)',
            'cache_read_tokens': r'cache[_\s]*read[_\s]*tokens?[:\s=]+(\d+)',
            'cache_creation_tokens': r'cache[_\s]*(?:creation|write)[_\s]*tokens?[:\s=]+(\d+)',
        }

        for field, pattern in patterns.items():
            match = re.search(pattern, output, re.IGNORECASE)
            if match:
                setattr(usage, field, int(match.group(1)))

        return usage
