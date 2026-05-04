"""
Prompt templates for Claude Code execution.
"""

CONTINUATION_TEMPLATE = """Continuing work on issue #{issue_number}: {issue_title}

## Progress So Far

Session {session_number} - Total turns used: {total_turns}
Branch: {branch_name}{branch_note}

{recent_notes}

## Your Task

Continue where you left off:
1. Check build (use build_errors.py):
   ```bash
   python3 {tools_dir}/build_errors.py --suggest-fixes
   ```
2. Run tests (use smart_test.py):
   ```bash
   python3 {tools_dir}/smart_test.py
   ```
3. Continue implementing (use semantic_search.py to find examples)
4. Fix any failures
5. Re-read issue title:
   - "Investigate"/"Test"/"Verify" → ONLY tests, NO UI
   - "Add feature"/"Implement UI" → Full stack

**Keep trying!** Use tools/ folder tools:
- build_errors.py, semantic_search.py, smart_test.py
- find_symbol.py (find definitions/usages), dotnet_deps.py (check packages)

Read CLAUDE.md for conventions."""

INITIAL_TEMPLATE = """Implement issue #{issue_number}: {issue_title}
{branch_note}

## CRITICAL: Read CLAUDE.md First
The repo has `CLAUDE.md` with full architecture guidelines. **Read it immediately.**

## Issue Type
- **Test/Investigation** ("test", "verify", "investigate") → ONLY tests, NO UI
- **User feature** ("add feature", "implement UI") → Full stack (Core + ViewModel + View + Tests)
- **Bugfix** → Fix the bug, add regression test

## Architecture (for NEW features)
1. Core logic (Connect-A-Pic-Core/)
2. ViewModel ([ObservableProperty], [RelayCommand])
3. View/AXAML (MainWindow.axaml)
4. Tests (UnitTests/)

Max 250 lines/file, SOLID principles, XML docs, no magic numbers.

## Before Finishing
1. **Build** (use build analyzer for cleaner output):
   ```bash
   python3 {tools_dir}/build_errors.py --suggest-fixes
   ```
2. **Test** (use smart test tool):
   ```bash
   python3 {tools_dir}/smart_test.py
   ```
3. Fix all errors/warnings
4. **Keep trying until it works**

## Issue #{issue_number}: {issue_title}

{issue_body}

## YOUR TASK

1. Read `CLAUDE.md` for architecture + `CODEBASE_MAP.md` for overview
2. **ALWAYS use semantic search first** (better than glob/grep):
   ```bash
   python3 {tools_dir}/semantic_search.py "your natural language query"
   ```
   Examples: "ViewModel for analysis", "test files for bounding box", "where is GDS export?"
3. Find similar features to reuse patterns
4. Implement:
   - NEW FEATURES → Core + ViewModel + View + Tests
   - TESTS/BUGFIXES → Tests or fix only (NO UI)
5. **ALWAYS use smart test tool** (NOT `dotnet test` directly):
   ```bash
   python3 {tools_dir}/smart_test.py [filter]
   ```
   Shows clean summary instead of 1000+ test results!
6. Build/test iteratively, fix errors immediately
7. **Keep trying until tests pass!**
8. **BEFORE final commit:** Review your own changes:
   - Check for code quality issues
   - Look for potential bugs or edge cases
   - Verify tests cover main scenarios
   - Fix any issues you find BEFORE committing

## 🚀 IMPORTANT: Always use tools/ folder tools!
- **build_errors.py** - Filtered build output + fix suggestions (instead of `dotnet build`)
- **semantic_search.py** - AI code search (instead of grep)
- **smart_test.py** - Filtered test output (instead of `dotnet test`)
- **find_symbol.py** - Find class/method definitions + usages (when refactoring/implementing)
- **dotnet_deps.py** - Check NuGet packages (when debugging references/conflicts)

These tools save 500-5000 tokens per use! Use them frequently!
"""


def build_prompt(issue, state=None, tools_dir: str = "tools") -> str:
    """
    Build the implementation prompt for Claude Code.

    Args:
        issue: GitHub Issue object
        state: Optional session state for continuation
        tools_dir: Absolute path to python-dev-tools directory

    Returns:
        Formatted prompt string
    """
    is_feature_branch = state and not state.branch_name.startswith("agent/issue-")
    branch_note = (
        f"\n**IMPORTANT:** You are working on existing branch: `{state.branch_name}`\n"
        f"Do NOT create a new branch. All work must be on this branch."
        if is_feature_branch
        else ""
    )

    if state and state.session_count > 0:
        recent_notes = "\n".join(state.notes[-5:]) if state.notes else "No notes yet."
        return CONTINUATION_TEMPLATE.format(
            issue_number=issue.number,
            issue_title=issue.title,
            session_number=state.session_count + 1,
            total_turns=state.total_turns_used,
            branch_name=state.branch_name,
            branch_note=branch_note,
            recent_notes=recent_notes,
            tools_dir=tools_dir,
        )
    return INITIAL_TEMPLATE.format(
        issue_number=issue.number,
        issue_title=issue.title,
        branch_note=branch_note,
        issue_body=issue.body or "No description provided.",
        tools_dir=tools_dir,
    )
