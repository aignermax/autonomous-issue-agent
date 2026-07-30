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
    current_repo: Optional[str] = None  # Repo the coder is working in (owner/name)


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
        # One refresh renders several panels, each needing the process list.
        # Scanning all processes is expensive under WSL — cache briefly so a
        # single refresh does exactly one scan.
        self._proc_cache: list = []
        self._proc_cache_at: float = 0.0

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

        Cached ~1.5s: one dashboard refresh calls this from several panels.
        """
        now = time.time()
        if self._proc_cache and now - self._proc_cache_at < 1.5:
            return self._proc_cache

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

        self._proc_cache = agents
        self._proc_cache_at = now
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
        current_repo = None
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

                    # Coder-only line ("[qa]"/"[pr-feedback]" prefix theirs);
                    # forward pass → ends at the most recent repo visited.
                    m = re.search(r'\] Checking repository: (\S+)', line)
                    if m and "[qa]" not in line and "[pr-feedback]" not in line:
                        current_repo = m.group(1)

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
                phase_re_worker = re.compile(r'Found issue #(\d+)(?: in (\S+):)?')
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
                        if m.group(2):
                            current_repo = m.group(2)
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
                        m = re.search(r'Found issue #(\d+)(?: in (\S+):)?', l)
                        if m:
                            current_issue = int(m.group(1))
                            if m.group(2):
                                current_repo = m.group(2)
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
            duplicate_count, issue_complexity, current_branch, current_pr,
            current_repo
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

    def get_pr_feedback_status(self) -> dict:
        """PR-feedback-agent status (process + heartbeat from pr-feedback-agent.log).

        Same shape as get_qa_status; state is "working" (handling a marker
        comment, current_pr set) or "polling".
        """
        fb_agents = [a for a in self.get_all_agent_processes() if a[2] == "pr-feedback"]
        if not fb_agents:
            return {"is_running": False, "pid": None, "duplicates": 0,
                    "state": "stopped", "current_pr": None, "last_activity": None}

        fb_agents.sort(key=lambda x: x[1], reverse=True)
        pid, _start, _role = fb_agents[0]
        duplicates = len(fb_agents) - 1

        fb_log = self.working_dir / "pr-feedback-agent.log"
        state = "polling"
        current_pr = None
        last_activity = None
        if fb_log.exists():
            try:
                import re
                last_activity = datetime.now() - datetime.fromtimestamp(fb_log.stat().st_mtime)
                tail = tail_lines(fb_log, 200)
                working_re = re.compile(r"\[pr-feedback\] PR #(\d+): handling comment")
                done_re = re.compile(r"\[pr-feedback\] (sleeping|nothing to do)")
                # Newest → oldest: worker-run output has no [pr-feedback]
                # prefix, so the latest phase marker decides.
                for line in reversed(tail):
                    m = working_re.search(line)
                    if m:
                        state = "working"
                        current_pr = int(m.group(1))
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
        """Recent issue history: persisted JSONL first, log parsing as fallback."""
        history = {}  # Use dict to deduplicate by issue number

        # Authoritative source: .sessions/issue-history.jsonl, written by the
        # agent at completion time. Survives dashboard restarts and log
        # rotation — the log tail below only covers the recent past.
        try:
            from history import read_issue_history
        except ImportError:
            from .history import read_issue_history
        for rec in read_issue_history(self.sessions_dir, limit=limit):
            try:
                ts = None
                if rec.get("timestamp"):
                    ts = datetime.strptime(rec["timestamp"], "%Y-%m-%d %H:%M:%S")
                dur = None
                if rec.get("duration_sec") is not None:
                    dur = timedelta(seconds=int(rec["duration_sec"]))
                history[int(rec["number"])] = IssueHistory(
                    number=int(rec["number"]),
                    title=rec.get("title", ""),
                    completed=bool(rec.get("completed")),
                    pr_url=rec.get("pr_url"),
                    total_tokens=int(rec.get("total_tokens", 0)),
                    total_cost_usd=float(rec.get("total_cost_usd", 0.0)),
                    session_count=int(rec.get("session_count", 0)),
                    repository=self._format_repo_name(
                        (rec.get("repository") or "").split("/")[-1]),
                    timestamp=ts,
                    duration=dur,
                )
            except (KeyError, ValueError, TypeError):
                continue

        # Fallback for the pre-JSONL era: parse the recent log tail. Never
        # overwrites a persisted record — and once the JSONL alone fills the
        # panel, skip log archaeology entirely (it's the expensive path).
        if len(history) < limit and self.agent_log.exists():
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

                            # Only add if we found token info or PR — and no
                            # persisted record exists (JSONL is authoritative).
                            if (tokens > 0 or pr_url) and issue_num not in history:
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
        """Compact columnar status: one column per role (coder/QA/PR-feedback)."""
        qa = self.monitor.get_qa_status()
        fb = self.monitor.get_pr_feedback_status()

        if not status.is_running and not qa["is_running"] and not fb["is_running"]:
            content = Text("[X] No agents running", style="bold red")
            return Panel(content, title="Agents Status", border_style="red")

        table = Table(show_header=True, box=None, padding=(0, 2))
        table.add_column("", style="cyan", width=10)
        table.add_column("Coder", overflow="fold")
        table.add_column("QA", overflow="fold")
        table.add_column("PR-Feedback", overflow="fold")

        def coder_state() -> Text:
            if not status.is_running:
                return Text("[X] not running", style="red")
            mapping = {
                "working": ("[>] Worker", "bold yellow"),
                "reviewing": ("[R] Reviewer", "bold magenta"),
                "qa": ("[Q] QA-fix", "bold blue"),
                "polling": ("[+] Polling", "bold green"),
                "error": ("[X] Error", "bold red"),
            }
            label, style = mapping.get(status.state, ("[ ] Idle", "dim"))
            return Text(label, style=style)

        def role_state(info: dict, working_label: str) -> Text:
            if not info["is_running"]:
                return Text("[X] not running", style="red")
            if info["state"] == working_label:
                return Text("[W] " + working_label.capitalize(), style="bold blue")
            if info["state"] == "polling":
                return Text("[+] Polling", style="bold green")
            return Text(info["state"], style="dim")

        def age(delta) -> Text:
            if delta is None:
                return Text("-", style="dim")
            s = int(delta.total_seconds())
            if s < 60:
                return Text(f"{s}s ago", style="green")
            if s < 1800:
                return Text(f"{s // 60}m ago", style="green" if s < 300 else "yellow")
            return Text(f"{s // 60}m ago [!]", style="red")

        table.add_row("Status", coder_state(),
                      role_state(qa, "verifying"), role_state(fb, "working"))
        table.add_row("PID",
                      str(status.pid) if status.pid else "-",
                      str(qa["pid"]) if qa["pid"] else "-",
                      str(fb["pid"]) if fb["pid"] else "-")

        # What each role is working on (issue/PR, repo, branch — multiline).
        # current_pr shows even without an issue: during a long review/qa
        # phase the 'Found issue' line can scroll out of the log tail.
        coder_work = Text()
        if status.current_issue:
            coder_work.append(f"#{status.current_issue}")
            if status.issue_complexity:
                style = "bold yellow" if status.issue_complexity == "COMPLEX" else "cyan"
                coder_work.append(" (")
                coder_work.append(status.issue_complexity, style=style)
                coder_work.append(")")
        if status.current_pr:
            if coder_work.plain:
                coder_work.append("  ")
            coder_work.append(f"PR #{status.current_pr}", style="magenta")
        if status.current_repo:
            coder_work.append(("\n" if coder_work.plain else "") + status.current_repo, style="magenta")
        if status.current_branch:
            coder_work.append("\n" + status.current_branch, style="green")
        if not coder_work.plain:
            coder_work = Text("-", style="dim")
        qa_work = (Text(f"PR #{qa['current_pr']}", style="magenta")
                   if qa["current_pr"] else Text("-", style="dim"))
        fb_work = (Text(f"PR #{fb['current_pr']}", style="magenta")
                   if fb["current_pr"] else Text("-", style="dim"))
        table.add_row("Work", coder_work, qa_work, fb_work)

        table.add_row("Last Log", age(status.last_activity),
                      age(qa["last_activity"]), age(fb["last_activity"]))

        # Coder extras: session duration, CPU (with hang detection), next poll.
        extras = Text()
        if status.is_running and status.session_duration:
            s = int(status.session_duration.total_seconds())
            dur = f"{s // 3600}h{(s % 3600) // 60}m" if s >= 3600 else f"{s // 60}m{s % 60}s"
            extras.append(f"session {dur}")
        if status.is_running and status.cpu_percent is not None:
            if extras.plain:
                extras.append("  ·  ")
            # In an active phase, ~0% CPU means the subprocess is likely hung.
            if status.state in ("working", "reviewing", "qa") and status.cpu_percent < 1.0:
                extras.append(f"CPU {status.cpu_percent:.1f}% (hung?)", style="bold red")
            else:
                extras.append(f"CPU {status.cpu_percent:.1f}%")
        if status.is_running and status.next_poll_in:
            secs = int(status.next_poll_in.total_seconds())
            if extras.plain:
                extras.append("  ·  ")
            extras.append(f"next poll {secs}s")
        if extras.plain:
            table.add_row("", extras, "", "")

        warn = []
        if status.duplicate_agents > 0:
            warn.append(f"{status.duplicate_agents + 1} coder agents running!")
        if qa["duplicates"] > 0:
            warn.append(f"{qa['duplicates'] + 1} QA agents running!")
        if fb["duplicates"] > 0:
            warn.append(f"{fb['duplicates'] + 1} pr-feedback agents running!")
        if warn:
            table.add_row("WARNING", Text(" / ".join(warn), style="bold red"), "", "")

        all_up = status.is_running and qa["is_running"] and fb["is_running"]
        none_up = not (status.is_running or qa["is_running"] or fb["is_running"])
        border = "green" if all_up else ("red" if none_up else "yellow")
        return Panel(table, title="Agents Status (Coder + QA + PR-Feedback)", border_style=border)

    @staticmethod
    def _env_int(name: str, default: int) -> int:
        """os.environ int with a safe fallback — a bad value must not crash a render."""
        try:
            return int(os.environ.get(name, str(default)))
        except (TypeError, ValueError):
            return default

    def create_config_panel(self) -> Panel:
        """Configuration panel: org sweep, external repos, labels, intervals."""
        # .env is static config — load once per dashboard lifetime, not per
        # 2s refresh.
        if not getattr(self, "_dotenv_loaded", False):
            from dotenv import load_dotenv
            load_dotenv(self.monitor.working_dir / ".env")
            self._dotenv_loaded = True

        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Setting", style="cyan", width=18)
        table.add_column("Value", style="white")

        # External (manual) repos only — org repos are covered by the sweep.
        # Honor legacy single-repo AGENT_REPO too (config.py still does).
        repos_str = os.environ.get("AGENT_REPOS", "")
        repos = [r.strip() for r in repos_str.split(",") if r.strip()]
        if not repos:
            single = os.environ.get("AGENT_REPO", "").strip()
            if single:
                repos = [single]
        org = os.environ.get("AGENT_DISCOVERY_ORG", "Akhetonics")
        interval = self._env_int("AGENT_DISCOVERY_INTERVAL_SEC", 120)

        if org:
            sweep_info = f"[green]{org}[/green] [dim](auto-swept every {interval}s"
            countdown = self._next_sweep_countdown(interval)
            if countdown is not None:
                sweep_info += f", next in {countdown}s"
            sweep_info += ")[/dim]"
            table.add_row("Org:", sweep_info)
        table.add_row("External repos:", ", ".join(repos) if repos else "[dim](none)[/dim]")

        labels = " · ".join([
            os.environ.get('AGENT_ISSUE_LABEL', 'agent-task'),
            os.environ.get('AGENT_COMPLEXITY_TAG', 'complex'),
            os.environ.get('AGENT_ECO_TAG', 'eco'),
        ])
        table.add_row("Labels:", labels)
        table.add_row(
            "Intervals:",
            f"repo poll {os.environ.get('AGENT_POLL_INTERVAL', '15')}s · "
            f"org sweep {interval}s")

        # Auto-discovered org repos. READ-ONLY: active_repos never persists,
        # so the dashboard cannot race the coder's registry writes.
        try:
            try:
                from repo_discovery import RepoRegistry
            except ImportError:
                from .repo_discovery import RepoRegistry
            expiry_days = self._env_int("AGENT_DISCOVERY_EXPIRY_DAYS", 8)
            registry = RepoRegistry(self.monitor.sessions_dir)
            auto_repos = registry.active_repos(expiry_days)
            if auto_repos:
                table.add_row("Auto-discovered:", f"{len(auto_repos)} repo(s)")
                for repo in auto_repos:
                    days_left = ""
                    last_seen_str = registry.last_seen(repo)
                    if last_seen_str:
                        try:
                            last_seen = datetime.strptime(last_seen_str, "%Y-%m-%d %H:%M:%S")
                            remaining = expiry_days - (datetime.now() - last_seen).days
                            days_left = f" [dim](expires in {max(0, remaining)}d)[/dim]"
                        except ValueError:
                            pass
                    table.add_row("", f"[green]{repo}[/green]{days_left}")
        except Exception:
            pass

        return Panel(table, title="Configuration", border_style="cyan")

    def _next_sweep_countdown(self, interval_sec: int) -> Optional[int]:
        """Seconds until the coder's next org sweep (from the hints file ts).

        Returns None when the hints are missing OR stale (coder stopped /
        sweep broken) so the panel shows no misleading 'next in 0s' forever.
        """
        try:
            import json as _json
            try:
                from repo_discovery import HINTS_FILENAME
            except ImportError:
                from .repo_discovery import HINTS_FILENAME
            data = _json.loads(
                (self.monitor.sessions_dir / HINTS_FILENAME).read_text(encoding="utf-8"))
            last = datetime.strptime(data["ts"], "%Y-%m-%d %H:%M:%S")
            elapsed = (datetime.now() - last).total_seconds()
            # A sweep should have run within one interval; if the last one is
            # older than 2x, the coder isn't sweeping — hide the countdown.
            if elapsed > interval_sec * 2:
                return None
            return max(0, int(interval_sec - elapsed))
        except Exception:
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
