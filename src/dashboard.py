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
    state: str  # "polling", "working", "idle", "error"
    next_poll_in: Optional[timedelta]
    last_activity: Optional[timedelta]  # Time since last log entry
    cpu_percent: Optional[float]  # CPU usage percentage
    session_duration: Optional[timedelta]  # How long current session is running
    duplicate_agents: int = 0  # Number of duplicate agent processes detected


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

    def get_all_agent_processes(self) -> List[Tuple[int, datetime]]:
        """Get all running agent processes (detects duplicates) - cross-platform using psutil"""
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
                            agents.append((pid, start_time))
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
                        agents.append((0, datetime.now()))  # Dummy entry
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
                                try:
                                    start_time = datetime.strptime(start_str, "%a %b %d %H:%M:%S %Y")
                                    agents.append((pid, start_time))
                                except:
                                    agents.append((pid, datetime.now()))
            except:
                pass

        return agents

    def get_agent_status(self) -> AgentStatus:
        """Get current agent status from logs and process"""
        # Check if agent is running and detect duplicates
        all_agents = self.get_all_agent_processes()

        if not all_agents:
            return AgentStatus(False, None, None, None, None, "stopped", None, None, None, None, 0)

        # Use the most recently started agent
        all_agents.sort(key=lambda x: x[1], reverse=True)
        pid, start_time = all_agents[0]

        # Store duplicate count for later warning
        duplicate_count = len(all_agents) - 1

        # Parse last lines of agent.log to determine state
        state = "polling"
        current_issue = None
        next_poll_in = None
        current_turn = None
        max_turns = None
        last_activity = None
        session_duration = None
        session_start_time = None

        if self.agent_log.exists():
            try:
                # Get last modification time of log file
                log_mtime = datetime.fromtimestamp(self.agent_log.stat().st_mtime)
                last_activity = datetime.now() - log_mtime

                with open(self.agent_log, 'r') as f:
                    lines = f.readlines()[-50:]  # Last 50 lines

                for line in reversed(lines):
                    # Check for sleeping (polling state)
                    if "Sleeping" in line and "s ..." in line:
                        import re
                        match = re.search(r'Sleeping (\d+)s', line)
                        if match:
                            sleep_seconds = int(match.group(1))
                            timestamp_match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                            if timestamp_match:
                                log_time = datetime.strptime(timestamp_match.group(1), "%Y-%m-%d %H:%M:%S")
                                elapsed = (datetime.now() - log_time).total_seconds()
                                remaining = max(0, sleep_seconds - elapsed)
                                next_poll_in = timedelta(seconds=remaining)
                        state = "polling"
                        break

                    # Check for working on issue
                    if "Invoking Claude Code" in line:
                        state = "working"
                        # Extract session start time
                        import re
                        timestamp_match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                        if timestamp_match:
                            session_start_time = datetime.strptime(timestamp_match.group(1), "%Y-%m-%d %H:%M:%S")
                            session_duration = datetime.now() - session_start_time

                        for l in reversed(lines):
                            if "Found issue #" in l:
                                match = re.search(r'issue #(\d+)', l)
                                if match:
                                    current_issue = int(match.group(1))
                                    break
                        break

                    # Check for errors
                    if "ERROR" in line and "Failed processing issue" in line:
                        state = "error"
                        break

            except Exception as e:
                pass

        # Get CPU usage - check claude child process if working, agent process if polling
        cpu_percent = None
        try:
            target_pid = pid  # Default to agent PID

            # If working on an issue, find claude child process of THIS agent
            if state == "working":
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
            duplicate_count
        )

    def get_issue_history(self, limit: int = 10) -> List[IssueHistory]:
        """Get recent issue history from agent.log"""
        history = {}  # Use dict to deduplicate by issue number

        # Parse agent.log for issue completions
        if self.agent_log.exists():
            try:
                with open(self.agent_log, 'r') as f:
                    lines = f.readlines()

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
                            for j in range(max(0, i-50), min(len(lines), i+5)):
                                token_match = re.search(r'Token usage: ([\d,]+) tokens.*cost: \$?([\d.]+)', lines[j])
                                if token_match:
                                    tokens = int(token_match.group(1).replace(',', ''))
                                    cost = float(token_match.group(2))

                                pr_match = re.search(r'https://github.com/[^/]+/[^/]+/pull/(\d+)', lines[j])
                                if pr_match:
                                    pr_url = pr_match.group(0)

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

        # Sort by issue number descending
        result = sorted(history.values(), key=lambda x: x.number, reverse=True)
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
        """Create agent status panel"""
        if not status.is_running:
            content = Text("[X] Agent Not Running", style="bold red")
            return Panel(content, title="Agent Status", border_style="red")

        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Key", style="cyan")
        table.add_column("Value")

        # Status indicator
        if status.state == "working":
            status_text = Text("[>] Working", style="bold yellow")
        elif status.state == "polling":
            status_text = Text("[+] Polling", style="bold green")
        elif status.state == "error":
            status_text = Text("[X] Error", style="bold red")
        else:
            status_text = Text("[ ] Idle", style="dim")

        table.add_row("Status", status_text)
        table.add_row("PID", str(status.pid))

        # Warning for duplicate agents
        if status.duplicate_agents > 0:
            warning_text = Text(f"WARNING: {status.duplicate_agents + 1} agents running!", style="bold red")
            table.add_row("WARNING", warning_text)

        if status.current_issue:
            table.add_row("Current Issue", f"#{status.current_issue}")
            if status.current_turn and status.max_turns:
                table.add_row("Progress", f"Turn {status.current_turn}/{status.max_turns}")
        else:
            table.add_row("Current Issue", Text("None", style="dim"))

        # Last Activity (Heartbeat!)
        if status.last_activity:
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

            table.add_row("Last Log Entry", Text(activity_str, style=activity_color))

        # CPU Usage
        if status.cpu_percent is not None:
            if status.cpu_percent > 10:
                cpu_str = f"{status.cpu_percent:.1f}% (active)"
                cpu_color = "green"
            elif status.cpu_percent > 0.5:
                cpu_str = f"{status.cpu_percent:.1f}% (idle)"
                cpu_color = "yellow"
            else:
                # 0% CPU while working = hung?
                if status.state == "working":
                    cpu_str = f"{status.cpu_percent:.1f}% (hung?)"
                    cpu_color = "red"
                else:
                    cpu_str = f"{status.cpu_percent:.1f}%"
                    cpu_color = "dim"

            table.add_row("CPU Usage", Text(cpu_str, style=cpu_color))

        # Session Duration (for working state)
        if status.session_duration and status.state == "working":
            mins = int(status.session_duration.total_seconds() // 60)
            secs = int(status.session_duration.total_seconds() % 60)
            if mins < 60:
                duration_str = f"{mins}m {secs}s"
            else:
                hours = mins // 60
                mins = mins % 60
                duration_str = f"{hours}h {mins}m"

            table.add_row("Session Time", duration_str)

        # Next Poll (for polling state)
        if status.next_poll_in:
            mins = int(status.next_poll_in.total_seconds() // 60)
            secs = int(status.next_poll_in.total_seconds() % 60)
            table.add_row("Next Poll", f"{mins}m {secs}s")

        return Panel(table, title="Agent Status", border_style="green" if status.is_running else "red")

    def create_config_panel(self) -> Panel:
        """Create configuration panel showing monitored repositories"""
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

        # Display repository list
        if len(repos) == 1:
            table.add_row("Repository:", repos[0])
        else:
            table.add_row("Repositories:", f"{len(repos)} repos")
            for i, repo in enumerate(repos, 1):
                table.add_row(f"  [{i}]", repo)

        # Show label filter
        table.add_row("", "")  # Empty row for spacing
        table.add_row("Label Filter:", "agent-task")

        return Panel(table, title="Configuration", border_style="cyan")

    def create_history_panel(self, history: List[IssueHistory]) -> Panel:
        """Create issue history panel"""
        if not history:
            content = Text("No completed issues yet", style="dim")
            return Panel(content, title="Recent Issues", border_style="blue")

        table = Table(show_header=True, box=None)
        table.add_column("Issue", style="cyan", width=6)
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
        try:
            with Live(self.generate_display(), refresh_per_second=0.5, screen=True) as live:
                while True:
                    time.sleep(2)
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
