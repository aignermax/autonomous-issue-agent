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

    def get_agent_status(self) -> AgentStatus:
        """Get current agent status from logs and process"""
        # Check if agent is running
        info = self.get_process_info("main.py")
        if not info:
            return AgentStatus(False, None, None, None, None, "stopped", None, None, None, None)

        pid, start_time = info

        # Parse last lines of agent.log FIRST to determine state
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
            state, next_poll_in, last_activity, cpu_percent, session_duration
        )

    def get_issue_history(self, limit: int = 5) -> List[IssueHistory]:
        """Get recent issue history from session files"""
        history = []

        if not self.sessions_dir.exists():
            return history

        for session_file in self.sessions_dir.glob("issue-*.json"):
            try:
                with open(session_file, 'r') as f:
                    data = json.load(f)

                history.append(IssueHistory(
                    number=data.get("issue_number", 0),
                    title="",  # Title not stored in session files
                    completed=data.get("completed", False),
                    pr_url=data.get("pr_url"),
                    total_tokens=data.get("total_tokens", 0),
                    total_cost_usd=data.get("total_cost_usd", 0.0),
                    session_count=data.get("session_count", 0)
                ))
            except:
                pass

        # Sort by issue number descending
        history.sort(key=lambda x: x.number, reverse=True)
        return history[:limit]


class Dashboard:
    """Main dashboard display"""

    def __init__(self, working_dir: Path):
        self.monitor = DashboardMonitor(working_dir)
        self.console = Console()

    def create_header(self) -> Panel:
        """Create header panel"""
        text = Text()
        text.append("🤖 Autonomous Issue Agent - Dashboard\n", style="bold cyan")
        text.append(f"Working Directory: {self.monitor.working_dir}", style="dim")
        return Panel(text, border_style="cyan")

    def create_agent_panel(self, status: AgentStatus) -> Panel:
        """Create agent status panel"""
        if not status.is_running:
            content = Text("❌ Agent Not Running", style="bold red")
            return Panel(content, title="Agent Status", border_style="red")

        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Key", style="cyan")
        table.add_column("Value")

        # Status indicator
        if status.state == "working":
            status_text = Text("🔧 Working", style="bold yellow")
        elif status.state == "polling":
            status_text = Text("🟢 Polling", style="bold green")
        elif status.state == "error":
            status_text = Text("❌ Error", style="bold red")
        else:
            status_text = Text("⚪ Idle", style="dim")

        table.add_row("Status", status_text)
        table.add_row("PID", str(status.pid))

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
                activity_str = f"{mins}m ago ⚠️"
                activity_color = "yellow"
            else:  # > 1 hour
                hours = seconds // 3600
                mins = (seconds % 3600) // 60
                activity_str = f"{hours}h {mins}m ago ❌"
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

    def create_mcp_panel(self, servers: List[MCPServerStatus]) -> Panel:
        """Create MCP servers status panel"""
        table = Table(show_header=True, box=None)
        table.add_column("Server", style="cyan")
        table.add_column("Status", justify="center")
        table.add_column("PID", justify="right")
        table.add_column("Uptime", justify="right")
        table.add_column("Port", justify="right")

        for server in servers:
            if server.is_running:
                status = Text("🟢", style="green")
                pid_str = str(server.pid) if server.pid else "-"

                if server.uptime:
                    hours = int(server.uptime.total_seconds() // 3600)
                    mins = int((server.uptime.total_seconds() % 3600) // 60)
                    if hours > 0:
                        uptime_str = f"{hours}h {mins}m"
                    else:
                        uptime_str = f"{mins}m"
                else:
                    uptime_str = "-"

                # Show port or communication method
                if server.port:
                    port_str = str(server.port)
                elif server.name in ["NetContextServer", "dotnet-test-mcp"]:
                    port_str = "stdio"
                else:
                    port_str = "-"
            else:
                # Special handling for dotnet-test-mcp (on-demand tool, not a server)
                if server.name == "dotnet-test-mcp":
                    status = Text("⚪", style="dim")
                    pid_str = "on-demand"
                    uptime_str = "CLI tool"
                    port_str = "-"
                else:
                    status = Text("🔴", style="red")
                    pid_str = "-"
                    uptime_str = "-"
                    port_str = str(server.port) if server.port else "-"

            table.add_row(server.name, status, pid_str, uptime_str, port_str)

        return Panel(table, title="MCP Servers", border_style="cyan")

    def create_history_panel(self, history: List[IssueHistory]) -> Panel:
        """Create issue history panel"""
        if not history:
            content = Text("No completed issues yet", style="dim")
            return Panel(content, title="Recent Issues", border_style="blue")

        table = Table(show_header=True, box=None)
        table.add_column("#", style="cyan", width=5)
        table.add_column("Status", justify="center", width=6)
        table.add_column("Tokens", justify="right", width=10)
        table.add_column("Cost", justify="right", width=8)
        table.add_column("Sessions", justify="right", width=8)

        for issue in history:
            status = "✅" if issue.completed else "⏳"
            tokens_str = f"{issue.total_tokens:,}" if issue.total_tokens > 0 else "-"
            cost_str = f"${issue.total_cost_usd:.2f}" if issue.total_cost_usd > 0 else "-"
            sessions_str = str(issue.session_count) if issue.session_count > 0 else "-"

            table.add_row(
                f"#{issue.number}",
                status,
                tokens_str,
                cost_str,
                sessions_str
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
        mcp_servers = self.monitor.get_mcp_server_status()
        history = self.monitor.get_issue_history(5)

        # Update layout
        layout["header"].update(self.create_header())
        layout["agent"].update(self.create_agent_panel(agent_status))
        layout["mcp"].update(self.create_mcp_panel(mcp_servers))
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
            self.console.print("\n👋 Dashboard stopped", style="yellow")


def main():
    """Main entry point"""
    working_dir = Path(__file__).parent.parent
    dashboard = Dashboard(working_dir)
    dashboard.run()


if __name__ == "__main__":
    main()
