#!/usr/bin/env python3
"""
MCP Benchmark Tool

Compares agent performance with and without MCP servers by running
the same issue twice in controlled conditions.

Usage:
    python benchmark_mcp.py --issue 252 --repo /path/to/Connect-A-PIC-Pro
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Optional
import shutil


class MCPBenchmark:
    """Benchmark tool for measuring MCP impact on token usage"""

    def __init__(self, issue_number: int, repo_path: Path):
        self.issue_number = issue_number
        self.repo_path = repo_path
        self.working_dir = Path(__file__).parent
        self.mcp_config = self.working_dir / ".mcp.json"
        self.mcp_backup = self.working_dir / ".mcp.json.backup"
        self.results = {
            "with_mcp": {},
            "without_mcp": {}
        }

    def backup_mcp_config(self):
        """Backup current MCP configuration"""
        if self.mcp_config.exists():
            shutil.copy(self.mcp_config, self.mcp_backup)
            print(f"✓ Backed up MCP config to {self.mcp_backup}")

    def restore_mcp_config(self):
        """Restore MCP configuration from backup"""
        if self.mcp_backup.exists():
            shutil.copy(self.mcp_backup, self.mcp_config)
            self.mcp_backup.unlink()
            print(f"✓ Restored MCP config")

    def disable_mcp(self):
        """Temporarily disable MCP by renaming config file"""
        if self.mcp_config.exists():
            self.mcp_config.rename(self.mcp_config.with_suffix('.json.disabled'))
            print(f"✓ Disabled MCP (renamed to .json.disabled)")

    def enable_mcp(self):
        """Re-enable MCP by restoring config file"""
        disabled_config = self.mcp_config.with_suffix('.json.disabled')
        if disabled_config.exists():
            disabled_config.rename(self.mcp_config)
            print(f"✓ Enabled MCP (restored .mcp.json)")

    def get_repo_state(self) -> str:
        """Get current git commit hash of the repo"""
        result = subprocess.run(
            ["git", "-C", str(self.repo_path), "rev-parse", "HEAD"],
            capture_output=True,
            text=True
        )
        return result.stdout.strip()

    def reset_repo_to_commit(self, commit: str):
        """Reset repo to a specific commit"""
        print(f"Resetting repo to commit {commit[:8]}...")
        subprocess.run(
            ["git", "-C", str(self.repo_path), "reset", "--hard", commit],
            check=True
        )
        # Clean any untracked files
        subprocess.run(
            ["git", "-C", str(self.repo_path), "clean", "-fd"],
            check=True
        )

    def find_issue_base_commit(self) -> Optional[str]:
        """Find the commit before the issue was solved"""
        print(f"Looking for the PR that fixed issue #{self.issue_number}...")

        # Try using gh CLI if available
        try:
            result = subprocess.run(
                ["gh", "pr", "list", "--state", "all", "--search", f"#{self.issue_number}", "--json", "mergeCommit,baseRefOid"],
                capture_output=True,
                text=True,
                cwd=self.repo_path
            )

            if result.returncode == 0:
                import json
                prs = json.loads(result.stdout)
                if prs:
                    # Use the base commit (before the PR was merged)
                    base_commit = prs[0].get("baseRefOid")
                    if base_commit:
                        print(f"✓ Found base commit from PR: {base_commit[:8]}")
                        return base_commit
        except FileNotFoundError:
            print("⚠ GitHub CLI (gh) not found - using simple HEAD^ fallback")

        # Fallback: Use HEAD^ (one commit before current)
        print("Using HEAD^ as base commit (commit before current HEAD)")
        result = subprocess.run(
            ["git", "-C", str(self.repo_path), "rev-parse", "HEAD^"],
            capture_output=True,
            text=True
        )
        return result.stdout.strip()

    def run_agent_on_issue(self, with_mcp: bool) -> Dict:
        """Run the agent on the issue and collect metrics"""
        run_type = "WITH MCP" if with_mcp else "WITHOUT MCP"
        print(f"\n{'='*60}")
        print(f"Running agent on Issue #{self.issue_number} {run_type}")
        print(f"{'='*60}\n")

        # Clear any existing session files
        sessions_dir = self.working_dir / ".sessions"
        if sessions_dir.exists():
            for session_file in sessions_dir.glob(f"issue-{self.issue_number}.json"):
                session_file.unlink()

        # Run the agent with --once flag to process only this issue
        start_time = time.time()

        # Use venv python to ensure dependencies are available
        venv_python = self.working_dir / "venv" / "bin" / "python3"
        if not venv_python.exists():
            venv_python = "python3"  # Fallback to system python

        result = subprocess.run(
            [str(venv_python), "main.py", "--once", str(self.issue_number)],
            capture_output=True,
            text=True,
            cwd=self.working_dir,
            timeout=3600  # 1 hour timeout
        )

        # Print output for debugging
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)

        duration = time.time() - start_time

        # Parse the session file to get token usage
        session_file = sessions_dir / f"issue-{self.issue_number}.json"
        tokens = 0
        cost = 0.0

        if session_file.exists():
            with open(session_file, 'r') as f:
                session_data = json.load(f)
                tokens = session_data.get("total_tokens", 0)
                cost = session_data.get("total_cost_usd", 0.0)

        # Also parse agent.log for token usage
        if tokens == 0:
            with open(self.working_dir / "agent.log", 'r') as f:
                lines = f.readlines()[-100:]  # Last 100 lines
                for line in reversed(lines):
                    if f"Issue #{self.issue_number}" in line and "Token usage:" in line:
                        import re
                        match = re.search(r'Token usage: ([\d,]+) tokens.*cost: \$?([\d.]+)', line)
                        if match:
                            tokens = int(match.group(1).replace(',', ''))
                            cost = float(match.group(2))
                            break

        return {
            "tokens": tokens,
            "cost_usd": cost,
            "duration_seconds": duration,
            "success": result.returncode == 0
        }

    def compare_results(self):
        """Compare results and print summary"""
        with_mcp = self.results["with_mcp"]
        without_mcp = self.results["without_mcp"]

        print(f"\n{'='*60}")
        print(f"BENCHMARK RESULTS - Issue #{self.issue_number}")
        print(f"{'='*60}\n")

        print(f"{'Metric':<30} {'Without MCP':<20} {'With MCP':<20} {'Savings':<15}")
        print("-" * 85)

        # Tokens
        tokens_diff = without_mcp["tokens"] - with_mcp["tokens"]
        tokens_pct = (tokens_diff / without_mcp["tokens"] * 100) if without_mcp["tokens"] > 0 else 0
        print(f"{'Tokens':<30} {without_mcp['tokens']:>15,}    {with_mcp['tokens']:>15,}    {tokens_pct:>6.1f}%")

        # Cost
        cost_diff = without_mcp["cost_usd"] - with_mcp["cost_usd"]
        cost_pct = (cost_diff / without_mcp["cost_usd"] * 100) if without_mcp["cost_usd"] > 0 else 0
        print(f"{'Cost (USD)':<30} ${without_mcp['cost_usd']:>14.4f}    ${with_mcp['cost_usd']:>14.4f}    {cost_pct:>6.1f}%")

        # Duration
        duration_diff = without_mcp["duration_seconds"] - with_mcp["duration_seconds"]
        without_mins = int(without_mcp["duration_seconds"] / 60)
        with_mins = int(with_mcp["duration_seconds"] / 60)
        print(f"{'Duration (minutes)':<30} {without_mins:>15}m    {with_mins:>15}m    {duration_diff/60:>6.1f}m")

        print("\n" + "="*60)
        if tokens_pct > 0:
            print(f"✅ MCP SAVED {tokens_pct:.1f}% tokens (${cost_diff:.4f} USD)")
        elif tokens_pct < 0:
            print(f"⚠ MCP INCREASED token usage by {abs(tokens_pct):.1f}%")
        else:
            print(f"➖ No significant difference")
        print("="*60 + "\n")

        # Save results to file
        results_file = self.working_dir / f"benchmark_issue_{self.issue_number}.json"
        with open(results_file, 'w') as f:
            json.dump({
                "issue": self.issue_number,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "results": self.results,
                "savings": {
                    "tokens": tokens_diff,
                    "tokens_pct": tokens_pct,
                    "cost_usd": cost_diff,
                    "cost_pct": cost_pct,
                    "duration_seconds": duration_diff
                }
            }, f, indent=2)
        print(f"📊 Results saved to {results_file}")

    def run_benchmark(self):
        """Run the full benchmark process"""
        print(f"\n🔬 MCP Benchmark Tool")
        print(f"Issue: #{self.issue_number}")
        print(f"Repo: {self.repo_path}\n")

        # Check if issue is closed
        print(f"Checking if issue #{self.issue_number} is closed...")
        from src.github_client import GitHubClient
        from src.config import Config
        import sys
        sys.path.insert(0, str(self.working_dir))

        try:
            config = Config()
            github = GitHubClient(config.repo_name)
            issue = github.repo.get_issue(self.issue_number)

            if issue.state == "open":
                print(f"\n⚠️  WARNING: Issue #{self.issue_number} is still OPEN!")
                print(f"Benchmarking works best on CLOSED issues because:")
                print(f"  1. We know the issue CAN be solved")
                print(f"  2. We can reset to the commit BEFORE the fix")
                print(f"  3. Both runs will solve the same problem")
                print(f"\nRecommended: Use a closed issue like #248, #244, or #243")
                print(f"\nContinue anyway? (y/n): ", end="")
                response = input().strip().lower()
                if response != 'y':
                    print("Benchmark cancelled.")
                    return
        except Exception as e:
            print(f"⚠ Could not check issue status: {e}")
            print("Continuing anyway...\n")

        try:
            # Backup MCP config
            self.backup_mcp_config()

            # Get repo state and find base commit
            current_commit = self.get_repo_state()
            print(f"Current repo commit: {current_commit[:8]}")

            base_commit = self.find_issue_base_commit()
            if not base_commit:
                print("⚠ Could not find base commit, using HEAD^")
                base_commit = current_commit + "^"

            # Run WITHOUT MCP
            print(f"\n{'='*60}")
            print(f"Phase 1: Running WITHOUT MCP")
            print(f"{'='*60}")
            self.disable_mcp()
            self.reset_repo_to_commit(base_commit)
            self.results["without_mcp"] = self.run_agent_on_issue(with_mcp=False)

            # Run WITH MCP
            print(f"\n{'='*60}")
            print(f"Phase 2: Running WITH MCP")
            print(f"{'='*60}")
            self.enable_mcp()
            self.reset_repo_to_commit(base_commit)
            self.results["with_mcp"] = self.run_agent_on_issue(with_mcp=True)

            # Compare results
            self.compare_results()

        except KeyboardInterrupt:
            print("\n\n⚠ Benchmark interrupted by user")
            sys.exit(1)
        except Exception as e:
            print(f"\n\n❌ Error during benchmark: {e}")
            raise
        finally:
            # Always restore MCP config and repo state
            self.enable_mcp()
            self.restore_mcp_config()
            self.reset_repo_to_commit(current_commit)
            print(f"✓ Restored repo to {current_commit[:8]}")


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark MCP impact on agent token usage"
    )
    parser.add_argument(
        "--issue",
        type=int,
        required=True,
        help="Issue number to benchmark"
    )
    parser.add_argument(
        "--repo",
        type=Path,
        required=True,
        help="Path to the Connect-A-PIC-Pro repository"
    )

    args = parser.parse_args()

    if not args.repo.exists():
        print(f"❌ Repository not found: {args.repo}")
        sys.exit(1)

    benchmark = MCPBenchmark(args.issue, args.repo)
    benchmark.run_benchmark()


if __name__ == "__main__":
    main()
