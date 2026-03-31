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

    def _get_working_branch(self, repo_name: str) -> str:
        """
        Get the working branch for a repository (dev if exists, otherwise default branch).

        Args:
            repo_name: Repository in format "owner/repo"

        Returns:
            Working branch name
        """
        try:
            import subprocess
            # Check if dev branch exists on remote
            result = subprocess.run(
                ["git", "ls-remote", "--heads", f"https://github.com/{repo_name}.git", "dev"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                return "dev"

            # Fall back to default branch from GitHub API
            import sys
            sys.path.insert(0, str(self.monitor.working_dir / "src"))
            from github_client import GitHubClient
            gh = GitHubClient(repo_name)
            return gh.default_branch
        except Exception:
            return "main"  # Ultimate fallback

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
                self.console.print(self.create_config_panel())
                self.console.print()
                self.console.print(self.create_history_panel(history))

                # Show menu
                self.console.print("\n")
                menu = Text()
                menu.append("=" * 80 + "\n", style="dim")
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
                menu.append("[c]", style="bold green")
                menu.append(" Config  ", style="dim")
                menu.append("[q]", style="bold red")
                menu.append(" Quit", style="dim")
                self.console.print(menu)
                self.console.print("=" * 80, style="dim")

                if self.auto_refresh:
                    self.console.print("\n[>] Auto-refreshing in 5 seconds... (or press Enter for menu)", style="dim")

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
                elif choice == 'c':
                    self.handle_config()

        except KeyboardInterrupt:
            self.console.print("\n\nDashboard stopped", style="yellow")

    def handle_start_agent(self):
        """Start the autonomous agent"""
        self.console.print("\n[AGENT] Starting Autonomous Agent", style="bold yellow")
        self.console.print("\nThis will start the agent in continuous mode,", style="dim")
        self.console.print("automatically working on open issues.\n", style="dim")
        self.console.print("Confirm? (y/n): ", style="cyan", end="")

        confirm = input().strip().lower()
        if confirm == 'y':
            self.console.print("\n[+] Starting agent...", style="green")
            self.console.print("TIP: Use [s] Stream Logs to watch progress!", style="dim")
            self.console.print("TIP: Use [k] Kill Agent to stop it.\n", style="dim")

            # Start agent in background (fully detached)
            # Check if wsl-venv exists (WSL), otherwise use venv (Linux native)
            if os.path.exists("wsl-venv/bin/python3"):
                python_cmd = "wsl-venv/bin/python3"
            elif sys.platform == 'win32':
                python_cmd = "python"
            else:
                python_cmd = "venv/bin/python3"

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
            self.console.print("[OK] Agent started in background!", style="green")
            self.console.print("\nPress Enter to continue...", style="dim")
            input()


    def handle_kill_agent(self):
        """Kill the agent"""
        self.console.print("\n[WARNING] Kill Agent Process?", style="bold yellow")
        self.console.print("This will stop the currently running agent.\n", style="dim")
        self.console.print("Confirm (y/n): ", style="yellow", end="")

        confirm = input().strip().lower()
        if confirm == 'y':
            if sys.platform == 'win32':
                subprocess.run(["taskkill", "/F", "/IM", "python.exe"], stderr=subprocess.DEVNULL)
            else:
                subprocess.run(["pkill", "-f", "python.*main.py"], stderr=subprocess.DEVNULL)

            self.console.print("\n[+] Agent killed", style="green")
            time.sleep(2)

    def handle_logs(self):
        """Show recent logs"""
        os.system('cls' if sys.platform == 'win32' else 'clear')
        self.console.print("\n[LOGS] Recent Agent Logs (last 30 lines)\n", style="bold cyan")
        self.console.print("=" * 80 + "\n", style="dim")

        if self.monitor.agent_log.exists():
            with open(self.monitor.agent_log, 'r') as f:
                lines = f.readlines()[-30:]
                for line in lines:
                    print(line.rstrip())
        else:
            self.console.print("No log file found", style="red")

        self.console.print("\n" + "=" * 80, style="dim")
        self.console.print("\nPress Enter to continue...", style="dim")
        input()

    def handle_stream_logs(self):
        """Stream logs in real-time (tail -f)"""
        os.system('cls' if sys.platform == 'win32' else 'clear')
        self.console.print("\n[STREAM] Agent Logs (Ctrl+C to stop)\n", style="bold cyan")
        self.console.print("=" * 80 + "\n", style="dim")

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
            self.console.print("\n\n[+] Stopped streaming", style="green")

    def handle_config(self):
        """Interactive configuration management"""
        from dotenv import load_dotenv, set_key

        env_file = self.monitor.working_dir / ".env"
        load_dotenv(env_file)

        while True:
            os.system('cls' if sys.platform == 'win32' else 'clear')
            self.console.print("\n[CONFIG] Repository Configuration\n", style="bold cyan")
            self.console.print("=" * 80, style="dim")

            # Get current repos
            repos_str = os.environ.get("AGENT_REPOS", "")
            if repos_str:
                repos = [r.strip() for r in repos_str.split(",") if r.strip()]
            else:
                repos = [os.environ.get("AGENT_REPO", "")]
                repos = [r for r in repos if r]

            # Display current configuration with branch info
            if repos:
                self.console.print("\nCurrent repositories:", style="bold white")
                for i, repo in enumerate(repos, 1):
                    # Try to get working branch info
                    try:
                        branch = self._get_working_branch(repo)
                        self.console.print(f"  [{i}] {repo} [dim]→ [green]{branch}[/green][/dim]")
                    except Exception as e:
                        self.console.print(f"  [{i}] {repo} [dim](unable to fetch branch: {str(e)[:30]}...)[/dim]", style="yellow")
            else:
                self.console.print("\n[!] No repositories configured!", style="yellow")

            # Show menu
            self.console.print("\n" + "=" * 80, style="dim")
            self.console.print("\nOptions:", style="bold white")
            self.console.print("  [a] Add repository")
            self.console.print("  [r] Remove repository")
            self.console.print("  [e] Edit .env file directly")
            self.console.print("  [b] Back to dashboard")

            choice = input("\nYour choice: ").strip().lower()

            if choice == 'b':
                break
            elif choice == 'a':
                self._handle_add_repo(env_file)
            elif choice == 'r':
                self._handle_remove_repo(env_file, repos)
            elif choice == 'e':
                self.console.print(f"\n[>] Opening .env in editor...", style="cyan")
                editor = os.environ.get('EDITOR', 'nano')
                subprocess.run([editor, str(env_file)])
                # Reload after edit
                load_dotenv(env_file, override=True)
                os.environ.clear()
                load_dotenv(env_file)

    def _handle_add_repo(self, env_file: Path):
        """Add a new repository"""
        self.console.print("\n[ADD] Add Repository\n", style="bold cyan")
        self.console.print("Enter repository in format: owner/repo")
        self.console.print("Example: aignermax/Connect-A-PIC-Pro\n")

        repo = input("Repository: ").strip()

        if not repo or '/' not in repo:
            self.console.print("\n[!] Invalid format. Use: owner/repo", style="red")
            time.sleep(2)
            return

        # Verify repository exists
        self.console.print(f"\n[>] Verifying repository access...", style="cyan")
        try:
            import sys
            sys.path.insert(0, str(self.monitor.working_dir / "src"))
            from github_client import GitHubClient
            gh = GitHubClient(repo)
            branch = gh.default_branch
            self.console.print(f"[+] Found repository! Default branch: [green]{branch}[/green]", style="green")
        except Exception as e:
            self.console.print(f"\n[!] Error accessing repository: {str(e)}", style="red")
            self.console.print("    Check repository name and GitHub token permissions", style="dim")
            time.sleep(3)
            return

        # Add to .env
        current_repos = os.environ.get("AGENT_REPOS", os.environ.get("AGENT_REPO", ""))
        if current_repos:
            new_repos = f"{current_repos},{repo}"
        else:
            new_repos = repo

        set_key(env_file, "AGENT_REPOS", new_repos)

        # Update environment
        os.environ["AGENT_REPOS"] = new_repos

        self.console.print(f"\n[+] Added {repo} to monitored repositories", style="green")
        time.sleep(2)

    def _handle_remove_repo(self, env_file: Path, repos: list):
        """Remove a repository"""
        if not repos:
            self.console.print("\n[!] No repositories to remove", style="red")
            time.sleep(2)
            return

        self.console.print("\n[REMOVE] Remove Repository\n", style="bold cyan")
        self.console.print("Enter number of repository to remove (1-{})".format(len(repos)))

        try:
            choice = int(input("Number: ").strip())
            if choice < 1 or choice > len(repos):
                raise ValueError()

            removed_repo = repos[choice - 1]
            repos.pop(choice - 1)

            # Update .env
            if repos:
                set_key(env_file, "AGENT_REPOS", ",".join(repos))
                os.environ["AGENT_REPOS"] = ",".join(repos)
            else:
                set_key(env_file, "AGENT_REPOS", "")
                os.environ["AGENT_REPOS"] = ""

            self.console.print(f"\n[+] Removed {removed_repo}", style="green")
            time.sleep(2)

        except (ValueError, EOFError):
            self.console.print("\n[!] Invalid choice", style="red")
            time.sleep(2)


def main():
    """Main entry point"""
    working_dir = Path(__file__).parent.parent
    dashboard = InteractiveDashboard(working_dir)
    dashboard.run()


if __name__ == "__main__":
    main()
