"""
Claude Code CLI integration.
"""

import subprocess
import logging
import re
import os
import pty
import select
import shutil
import platform
import time
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
        Run a prompt through Claude Code in headless JSON mode with activity monitoring.

        Args:
            prompt: The prompt to execute
            resume_file: Optional state file to resume from previous session

        Returns:
            Tuple of (output string, reached_max_turns, usage_stats)
        """
        log.info("Invoking Claude Code in headless JSON mode...")

        cmd = [
            self.claude_cli,
            "-p", prompt,
            "--output-format", "json",
            "--max-turns", str(self.max_turns),
            "--dangerously-skip-permissions"
        ]

        # Add resume flag if continuing from previous session
        if resume_file and resume_file.exists():
            cmd.extend(["--resume", str(resume_file)])
            log.info(f"Resuming from session file: {resume_file}")

        # Start Claude Code process
        process = subprocess.Popen(
            cmd,
            cwd=self.working_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        # Monitor activity with timeout (20 minutes max inactivity)
        max_inactivity = 1200  # 20 minutes
        check_interval = 60  # Check every minute
        last_activity_time = time.time()
        last_mtime = self._get_repo_last_modified_time()

        log.info(f"Monitoring Claude Code activity (PID: {process.pid})")

        while process.poll() is None:  # While process is running
            time.sleep(check_interval)

            # Check if repo files were modified (sign of activity)
            current_mtime = self._get_repo_last_modified_time()
            if current_mtime > last_mtime:
                last_activity_time = time.time()
                last_mtime = current_mtime
                log.debug(f"Activity detected (file modified)")

            # Check for inactivity timeout
            inactivity_duration = time.time() - last_activity_time
            if inactivity_duration > max_inactivity:
                log.warning(f"Claude Code appears stuck (no activity for {inactivity_duration:.0f}s)")
                log.warning(f"Killing stuck process (PID: {process.pid})")
                process.kill()
                process.wait(timeout=5)
                raise RuntimeError(
                    f"Claude Code stuck: no file modifications for {inactivity_duration:.0f}s. "
                    "Possible causes: waiting for input, infinite loop, or crashed silently."
                )

        # Process completed, get output
        stdout, stderr = process.communicate()
        result = subprocess.CompletedProcess(
            args=cmd,
            returncode=process.returncode,
            stdout=stdout,
            stderr=stderr
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

    def _get_repo_last_modified_time(self) -> float:
        """
        Get the most recent modification time of any file in the repository.

        Returns:
            Unix timestamp of the most recently modified file
        """
        import os
        max_mtime = 0.0
        try:
            for root, dirs, files in os.walk(self.working_dir):
                # Skip .git directory
                if '.git' in root:
                    continue
                for file in files:
                    try:
                        file_path = os.path.join(root, file)
                        mtime = os.path.getmtime(file_path)
                        if mtime > max_mtime:
                            max_mtime = mtime
                    except (OSError, PermissionError):
                        continue
        except Exception as e:
            log.warning(f"Error checking repo modification times: {e}")
        return max_mtime

    def _parse_json_usage(self, response: dict) -> UsageStats:
        """Parse usage statistics from JSON response."""
        usage_data = response.get("usage", {})
        return UsageStats(
            input_tokens=usage_data.get("input_tokens", 0),
            output_tokens=usage_data.get("output_tokens", 0),
            cache_read_tokens=usage_data.get("cache_read_tokens", 0),
            cache_creation_tokens=usage_data.get("cache_creation_tokens", 0),
        )

    def execute_interactive(self, prompt: str, resume_file: Optional[Path] = None, stream_output: bool = False) -> Tuple[str, bool, UsageStats]:
        """
        Run Claude Code in INTERACTIVE mode with pseudo-TTY to enable MCP support.

        This method uses a PTY (pseudo-terminal) to run Claude Code in interactive mode,
        which is required for MCP to function properly. The headless JSON mode hangs with MCP.

        Args:
            prompt: The prompt to execute
            resume_file: Optional state file to resume from previous session
            stream_output: If True, print output to console in real-time

        Returns:
            Tuple of (output string, reached_max_turns, usage_stats)
        """
        # Check if MCP is available
        mcp_config = self.working_dir.parent / ".mcp.json"
        has_mcp = mcp_config.exists()

        # Build command - NO -p flag for interactive mode!
        cmd = [
            self.claude_cli,
            "--max-turns", str(self.max_turns),
            "--permission-mode", "bypassPermissions",
        ]

        # Add MCP config if available
        if has_mcp:
            cmd.extend(["--mcp-config", str(mcp_config)])
            log.info(f"Using MCP config (interactive mode): {mcp_config}")

        # Add resume flag if continuing from previous session
        if resume_file and resume_file.exists():
            cmd.extend(["--resume", str(resume_file)])
            log.info(f"Resuming from session file: {resume_file}")

        log.info("Invoking Claude Code in interactive mode with PTY...")

        # Create pseudo-TTY
        master, slave = pty.openpty()

        try:
            # Start Claude Code in interactive mode
            process = subprocess.Popen(
                cmd,
                stdin=slave,
                stdout=slave,
                stderr=slave,
                cwd=self.working_dir,
                close_fds=True
            )

            os.close(slave)  # Close slave end in parent process

            # Wait for Claude to start and show initial prompts
            time.sleep(3)

            # Auto-answer the "Bypass Permissions" warning (option 2 = Yes, I accept)
            # We need to send Enter to select option 2 (which is already highlighted)
            try:
                os.write(master, b"\x1b[B")  # Down arrow to option 2
                time.sleep(0.5)
                os.write(master, b"\n")  # Enter to confirm
                time.sleep(2)
            except OSError:
                pass  # May not appear every time

            # Send the actual prompt
            os.write(master, (prompt + "\n").encode())

            # Read output
            output_lines = []
            start_time = time.time()
            timeout = 3600  # 1 hour safety timeout

            while time.time() - start_time < timeout:
                # Check if process is still running
                if process.poll() is not None:
                    log.info("Claude Code process exited")
                    break

                # Check if there's data to read (with 1 second timeout)
                ready, _, _ = select.select([master], [], [], 1.0)

                if ready:
                    try:
                        data = os.read(master, 4096)
                        if data:
                            text = data.decode('utf-8', errors='replace')
                            output_lines.append(text)
                            # Stream to console if requested
                            if stream_output:
                                print(text, end='', flush=True)
                        else:
                            break  # EOF
                    except OSError:
                        break

            # Terminate process if still running
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()

            # Combine output
            full_output = ''.join(output_lines)

            # Parse the interactive output to extract results and usage
            cleaned_output = self._clean_terminal_output(full_output)
            reached_max_turns = "reached max turns" in cleaned_output.lower() or "max turns" in cleaned_output.lower()
            usage = self._parse_interactive_usage(full_output)

            log.info(
                f"Token usage: {usage.total_tokens} tokens, "
                f"Estimated cost: ${usage.estimated_cost_usd:.4f}"
            )

            return cleaned_output, reached_max_turns, usage

        finally:
            os.close(master)

    def _clean_terminal_output(self, raw_output: str) -> str:
        """Remove ANSI escape codes and terminal control sequences from output."""
        # Remove ANSI escape codes
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        cleaned = ansi_escape.sub('', raw_output)

        # Remove common terminal control sequences
        cleaned = re.sub(r'\[\?[0-9]+[hl]', '', cleaned)  # Private mode set/reset
        cleaned = re.sub(r'\x0d', '', cleaned)  # Carriage returns

        return cleaned

    def _parse_interactive_usage(self, output: str) -> UsageStats:
        """
        Parse usage statistics from interactive terminal output.

        Claude Code may display usage info in various formats in interactive mode.
        We look for patterns like "X tokens" or usage summaries.
        """
        # Try to find token usage patterns in output
        # Example: "Used 15,234 tokens"
        token_match = re.search(r'(\d+[,\d]*)\s+tokens', output, re.IGNORECASE)
        if token_match:
            tokens_str = token_match.group(1).replace(',', '')
            try:
                total_tokens = int(tokens_str)
                # Estimate breakdown (80% input, 20% output as rough guess)
                return UsageStats(
                    input_tokens=int(total_tokens * 0.8),
                    output_tokens=int(total_tokens * 0.2),
                )
            except ValueError:
                pass

        # If we can't parse usage, return empty stats
        # (Agent will still work, just won't have accurate cost tracking)
        return UsageStats()
