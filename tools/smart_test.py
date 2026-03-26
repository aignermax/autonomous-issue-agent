#!/usr/bin/env python3
"""
Smart Test Tool for Autonomous Agent

Runs dotnet tests intelligently with filtered output.
Agent calls this instead of raw 'dotnet test' to avoid overwhelming output.

Usage:
    python3 smart_test.py                           # Run all tests, show summary
    python3 smart_test.py ParameterSweeper          # Run only tests matching "ParameterSweeper"
    python3 smart_test.py --file ParameterSweeperTests.cs   # Run specific test file
    python3 smart_test.py --verbose                 # Show all test output
"""

import sys
import subprocess
import re
from pathlib import Path

# Determine repo root - support two scenarios:
# 1. Tool in autonomous-issue-agent/tools/ → repo is ../repo/
# 2. Tool in Connect-A-PIC-Pro/tools/ → repo is ../

def get_repo_root() -> Path:
    """Find repository root dynamically."""
    tool_dir = Path(__file__).parent
    parent_dir = tool_dir.parent

    # First check if parent directory looks like the actual project (has .sln or .csproj)
    has_solution = list(parent_dir.glob("*.sln"))
    has_project = (parent_dir / "Connect-A-Pic-Core").exists()

    if has_solution or has_project:
        # We're directly in the project! (tools/ is inside Connect-A-PIC-Pro/)
        return parent_dir
    # Otherwise check if we're in autonomous-issue-agent setup (has separate repo/ directory)
    elif (parent_dir / "repo").exists():
        return parent_dir / "repo"
    # Fallback: use current working directory
    else:
        return Path.cwd()

REPO_ROOT = get_repo_root()


def run_dotnet_test(filter_pattern: str = None, verbose: bool = False) -> tuple[bool, str]:
    """
    Run dotnet test with optional filtering.

    Returns:
        (success, output_summary)
    """
    cmd = ["dotnet", "test"]

    if filter_pattern:
        # Use dotnet test --filter to run only matching tests
        cmd.extend(["--filter", f"FullyQualifiedName~{filter_pattern}"])

    # Always show minimal output unless verbose
    if not verbose:
        cmd.append("--logger:console;verbosity=minimal")

    print(f"🧪 Running: {' '.join(cmd)}", file=sys.stderr)
    print(f"📁 Working directory: {REPO_ROOT}", file=sys.stderr)
    print("", file=sys.stderr)

    result = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=300  # 5 minute timeout
    )

    return result.returncode == 0, result.stdout, result.stderr


def parse_test_summary(stdout: str) -> dict:
    """Parse test summary from dotnet output (English or German)."""
    summary = {
        "total": 0,
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "duration": "N/A"
    }

    # English: "Passed!  - Failed:     0, Passed:   123, Skipped:     0, Total:   123, Duration: 2.3s"
    match = re.search(r'(Passed|Failed)!\s*-\s*Failed:\s*(\d+),\s*Passed:\s*(\d+),\s*Skipped:\s*(\d+),\s*Total:\s*(\d+),\s*Duration:\s*([^,\n]+)', stdout)

    if match:
        summary["failed"] = int(match.group(2))
        summary["passed"] = int(match.group(3))
        summary["skipped"] = int(match.group(4))
        summary["total"] = int(match.group(5))
        summary["duration"] = match.group(6).strip()
        return summary

    # German: "Bestanden!   : Fehler:     0, erfolgreich:     7, übersprungen:     0, gesamt:     7, Dauer: 253 ms"
    match = re.search(r'(Bestanden|Fehler)!\s*:\s*Fehler:\s*(\d+),\s*erfolgreich:\s*(\d+),\s*übersprungen:\s*(\d+),\s*gesamt:\s*(\d+),\s*Dauer:\s*([^-\n]+)', stdout)

    if match:
        summary["failed"] = int(match.group(2))
        summary["passed"] = int(match.group(3))
        summary["skipped"] = int(match.group(4))
        summary["total"] = int(match.group(5))
        summary["duration"] = match.group(6).strip()

    return summary


def extract_failed_tests(stdout: str, stderr: str) -> list[dict]:
    """Extract information about failed tests."""
    failed = []

    # Look for test failure details in output
    # Format: "X [FAIL] Namespace.ClassName.TestMethod"
    for line in (stdout + stderr).split('\n'):
        if '[FAIL]' in line or 'Failed' in line and '::' in line:
            # Try to extract test name
            match = re.search(r'\[FAIL\]\s+(.+)', line)
            if match:
                test_name = match.group(1).strip()
                failed.append({"name": test_name, "line": line})

    return failed


def format_output(success: bool, summary: dict, failed_tests: list[dict], verbose: bool, stdout: str, stderr: str) -> str:
    """Format test output for agent consumption."""
    output = []

    # Header
    if success:
        output.append("✅ TESTS PASSED")
    else:
        output.append("❌ TESTS FAILED")

    output.append("")

    # Summary
    output.append("## Summary")
    output.append(f"- Total:   {summary['total']} tests")
    output.append(f"- Passed:  {summary['passed']} ✅")
    output.append(f"- Failed:  {summary['failed']} ❌")
    output.append(f"- Skipped: {summary['skipped']} ⏭️")
    output.append(f"- Duration: {summary['duration']}")
    output.append("")

    # Failed tests details
    if failed_tests:
        output.append("## Failed Tests")
        for test in failed_tests:
            output.append(f"- {test['name']}")
        output.append("")

    # Show full output if verbose or if there are failures
    if verbose or failed_tests:
        output.append("## Detailed Output")
        output.append("")
        output.append("### stdout:")
        output.append(stdout)
        output.append("")
        output.append("### stderr:")
        output.append(stderr)

    return '\n'.join(output)


def main():
    """Main entry point."""
    args = sys.argv[1:]

    # Parse arguments
    filter_pattern = None
    verbose = False

    if "--help" in args or "-h" in args:
        print(__doc__)
        sys.exit(0)

    if "--verbose" in args or "-v" in args:
        verbose = True
        args = [a for a in args if a not in ["--verbose", "-v"]]

    if "--file" in args:
        idx = args.index("--file")
        if idx + 1 < len(args):
            file_name = args[idx + 1]
            # Convert file name to test class pattern
            # "ParameterSweeperTests.cs" -> "ParameterSweeperTests"
            filter_pattern = Path(file_name).stem
            args = args[:idx] + args[idx+2:]

    # Remaining args are filter pattern
    if args and not filter_pattern:
        filter_pattern = args[0]

    # Run tests
    try:
        success, stdout, stderr = run_dotnet_test(filter_pattern, verbose)
    except subprocess.TimeoutExpired:
        print("❌ Tests timed out after 5 minutes!", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error running tests: {e}", file=sys.stderr)
        sys.exit(1)

    # Parse results
    summary = parse_test_summary(stdout + stderr)
    failed_tests = extract_failed_tests(stdout, stderr)

    # Format and output
    output = format_output(success, summary, failed_tests, verbose, stdout, stderr)
    print(output)

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
