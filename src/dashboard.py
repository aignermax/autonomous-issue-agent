#!/usr/bin/env python3
"""
Terminal Dashboard for Autonomous Issue Agent

Shows real-time status of:
- Agent state (polling, working, etc.)
- MCP servers (OpenViking, NetContextServer, dotnet-test-mcp)
- Current issue being worked on
- Recent issue history
- Token usage statistics

Usage:
    python src/dashboard.py
"""

import time
import os
import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass

from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich.text import Text
from rich.progress import Progress, SpinnerColumn, TextColumn


def tail_lines(path, max_lines: int, max_bytes: int = 262144) -> list:
    """Read at most `max_lines` from the end of `path` WITHOUT loading the
    whole file. Multi-MB agent logs previously made every dashboard refresh
    (5s cycle) re-read the full file, freezing the UI."""
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - max_bytes))
            data = f.read()
        text = data.decode("utf-8", errors="replace")
        lines = text.splitlines(keepends=True)
        # Drop a likely-partial first line when we started mid-file.
        if size > max_bytes and lines:
            lines = lines[1:]
        return lines[-max_lines:]
    except OSError:
        return []


@dataclass
class MCPServerStatus:
    """Status of an MCP server"""
    name: str
    is_running: bool
    pid: Optional[int]
    uptime: Optional[timedelta]
    port: Optional[int] = None


@dataclass
class AgentStatus:
    """Current agent status"""
    is_running: bool
    pid: Optional[int]
    current_issue: Optional[int]
    current_turn: Optional[int]
    max_turns: Optional[int]
    state: str  # "polling" | "working" | "reviewing" | "qa" | "idle" | "error" | "stopped"
    next_poll_in: Optional[timedelta]
    last_activity: Optional[timedelta]  # Time since last log entry
    cpu_percent: Optional[float]  # CPU usage percentage
    session_duration: Optional[timedelta]  # How long current session is running
    duplicate_agents: int = 0  # Number of duplicate agent processes detected
    issue_complexity: Optional[str] = None  # "REGULAR" or "COMPLEX"
    current_branch: Optional[str] = None  # Working branch (e.g., "agent/issue-110-...")
    current_pr: Optional[int] = None  # PR number when state is "reviewing" or "qa"


@dataclass
class IssueHistory:
    """History of processed issue"""
    number: int
    title: str
    completed: bool
    pr_url: Optional[str]
    total_tokens: int
    total_cost_usd: float
    session_count: int
    repository: str = ""  # Repository name (e.g., "akhe-ktop" for akhetonics-desktop)
    timestamp: Optional[datetime] = None
    duration: Optional[timedelta] = None


