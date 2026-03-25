#!/usr/bin/env python3
"""
Interactive Dashboard for Autonomous Issue Agent

Adds keyboard controls and benchmark management.
Cross-platform compatible (Windows/Linux).

Usage:
    python src/dashboard_interactive.py
"""

import time
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

# Import existing dashboard components
from dashboard import DashboardMonitor, Dashboard as BaseDashboard


class InteractiveDashboard(BaseDashboard):
    """Interactive dashboard with keyboard controls"""

    def __init__(self, working_dir: Path):
        super().__init__(working_dir)
        self.auto_refresh = True

    def get_benchmark_status(self) -> Dict:
        """Check if benchmark is running and get status"""
        result = {
            "running": False,
            "phase": None,
            "issue": None
        }

        try:
            # Check for benchmark process (cross-platform)
            if sys.platform == 'win32':
                # Windows
                proc_result = subprocess.run(
                    ["tasklist", "/FI", "IMAGENAME eq python*"],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                # Simple check - if python is running, might be benchmark
                result["running"] = "python" in proc_result.stdout.lower()
            else:
                # Unix/Linux
                proc_result = subprocess.run(
                    ["ps", "aux"],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                for line in proc_result.stdout.split('\n'):
                    if 'benchmark_mcp.py' in line and 'grep' not in line:
                        result["running"] = True
                        # Extract issue number
                        if '--issue' in line:
                            parts = line.split('--issue')
                            if len(parts) > 1:
                                issue_num = parts[1].strip().split()[0]
                                result["issue"] = issue_num
                        break

            # Check agent.log for current phase
            if result["running"] and self.monitor.agent_log.exists():
                with open(self.monitor.agent_log, 'r') as f:
                    lines = f.readlines()[-100:]
                    for line in reversed(lines):
                        if "Using MCP config" in line:
                            result["phase"] = "WITH MCP (Phase 2)"
                            break
                        elif "Invoking Claude Code" in line:
                            # Check if MCP mentioned in recent lines
                            recent = ''.join(lines[-50:])
                            if "Using MCP" not in recent:
                                result["phase"] = "WITHOUT MCP (Phase 1)"
                            break

        except Exception:
            pass

        return result

    def create_benchmark_panel(self, status: Dict) -> Panel:
        """Create benchmark status panel"""
        if not status["running"]:
            content = Text("No benchmark running", style="dim")
            content.append("\n\nPress ", style="dim")
            content.append("[b]", style="bold green")
            content.append(" to start benchmark", style="dim")
        else:
            content = Text("🔬 Benchmark Running\n", style="bold yellow")
            if status["issue"]:
                content.append(f"Issue: #{status['issue']}\n", style="cyan")
            if status["phase"]:
                content.append(f"Phase: {status['phase']}\n", style="yellow")
            else:
                content.append("Phase: Starting...\n", style="dim")
            content.append("\n⏱️  Expected: 40-60 minutes total", style="dim")

        return Panel(content, title="🔬 Benchmark Status", border_style="yellow")

    def run(self):
        """Run interactive dashboard"""
        try:
            while True:
                # Clear screen (cross-platform)
                os.system('cls' if sys.platform == 'win32' else 'clear')

                # Generate main display
                self.console.print(self.create_header())
                self.console.print()

                # Get status
                agent_status = self.monitor.get_agent_status()
                mcp_servers = self.monitor.get_mcp_server_status()
                history = self.monitor.get_issue_history()
                benchmark_status = self.get_benchmark_status()

                # Display panels
                self.console.print(self.create_agent_panel(agent_status))
                self.console.print()
                self.console.print(self.create_mcp_panel(mcp_servers))
                self.console.print()
                self.console.print(self.create_benchmark_panel(benchmark_status))
                self.console.print()
                self.console.print(self.create_history_panel(history))

                # Show menu
                self.console.print("\n")
                menu = Text()
                menu.append("═" * 80 + "\n", style="dim")
                menu.append("Commands: ", style="bold cyan")
                menu.append("[r]", style="bold green")
                menu.append(" Refresh  ", style="dim")
                menu.append("[b]", style="bold green")
                menu.append(" Start Benchmark  ", style="dim")
                menu.append("[k]", style="bold green")
                menu.append(" Kill Agent  ", style="dim")
                menu.append("[l]", style="bold green")
                menu.append(" Show Logs  ", style="dim")
                menu.append("[a]", style="bold green")
                menu.append(" Auto-refresh: ", style="dim")
                menu.append("ON" if self.auto_refresh else "OFF", style="green" if self.auto_refresh else "red")
                menu.append("  ", style="dim")
                menu.append("[q]", style="bold red")
                menu.append(" Quit", style="dim")
                self.console.print(menu)
                self.console.print("═" * 80, style="dim")

                if self.auto_refresh:
                    self.console.print("\n⟳ Auto-refreshing in 5 seconds... (or press Enter for menu)", style="dim")

                    # Handle input with timeout (platform-specific)
                    choice = ""
                    if sys.platform != 'win32':
                        # Unix/Linux - use select for timeout
                        import select
                        rlist, _, _ = select.select([sys.stdin], [], [], 5.0)
                        if rlist:
                            choice = sys.stdin.readline().strip().lower()
                        else:
                            # Timeout - auto refresh
                            continue
                    else:
                        # Windows - simpler approach, just ask for input
                        try:
                            import msvcrt
                            start_time = time.time()
                            chars = []
                            while time.time() - start_time < 5.0:
                                if msvcrt.kbhit():
                                    ch = msvcrt.getch().decode('utf-8', errors='ignore')
                                    if ch == '\r':  # Enter
                                        break
                                    chars.append(ch)
                                time.sleep(0.1)
                            choice = ''.join(chars).strip().lower()
                            if not choice:
                                continue
                        except:
                            # Fallback - just sleep
                            time.sleep(5)
                            continue
                else:
                    choice = input("\nYour choice: ").strip().lower()

                # Handle command
                if choice == 'q':
                    break
                elif choice == 'r' or choice == '':
                    continue
                elif choice == 'a':
                    self.auto_refresh = not self.auto_refresh
                elif choice == 'b':
                    self.handle_benchmark()
                elif choice == 'k':
                    self.handle_kill_agent()
                elif choice == 'l':
                    self.handle_logs()

        except KeyboardInterrupt:
            self.console.print("\n\n👋 Dashboard stopped", style="yellow")

    def handle_benchmark(self):
        """Start benchmark"""
        self.console.print("\n🔬 Starting Benchmark", style="bold yellow")
        self.console.print("\nEnter issue number (or press Enter to cancel): ", style="cyan", end="")

        issue = input().strip()
        if issue and issue.isdigit():
            self.console.print(f"\n✓ Starting benchmark on issue #{issue}...", style="green")
            self.console.print("⏱️  This will take 40-60 minutes.", style="yellow")
            self.console.print("💡 You can close this dashboard and check back later.\n", style="dim")

            # Start benchmark in background
            python_cmd = "python" if sys.platform == 'win32' else "venv/bin/python3"
            subprocess.Popen(
                [python_cmd, "benchmark_mcp.py", "--issue", issue, "--repo", "./repo"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=self.monitor.working_dir
            )

            self.console.print("Press Enter to continue...", style="dim")
            input()

    def handle_kill_agent(self):
        """Kill the agent"""
        self.console.print("\n⚠️  Kill Agent Process?", style="bold yellow")
        self.console.print("This will stop the currently running agent.\n", style="dim")
        self.console.print("Confirm (y/n): ", style="yellow", end="")

        confirm = input().strip().lower()
        if confirm == 'y':
            if sys.platform == 'win32':
                subprocess.run(["taskkill", "/F", "/IM", "python.exe"], stderr=subprocess.DEVNULL)
            else:
                subprocess.run(["pkill", "-f", "python.*main.py"], stderr=subprocess.DEVNULL)

            self.console.print("\n✓ Agent killed", style="green")
            time.sleep(2)

    def handle_logs(self):
        """Show recent logs"""
        os.system('cls' if sys.platform == 'win32' else 'clear')
        self.console.print("\n📋 Recent Agent Logs (last 30 lines)\n", style="bold cyan")
        self.console.print("═" * 80 + "\n", style="dim")

        if self.monitor.agent_log.exists():
            with open(self.monitor.agent_log, 'r') as f:
                lines = f.readlines()[-30:]
                for line in lines:
                    print(line.rstrip())
        else:
            self.console.print("No log file found", style="red")

        self.console.print("\n" + "═" * 80, style="dim")
        self.console.print("\nPress Enter to continue...", style="dim")
        input()


def main():
    """Main entry point"""
    working_dir = Path(__file__).parent.parent
    dashboard = InteractiveDashboard(working_dir)
    dashboard.run()


if __name__ == "__main__":
    main()
