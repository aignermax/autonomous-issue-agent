"""
Prompt templates for Claude Code execution.
"""

CONTINUATION_TEMPLATE = """You are continuing work on issue #{issue_number}: {issue_title}

## Progress So Far

Session {session_number} - Total turns used: {total_turns}
Branch: {branch_name}{branch_note}

{recent_notes}

## Your Task

Continue where you left off. Review what's been done, then:
1. Check build status: `dotnet build`
2. Check test status: `dotnet test`
3. Continue implementing missing pieces
4. Fix any failing tests
5. **IMPORTANT:** Re-read the issue title to determine type:
   - "Investigate"/"Test"/"Verify" → ONLY write tests, NO UI
   - "Add feature"/"Implement UI" → Full vertical slice (Core + ViewModel + View)

**Do not give up!** Take as many attempts as needed to get tests passing.

Read CLAUDE.md for all project conventions."""

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
1. `dotnet build` → must pass
2. `dotnet test` → all pass
3. Fix errors/warnings
4. **Keep trying until it works**

## Issue #{issue_number}: {issue_title}

{issue_body}

## YOUR TASK

1. Read `CLAUDE.md` for architecture + `CODEBASE_MAP.md` for overview
2. Use glob/grep to find relevant files (e.g., `**/*ViewModel.cs`)
3. Find similar features to reuse patterns
4. Implement:
   - NEW FEATURES → Core + ViewModel + View + Tests
   - TESTS/BUGFIXES → Tests or fix only (NO UI)
5. Build/test iteratively, fix errors immediately
6. **Keep trying until tests pass!**

## 🔍 Tools

**Semantic search** (AI-powered code search):
```bash
/home/aigner/connect-a-pic-agent/venv/bin/python3 /home/aigner/connect-a-pic-agent/tools/semantic_search.py "query"
```

**Smart test** (filtered test output):
```bash
/home/aigner/connect-a-pic-agent/venv/bin/python3 /home/aigner/connect-a-pic-agent/tools/smart_test.py [filter]
```"""


def build_prompt(issue, state=None) -> str:
    """
    Build the implementation prompt for Claude Code.

    Args:
        issue: GitHub Issue object
        state: Optional session state for continuation

    Returns:
        Formatted prompt string
    """
    # Determine if working on existing feature branch
    is_feature_branch = state and not state.branch_name.startswith("agent/issue-")
    branch_note = (
        f"\n**IMPORTANT:** You are working on existing branch: `{state.branch_name}`\n"
        f"Do NOT create a new branch. All work must be on this branch."
        if is_feature_branch
        else ""
    )

    if state and state.session_count > 0:
        # Continuation prompt
        recent_notes = "\n".join(state.notes[-5:]) if state.notes else "No notes yet."
        return CONTINUATION_TEMPLATE.format(
            issue_number=issue.number,
            issue_title=issue.title,
            session_number=state.session_count + 1,
            total_turns=state.total_turns_used,
            branch_name=state.branch_name,
            branch_note=branch_note,
            recent_notes=recent_notes
        )
    else:
        # Initial prompt
        return INITIAL_TEMPLATE.format(
            issue_number=issue.number,
            issue_title=issue.title,
            branch_note=branch_note,
            issue_body=issue.body or "No description provided."
        )