class DashboardMonitor:
    """Monitors agent and MCP server status"""

    def __init__(self, working_dir: Path):
        self.working_dir = working_dir
        self.sessions_dir = working_dir / ".sessions"
        self.agent_log = working_dir / "agent.log"
        self.console = Console()

    def get_process_info(self, pattern: str) -> Optional[Tuple[int, datetime]]:
        """Get PID and start time of a process matching pattern"""
        try:
            # Use LANG=C to get English dates for reliable parsing
            result = subprocess.run(
                ["ps", "-eo", "pid,lstart,cmd"],
                capture_output=True,
                text=True,
                timeout=2,
                env={**os.environ, 'LANG': 'C'}
            )

            for line in result.stdout.split('\n'):
                if pattern in line and 'grep' not in line:
                    parts = line.strip().split(None, 6)
                    if len(parts) >= 6:
                        pid = int(parts[0])
                        # Parse start time: "Mon Mar 24 07:29:41 2026"
                        start_str = ' '.join(parts[1:6])
                        try:
                            start_time = datetime.strptime(start_str, "%a %b %d %H:%M:%S %Y")
                            return (pid, start_time)
                        except Exception as e:
                            # Fallback: try to use etime instead
                            return (pid, datetime.now())
            return None
        except:
            return None

    def get_mcp_server_status(self) -> List[MCPServerStatus]:
        """Check status of all MCP servers"""
        servers = []

        # OpenViking
        info = self.get_process_info("openviking-server")
        if info:
            pid, start_time = info
            uptime = datetime.now() - start_time
            servers.append(MCPServerStatus("OpenViking", True, pid, uptime, 1933))
        else:
            servers.append(MCPServerStatus("OpenViking", False, None, None, 1933))

        # NetContextServer (look for the actual binary, not the dotnet run wrapper)
        info = self.get_process_info("bin/Debug/net8.0/NetContextServer")
        if not info:
            # Fallback to dotnet run command
            info = self.get_process_info("NetContextServer.csproj")
        if info:
            pid, start_time = info
            uptime = datetime.now() - start_time
            servers.append(MCPServerStatus("NetContextServer", True, pid, uptime, None))  # stdio, no port
        else:
            servers.append(MCPServerStatus("NetContextServer", False, None, None, None))

        # dotnet-test-mcp (harder to detect - it's spawned by Claude Code)
        info = self.get_process_info("dotnet-test-mcp")
        if info:
            pid, start_time = info
            uptime = datetime.now() - start_time
            servers.append(MCPServerStatus("dotnet-test-mcp", True, pid, uptime))
        else:
            servers.append(MCPServerStatus("dotnet-test-mcp", False, None, None))

        return servers

    def get_all_agent_processes(self) -> List[Tuple[int, datetime, str]]:
        """Get all running agent processes — tagged by role.

        Returns a list of (pid, start_time, role) where role is "coder" for
        the default `python main.py` invocation and "qa" when `--role qa`
        appears in the cmdline. Coder + QA run side-by-side and must not be
        treated as duplicates of each other.
        """
        agents = []
        try:
            import psutil

            for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
                try:
                    proc_info = proc.info
                    # Check if it's a Python process running main.py
                    if proc_info['name'] and 'python' in proc_info['name'].lower():
                        cmdline = proc_info.get('cmdline', [])
                        if cmdline and any('main.py' in arg for arg in cmdline):
                            pid = proc_info['pid']
                            # Convert create_time (timestamp) to datetime
                            start_time = datetime.fromtimestamp(proc_info['create_time'])
                            # Role = value after --role (qa, pr-feedback, ...);
                            # no flag = coder. Unknown roles must NOT fall back
                            # to "coder" — that once showed pr-feedback as a
                            # duplicate coder and the user killed the agents.
                            role = "coder"
                            for i, a in enumerate(cmdline):
                                if a == "--role" and i + 1 < len(cmdline):
                                    role = cmdline[i + 1]
                                    break
                            agents.append((pid, start_time, role))
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
        except ImportError:
            # Fallback to old method if psutil not available
            try:
                if sys.platform == 'win32':
                    # Windows fallback: Try tasklist
                    result = subprocess.run(
                        ["tasklist", "/FI", "IMAGENAME eq python.exe", "/V", "/FO", "CSV"],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    # This is less reliable, just mark as running if found
                    if 'python.exe' in result.stdout:
                        agents.append((0, datetime.now(), "coder"))  # Dummy entry
                else:
                    # Unix/Linux fallback
                    result = subprocess.run(
                        ["ps", "-eo", "pid,lstart,cmd"],
                        capture_output=True,
                        text=True,
                        timeout=2,
                        env={**os.environ, 'LANG': 'C'}
                    )
                    for line in result.stdout.split('\n'):
                        if 'main.py' in line and 'grep' not in line and 'python' in line:
                            parts = line.strip().split(None, 6)
                            if len(parts) >= 6:
                                pid = int(parts[0])
                                start_str = ' '.join(parts[1:6])
                                # Detect role from the rest of the cmdline
                                tail = parts[6] if len(parts) > 6 else ""
                                m_role = __import__("re").search(r"--role\s+(\S+)", tail)
                                role = m_role.group(1) if m_role else "coder"
                                try:
                                    start_time = datetime.strptime(start_str, "%a %b %d %H:%M:%S %Y")
                                    agents.append((pid, start_time, role))
                                except:
                                    agents.append((pid, datetime.now(), role))
            except:
                pass

        return agents

    def get_agent_status(self) -> AgentStatus:
        """Get current coder-agent status from logs and process.

        Only the "coder" role is considered here — the QA agent has its own
        status accessor (see get_qa_status) and shares neither process tree
        nor log file with the coder.
        """
        # Check if agent is running and detect duplicates within the coder role
        coder_agents = [a for a in self.get_all_agent_processes() if a[2] == "coder"]

        if not coder_agents:
            return AgentStatus(False, None, None, None, None, "stopped", None, None, None, None, 0, None, None, None)

        # Use the most recently started coder
        coder_agents.sort(key=lambda x: x[1], reverse=True)
        pid, start_time, _role = coder_agents[0]

        # Duplicate count: extra coders beyond the canonical one
        duplicate_count = len(coder_agents) - 1

        # Parse last lines of agent.log to determine state
        state = "polling"
        current_issue = None
        current_pr = None
        current_branch = None
        next_poll_in = None
        current_turn = None
        max_turns = None
        last_activity = None
        session_duration = None
        session_start_time = None
        issue_complexity = None

        if self.agent_log.exists():
            try:
                import re

                # Get last modification time of log file
                log_mtime = datetime.fromtimestamp(self.agent_log.stat().st_mtime)
                last_activity = datetime.now() - log_mtime

                # Read a generous tail. Worker phases can emit hundreds of
                # "Claude Code activity" lines, so a small window drops the
                # earlier phase markers (Found issue, Reviewer running, ...).
                lines = tail_lines(self.agent_log, 1000)

                # First pass: collect complexity + branch info from anywhere in
                # the window (these can come from before the current phase).
                for line in lines:
                    if "marked as COMPLEX" in line or "→ COMPLEX mode" in line:
                        issue_complexity = "COMPLEX"
                    elif "marked as REGULAR" in line or "→ REGULAR mode" in line:
                        issue_complexity = "REGULAR"

                    if "Creating new branch:" in line or "Checking out existing branch:" in line:
                        m = re.search(r'branch:\s+(agent/[^\s]+)', line)
                        if m:
                            current_branch = m.group(1)

                # Phase detection: walk from newest to oldest and pick the
                # first phase marker we see. Reviewer / QA logs come BEFORE
                # their own "Invoking Claude Code" line — so checking phase
                # markers first (and stopping at the first hit) yields the
                # actual current phase even though the generic Invoking line
                # is newer in the log.
                phase_re_qa = re.compile(
                    r'\[qa-review\] running on PR #(\d+)'
                    r'|\[qa\] verifying PR #(\d+)'
                )
                phase_re_review = re.compile(r'Reviewer running on PR #(\d+)')
                phase_re_worker = re.compile(r'Found issue #(\d+)')
                phase_re_sleep = re.compile(r'Sleeping (\d+)s')
                phase_re_ts = re.compile(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})')

                for line in reversed(lines):
                    if "ERROR" in line and "Failed processing issue" in line:
                        state = "error"
                        break

                    m = phase_re_qa.search(line)
                    if m:
                        state = "qa"
                        current_pr = int(m.group(1) or m.group(2))
                        ts = phase_re_ts.search(line)
                        if ts:
                            session_start_time = datetime.strptime(ts.group(1), "%Y-%m-%d %H:%M:%S")
                            session_duration = datetime.now() - session_start_time
                        break

                    m = phase_re_review.search(line)
                    if m:
                        state = "reviewing"
                        current_pr = int(m.group(1))
                        ts = phase_re_ts.search(line)
                        if ts:
                            session_start_time = datetime.strptime(ts.group(1), "%Y-%m-%d %H:%M:%S")
                            session_duration = datetime.now() - session_start_time
                        break

                    m = phase_re_worker.search(line)
                    if m:
                        state = "working"
                        current_issue = int(m.group(1))
                        ts = phase_re_ts.search(line)
                        if ts:
                            session_start_time = datetime.strptime(ts.group(1), "%Y-%m-%d %H:%M:%S")
                            session_duration = datetime.now() - session_start_time
                        break

                    m = phase_re_sleep.search(line)
                    if m:
                        state = "polling"
                        sleep_seconds = int(m.group(1))
                        ts = phase_re_ts.search(line)
                        if ts:
                            log_time = datetime.strptime(ts.group(1), "%Y-%m-%d %H:%M:%S")
                            elapsed = (datetime.now() - log_time).total_seconds()
                            remaining = max(0, sleep_seconds - elapsed)
                            next_poll_in = timedelta(seconds=remaining)
                        break

                # If we're past the worker phase (reviewing/qa), the original
                # issue number is still useful context — find it independently.
                if state in ("reviewing", "qa") and current_issue is None:
                    for l in reversed(lines):
                        m = re.search(r'Found issue #(\d+)', l)
                        if m:
                            current_issue = int(m.group(1))
                            break

            except Exception:
                pass

        # Get CPU usage - check claude child process if working, agent process if polling
        cpu_percent = None
        try:
            target_pid = pid  # Default to agent PID

            # If a Claude subprocess is active (worker/reviewer/qa), use its CPU
            if state in ("working", "reviewing", "qa"):
                # Find claude process that is a child of the agent process
                result = subprocess.run(
                    ["ps", "-eo", "pid,ppid,cmd"],
                    capture_output=True,
                    text=True,
                    timeout=1,
                    env={**os.environ, 'LANG': 'C'}
                )
                for line in result.stdout.split('\n'):
                    if 'claude' in line and str(pid) in line:
                        parts = line.strip().split(None, 2)
                        if len(parts) >= 2:
                            claude_pid = int(parts[0])
                            parent_pid = int(parts[1])
                            # Check if this claude's parent is our agent
                            if parent_pid == pid:
                                target_pid = claude_pid
                                break

            result = subprocess.run(
                ["ps", "-p", str(target_pid), "-o", "%cpu"],
                capture_output=True,
                text=True,
                timeout=1
            )
            lines = result.stdout.strip().split('\n')
            if len(lines) > 1:
                cpu_percent = float(lines[1].strip())
        except:
            pass

        return AgentStatus(
            True, pid, current_issue, current_turn, max_turns,
            state, next_poll_in, last_activity, cpu_percent, session_duration,
            duplicate_count, issue_complexity, current_branch, current_pr
        )

    def get_qa_status(self) -> dict:
        """Lightweight QA-agent status (process + heartbeat from qa-agent.log).

        Returned dict keys:
            is_running: bool
            pid: Optional[int]
            duplicates: int           — extra QA processes beyond the canonical one
            state: str                — "verifying" | "polling" | "stopped"
            current_pr: Optional[int] — PR being verified, when state=="verifying"
            last_activity: Optional[timedelta]
        """
        qa_agents = [a for a in self.get_all_agent_processes() if a[2] == "qa"]
        if not qa_agents:
            return {"is_running": False, "pid": None, "duplicates": 0,
                    "state": "stopped", "current_pr": None, "last_activity": None}

        qa_agents.sort(key=lambda x: x[1], reverse=True)
        pid, _start, _role = qa_agents[0]
        duplicates = len(qa_agents) - 1

        qa_log = self.working_dir / "qa-agent.log"
        state = "polling"
        current_pr = None
        last_activity = None
        if qa_log.exists():
            try:
                import re
                last_activity = datetime.now() - datetime.fromtimestamp(qa_log.stat().st_mtime)
                tail = tail_lines(qa_log, 200)
                # Walk newest → oldest, latch onto the first phase marker.
                pr_re = re.compile(r"\[qa\] verifying PR #(\d+)|\[qa-review\] running on PR #(\d+)")
                done_re = re.compile(r"\[qa\] PR #\d+ (PASSED|FAILED)|\[qa\] sleeping")
                for line in reversed(tail):
                    m = pr_re.search(line)
                    if m:
                        state = "verifying"
                        current_pr = int(m.group(1) or m.group(2))
                        break
                    if done_re.search(line):
                        state = "polling"
                        break
            except Exception:
                pass

        return {"is_running": True, "pid": pid, "duplicates": duplicates,
                "state": state, "current_pr": current_pr,
                "last_activity": last_activity}

    def _format_repo_name(self, repo_name: str) -> str:
        """Format repository name to first 4 chars + '-' + last 4 chars."""
        if not repo_name:
            return ""
        if len(repo_name) <= 9:  # If 9 or less chars, show full name
            return repo_name
        return f"{repo_name[:4]}-{repo_name[-4:]}"

    def get_issue_history(self, limit: int = 10) -> List[IssueHistory]:
        """Get recent issue history from agent.log"""
        history = {}  # Use dict to deduplicate by issue number

        # Parse agent.log for issue completions. Bounded tail — this runs on
        # every refresh and the log grows unbounded.
        if self.agent_log.exists():
            try:
                lines = tail_lines(self.agent_log, 5000, max_bytes=524288)

                import re
                for i, line in enumerate(lines):
                    # Look for issue completion
                    if "Issue #" in line and "done" in line:
                        # Extract issue number and timestamp
                        issue_match = re.search(r'#(\d+)', line)
                        timestamp_match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)

                        if issue_match:
                            issue_num = int(issue_match.group(1))
                            timestamp = None
                            if timestamp_match:
                                try:
                                    timestamp = datetime.strptime(timestamp_match.group(1), "%Y-%m-%d %H:%M:%S")
                                except:
                                    pass

                            # Look for token usage, PR info, and session start in nearby lines
                            tokens = 0
                            cost = 0.0
                            pr_url = None
                            session_start = None
                            duration = None

                            # Search backwards for token/PR/session info
                            repo_name = ""
                            for j in range(max(0, i-50), min(len(lines), i+5)):
                                token_match = re.search(r'Token usage: ([\d,]+) tokens.*cost: \$?([\d.]+)', lines[j])
                                if token_match:
                                    tokens = int(token_match.group(1).replace(',', ''))
                                    cost = float(token_match.group(2))

                                pr_match = re.search(r'https://github.com/[^/]+/([^/]+)/pull/(\d+)', lines[j])
                                if pr_match:
                                    pr_url = pr_match.group(0)
                                    repo_name = pr_match.group(1)  # Extract repo name from URL

                                # Look for session start to calculate duration
                                if f"issue #{issue_num}" in lines[j].lower() and "Starting new session" in lines[j]:
                                    start_match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', lines[j])
                                    if start_match and timestamp:
                                        try:
                                            session_start = datetime.strptime(start_match.group(1), "%Y-%m-%d %H:%M:%S")
                                            duration = timestamp - session_start
                                        except:
                                            pass

                            # Only add if we found token info or PR
                            if tokens > 0 or pr_url:
                                history[issue_num] = IssueHistory(
                                    number=issue_num,
                                    title="",
                                    completed=True,
                                    pr_url=pr_url,
                                    total_tokens=tokens,
                                    total_cost_usd=cost,
                                    session_count=1,
                                    repository=self._format_repo_name(repo_name),
                                    timestamp=timestamp,
                                    duration=duration
                                )
            except:
                pass

        # Also include ongoing sessions from session files
        if self.sessions_dir.exists():
            for session_file in self.sessions_dir.glob("issue-*.json"):
                try:
                    with open(session_file, 'r') as f:
                        data = json.load(f)

                    issue_num = data.get("issue_number", 0)
                    if issue_num and issue_num not in history:
                        history[issue_num] = IssueHistory(
                            number=issue_num,
                            title="",
                            completed=data.get("completed", False),
                            pr_url=data.get("pr_url"),
                            total_tokens=data.get("total_tokens", 0),
                            total_cost_usd=data.get("total_cost_usd", 0.0),
                            session_count=data.get("session_count", 0)
                        )
                except:
                    pass

        # Sort by timestamp descending (newest first)
        # Issues without timestamp go to the end
        result = sorted(
            history.values(),
            key=lambda x: x.timestamp if x.timestamp else datetime.min,
            reverse=True
        )
        return result[:limit]


