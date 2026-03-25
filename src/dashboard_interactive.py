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
                history = self.monitor.get_issue_history()

                # Display panels
                self.console.print(self.create_agent_panel(agent_status))
                self.console.print()
                self.console.print(self.create_history_panel(history))

                # Show menu
                self.console.print("\n")
                menu = Text()
                menu.append("═" * 80 + "\n", style="dim")
                menu.append("Commands: ", style="bold cyan")
                menu.append("[r]", style="bold green")
                menu.append(" Refresh  ", style="dim")
                menu.append("[g]", style="bold green")
                menu.append(" Start Agent  ", style="dim")
                menu.append("[k]", style="bold green")
                menu.append(" Kill Agent  ", style="dim")
                menu.append("[l]", style="bold green")
                menu.append(" Show Logs  ", style="dim")
                menu.append("[s]", style="bold green")
                menu.append(" Stream Logs  ", style="dim")
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
                elif choice == 'g':
                    self.handle_start_agent()
                elif choice == 'k':
                    self.handle_kill_agent()
                elif choice == 'l':
                    self.handle_logs()
                elif choice == 's':
                    self.handle_stream_logs()

        except KeyboardInterrupt:
            self.console.print("\n\n👋 Dashboard stopped", style="yellow")

    def handle_start_agent(self):
        """Start the autonomous agent"""
        self.console.print("\n🤖 Starting Autonomous Agent", style="bold yellow")
        self.console.print("\nThis will start the agent in continuous mode,", style="dim")
        self.console.print("automatically working on open issues.\n", style="dim")
        self.console.print("Confirm? (y/n): ", style="cyan", end="")

        confirm = input().strip().lower()
        if confirm == 'y':
            self.console.print("\n✓ Starting agent...", style="green")
            self.console.print("💡 Use [s] Stream Logs to watch progress!", style="dim")
            self.console.print("💡 Use [k] Kill Agent to stop it.\n", style="dim")

            # Start agent in background (fully detached)
            python_cmd = "python" if sys.platform == 'win32' else "venv/bin/python3"

            if sys.platform == 'win32':
                # Windows: use CREATE_NEW_PROCESS_GROUP
                subprocess.Popen(
                    [python_cmd, "main.py"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    cwd=self.monitor.working_dir,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                )
            else:
                # Unix: use start_new_session for full detachment
                subprocess.Popen(
                    [python_cmd, "main.py"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    cwd=self.monitor.working_dir,
                    start_new_session=True
                )

            time.sleep(2)
            self.console.print("✅ Agent started in background!", style="green")
            self.console.print("\nPress Enter to continue...", style="dim")
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

    def handle_stream_logs(self):
        """Stream logs in real-time (tail -f)"""
        os.system('cls' if sys.platform == 'win32' else 'clear')
        self.console.print("\n📡 Streaming Agent Logs (Ctrl+C to stop)\n", style="bold cyan")
        self.console.print("═" * 80 + "\n", style="dim")

        if not self.monitor.agent_log.exists():
            self.console.print("No log file found", style="red")
            time.sleep(2)
            return

        # Use tail -f on Unix, or manual polling on Windows
        try:
            if sys.platform != 'win32':
                subprocess.run(["tail", "-f", str(self.monitor.agent_log)])
            else:
                # Windows: manual tail -f implementation
                with open(self.monitor.agent_log, 'r') as f:
                    f.seek(0, 2)  # Go to EOF
                    while True:
                        line = f.readline()
                        if line:
                            print(line.rstrip())
                        else:
                            time.sleep(0.1)
        except KeyboardInterrupt:
            self.console.print("\n\n✓ Stopped streaming", style="green")
            time.sleep(1)


def main():
    """Main entry point"""
    working_dir = Path(__file__).parent.parent
    dashboard = InteractiveDashboard(working_dir)
    dashboard.run()


if __name__ == "__main__":
    main()