class Dashboard:
    """Main dashboard display"""

    def __init__(self, working_dir: Path):
        self.monitor = DashboardMonitor(working_dir)
        self.console = Console()

    def create_header(self) -> Panel:
        """Create header panel"""
        text = Text()
        text.append("[AGENT] Autonomous Issue Agent - Dashboard\n", style="bold cyan")
        text.append(f"Working Directory: {self.monitor.working_dir}", style="dim")
        return Panel(text, border_style="cyan")

    def create_agent_panel(self, status: AgentStatus) -> Panel:
        """Create agent status panel (coder + QA roles)."""
        qa = self.monitor.get_qa_status()

        if not status.is_running and not qa["is_running"]:
            content = Text("[X] No agents running", style="bold red")
            return Panel(content, title="Agents Status", border_style="red")

        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Key", style="cyan")
        table.add_column("Value")

        if not status.is_running:
            table.add_row("Coder", Text("[X] not running", style="red"))
        else:
            # Status indicator
            if status.state == "working":
                status_text = Text("[>] Worker", style="bold yellow")
            elif status.state == "reviewing":
                status_text = Text("[R] Reviewer", style="bold magenta")
            elif status.state == "qa":
                status_text = Text("[Q] QA-fix", style="bold blue")
            elif status.state == "polling":
                status_text = Text("[+] Polling", style="bold green")
            elif status.state == "error":
                status_text = Text("[X] Error", style="bold red")
            else:
                status_text = Text("[ ] Idle", style="dim")

            table.add_row("Coder", status_text)
            table.add_row("  PID", str(status.pid))

            # Warning for duplicate coders
            if status.duplicate_agents > 0:
                warning_text = Text(f"WARNING: {status.duplicate_agents + 1} coder agents running!", style="bold red")
                table.add_row("  WARNING", warning_text)

            if status.current_issue:
                if status.issue_complexity:
                    complexity_style = "bold yellow" if status.issue_complexity == "COMPLEX" else "cyan"
                    issue_display = Text(f"#{status.current_issue} (")
                    issue_display.append(status.issue_complexity, style=complexity_style)
                    issue_display.append(")")
                else:
                    issue_display = f"#{status.current_issue}"
                table.add_row("  Current Issue", issue_display)
                if status.current_pr:
                    table.add_row("  Current PR", Text(f"#{status.current_pr}", style="magenta"))
                if status.current_branch:
                    table.add_row("  Working Branch", Text(status.current_branch, style="green"))
                if status.current_turn and status.max_turns:
                    table.add_row("  Progress", f"Turn {status.current_turn}/{status.max_turns}")
            else:
                table.add_row("  Current Issue", Text("None", style="dim"))
                if status.current_pr:
                    table.add_row("  Current PR", Text(f"#{status.current_pr}", style="magenta"))

        # Last Activity (Heartbeat!)
        if status.is_running and status.last_activity:
            seconds = int(status.last_activity.total_seconds())
            if seconds < 60:
                activity_str = f"{seconds}s ago"
                activity_color = "green"
            elif seconds < 300:  # < 5 minutes
                mins = seconds // 60
                activity_str = f"{mins}m {seconds % 60}s ago"
                activity_color = "green"
            elif seconds < 1800:  # < 30 minutes
                mins = seconds // 60
                activity_str = f"{mins}m ago"
                activity_color = "yellow"
            elif seconds < 3600:  # < 1 hour
                mins = seconds // 60
                activity_str = f"{mins}m ago [!]"
                activity_color = "yellow"
            else:  # > 1 hour
                hours = seconds // 3600
                mins = (seconds % 3600) // 60
                activity_str = f"{hours}h {mins}m ago [X]"
                activity_color = "red"

            table.add_row("  Last Log Entry", Text(activity_str, style=activity_color))

        # CPU Usage
        if status.is_running and status.cpu_percent is not None:
            if status.cpu_percent > 10:
                cpu_str = f"{status.cpu_percent:.1f}% (active)"
                cpu_color = "green"
            elif status.cpu_percent > 0.5:
                cpu_str = f"{status.cpu_percent:.1f}% (idle)"
                cpu_color = "yellow"
            else:
                # 0% CPU while a Claude subprocess should be running = hung?
                if status.state in ("working", "reviewing", "qa"):
                    cpu_str = f"{status.cpu_percent:.1f}% (hung?)"
                    cpu_color = "red"
                else:
                    cpu_str = f"{status.cpu_percent:.1f}%"
                    cpu_color = "dim"

            table.add_row("  CPU Usage", Text(cpu_str, style=cpu_color))

        # Session Duration (for any active Claude subprocess phase)
        if status.is_running and status.session_duration and status.state in ("working", "reviewing", "qa"):
            mins = int(status.session_duration.total_seconds() // 60)
            secs = int(status.session_duration.total_seconds() % 60)
            if mins < 60:
                duration_str = f"{mins}m {secs}s"
            else:
                hours = mins // 60
                mins = mins % 60
                duration_str = f"{hours}h {mins}m"

            table.add_row("  Session Time", duration_str)

        # Next Poll (for polling state)
        if status.is_running and status.next_poll_in:
            mins = int(status.next_poll_in.total_seconds() // 60)
            secs = int(status.next_poll_in.total_seconds() % 60)
            table.add_row("  Next Poll", f"{mins}m {secs}s")

        # ── QA Agent (separate process, separate log) ─────────────────
        if not qa["is_running"]:
            table.add_row("QA", Text("[X] not running", style="red"))
        else:
            if qa["state"] == "verifying":
                qa_state_text = Text("[V] Verifying", style="bold blue")
            elif qa["state"] == "polling":
                qa_state_text = Text("[+] Polling", style="bold green")
            else:
                qa_state_text = Text(qa["state"], style="dim")
            table.add_row("QA", qa_state_text)
            table.add_row("  PID", str(qa["pid"]))
            if qa["duplicates"] > 0:
                table.add_row("  WARNING",
                              Text(f"{qa['duplicates'] + 1} QA agents running!", style="bold red"))
            if qa["current_pr"]:
                table.add_row("  Current PR", Text(f"#{qa['current_pr']}", style="magenta"))
            if qa["last_activity"]:
                s = int(qa["last_activity"].total_seconds())
                if s < 60:
                    activity_str, activity_color = f"{s}s ago", "green"
                elif s < 1800:
                    activity_str, activity_color = f"{s // 60}m ago", "green" if s < 300 else "yellow"
                else:
                    activity_str, activity_color = f"{s // 60}m ago [!]", "red"
                table.add_row("  Last Log Entry", Text(activity_str, style=activity_color))

        # Border green only if both are healthy; red if both stopped; yellow otherwise
        if status.is_running and qa["is_running"]:
            border = "green"
        elif not status.is_running and not qa["is_running"]:
            border = "red"
        else:
            border = "yellow"
        return Panel(table, title="Agents Status (Coder + QA)", border_style=border)

    def create_config_panel(self) -> Panel:
        """Create configuration panel showing monitored repositories with branch info"""
        from dotenv import load_dotenv
        load_dotenv(self.monitor.working_dir / ".env")

        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Setting", style="cyan", width=18)
        table.add_column("Value", style="white")

        # Get repositories from environment
        repos_str = os.environ.get("AGENT_REPOS", "")
        if repos_str:
            repos = [r.strip() for r in repos_str.split(",") if r.strip()]
        else:
            # Fallback to single repo mode
            repos = [os.environ.get("AGENT_REPO", "Not configured")]

        # Check if agent is actively working to skip expensive API calls
        agent_status = self.monitor.get_agent_status()
        skip_api_calls = agent_status.is_running

        # Display repository list with branch info
        if len(repos) == 1:
            table.add_row("Repository:", repos[0])
            # Try to get working branch (dev if exists, otherwise default)
            if not skip_api_calls:
                branch_info = self._get_working_branch(repos[0])
                if branch_info:
                    table.add_row("  Base Branch:", f"[green]{branch_info}[/green]")
            else:
                # Use cached value when agent is working
                if hasattr(self, '_branch_cache') and repos[0] in self._branch_cache:
                    branch_info = self._branch_cache[repos[0]]
                    table.add_row("  Base Branch:", f"[green]{branch_info}[/green]")
        else:
            table.add_row("Repositories:", f"{len(repos)} repos")

            # Display repos one by one (immediate display, no waiting)
            for i, repo in enumerate(repos, 1):
                if not skip_api_calls:
                    # Fetch branch info synchronously but display immediately
                    branch_info = self._get_working_branch(repo)
                    if branch_info:
                        table.add_row(f"  [{i}]", f"{repo} [dim]→ [green]{branch_info}[/green][/dim]")
                    else:
                        table.add_row(f"  [{i}]", repo)
                else:
                    # Use cached value when agent is working
                    if hasattr(self, '_branch_cache') and repo in self._branch_cache:
                        branch_info = self._branch_cache[repo]
                        table.add_row(f"  [{i}]", f"{repo} [dim]→ [green]{branch_info}[/green][/dim]")
                    else:
                        table.add_row(f"  [{i}]", repo)

        # Show label configuration
        table.add_row("", "")  # Empty row for spacing
        activation_label = os.environ.get('AGENT_ISSUE_LABEL', 'agent-task')
        complexity_tag = os.environ.get('AGENT_COMPLEXITY_TAG', 'complex')
        table.add_row("Activation Label:", activation_label)
        table.add_row("Complexity Tag:", complexity_tag)
        table.add_row("Poll Interval:", f"{os.environ.get('AGENT_POLL_INTERVAL', '15')}s")

        return Panel(table, title="Configuration", border_style="cyan")

    def _get_working_branch(self, repo_name: str) -> Optional[str]:
        """Get working branch for a repository (dev if exists, otherwise default branch) (cached)"""
        # PERFORMANCE FIX: Skip slow git ls-remote and GitHub API calls
        # These were making dashboard refresh take 5+ seconds per repo!
        # The target branch info is not critical for dashboard display
        # User can see the actual working branch in Agent Status panel instead
        return None

    def create_history_panel(self, history: List[IssueHistory]) -> Panel:
        """Create issue history panel"""
        if not history:
            content = Text("No completed issues yet", style="dim")
            return Panel(content, title="Recent Issues", border_style="blue")

        table = Table(show_header=True, box=None)
        table.add_column("Issue", style="cyan", width=6)
        table.add_column("Repo", style="magenta", width=9)
        table.add_column("PR", style="green", width=6)
        table.add_column("OK", justify="center", width=3)
        table.add_column("Duration", justify="right", width=9)
        table.add_column("Tokens", justify="right", width=9)
        table.add_column("Cost", justify="right", width=7)
        table.add_column("When", justify="right", width=12)

        for issue in history:
            issue_str = f"#{issue.number}"

            # Extract PR number from URL
            pr_str = "-"
            if issue.pr_url:
                import re
                pr_match = re.search(r'/pull/(\d+)', issue.pr_url)
                if pr_match:
                    pr_str = f"#{pr_match.group(1)}"

            # Status indicator
            status = "YES" if issue.completed else "..."

            # Duration
            duration_str = "-"
            if issue.duration:
                total_mins = int(issue.duration.total_seconds() / 60)
                if total_mins < 60:
                    duration_str = f"{total_mins}m"
                else:
                    hours = total_mins // 60
                    mins = total_mins % 60
                    duration_str = f"{hours}h{mins}m"

            # Tokens and cost
            tokens_str = f"{issue.total_tokens:,}" if issue.total_tokens > 0 else "-"
            cost_str = f"${issue.total_cost_usd:.2f}" if issue.total_cost_usd > 0 else "-"

            # Timestamp (relative time)
            when_str = "-"
            if issue.timestamp:
                delta = datetime.now() - issue.timestamp
                hours_ago = int(delta.total_seconds() / 3600)
                if hours_ago < 1:
                    mins_ago = int(delta.total_seconds() / 60)
                    when_str = f"{mins_ago}m ago"
                elif hours_ago < 24:
                    when_str = f"{hours_ago}h ago"
                else:
                    days_ago = hours_ago // 24
                    when_str = f"{days_ago}d ago"

            table.add_row(
                issue_str,
                issue.repository if issue.repository else "-",
                pr_str,
                status,
                duration_str,
                tokens_str,
                cost_str,
                when_str
            )

        return Panel(table, title="Recent Issues", border_style="blue")

    def create_layout(self) -> Layout:
        """Create dashboard layout"""
        layout = Layout()

        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main"),
            Layout(name="footer", size=3)
        )

        layout["main"].split_row(
            Layout(name="left"),
            Layout(name="history")
        )

        layout["left"].split_column(
            Layout(name="agent"),
            Layout(name="mcp")
        )

        return layout

    def generate_display(self) -> Layout:
        """Generate the full dashboard display"""
        layout = self.create_layout()

        # Get current status
        agent_status = self.monitor.get_agent_status()
        history = self.monitor.get_issue_history(5)

        # Update layout
        layout["header"].update(self.create_header())
        layout["agent"].update(self.create_agent_panel(agent_status))
        layout["mcp"].update(self.create_config_panel())
        layout["history"].update(self.create_history_panel(history))

        # Footer
        footer_text = Text()
        footer_text.append("Press ", style="dim")
        footer_text.append("Ctrl+C", style="bold")
        footer_text.append(" to exit  •  Refreshing every 2 seconds", style="dim")
        layout["footer"].update(Panel(footer_text, border_style="dim"))

        return layout

    def run(self):
        """Run the dashboard"""
        # Dashboard refresh interval (configurable to avoid API rate limits when multiple instances run)
        refresh_interval = int(os.environ.get("DASHBOARD_REFRESH_INTERVAL", "5"))
        try:
            with Live(self.generate_display(), refresh_per_second=0.5, screen=True) as live:
                while True:
                    time.sleep(refresh_interval)
                    live.update(self.generate_display())
        except KeyboardInterrupt:
            self.console.print("\nDashboard stopped", style="yellow")


def main():
    """Main entry point"""
    working_dir = Path(__file__).parent.parent
    dashboard = Dashboard(working_dir)
    dashboard.run()


if __name__ == "__main__":
    main()
