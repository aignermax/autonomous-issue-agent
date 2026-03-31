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

INITIAL_TEMPLATE = """You are a senior C# / Avalonia developer implementing issue #{issue_number}: {issue_title}
{branch_note}

## CRITICAL: Read CLAUDE.md First

The repository contains `CLAUDE.md` with complete architecture guidelines. **Read it immediately.**

## Architecture Guidelines

**For NEW FEATURES:** Follow Vertical Slice Architecture:
1. Core logic (Connect-A-Pic-Core/)
2. ViewModel (CAP.Avalonia/ViewModels/) with [ObservableProperty] and [RelayCommand]
3. View/AXAML (MainWindow.axaml or new view)
4. DI wiring (App.axaml.cs if needed)
5. Unit tests (UnitTests/)
6. Integration tests (Core + ViewModel)

**For TESTS-ONLY or BUGFIXES:** UI is NOT required. Focus on:
- Writing comprehensive tests
- Fixing the specific bug
- No need for ViewModel/View if not adding user-facing features

**CRITICAL: Determine the issue type BEFORE starting:**

- ✅ **Test/Investigation issue** → Write ONLY tests, NO UI/ViewModel
  - Keywords: "test", "verify", "investigate", "reproduce", "confirm bug"
  - Example: "Investigate: PDK coordinate mismatch" → ONLY write tests
  - Example: "Add test: GDS roundtrip" → ONLY write tests

- ✅ **User-facing feature** → Full vertical slice (Core + ViewModel + View)
  - Keywords: "add feature", "implement UI", "user can", "new panel"
  - Example: "Add export dialog" → Full vertical slice required

**If in doubt, it's probably a test-only issue.** The user will explicitly say if they want UI.

## Code Quality Rules

- **Max 250 lines per NEW file**
- SOLID principles strictly
- Methods max ~20 lines
- Use CommunityToolkit.Mvvm patterns
- XML documentation for all public members
- No magic numbers

## Build & Verification

Before finishing:
1. `dotnet build` — must succeed
2. `dotnet test` — all tests must pass
3. Fix all errors and warnings
4. **Do not stop until everything works**

## Issue #{issue_number}: {issue_title}

{issue_body}

## YOUR TASK

1. **First:** Read `CLAUDE.md` for architecture patterns and `CODEBASE_MAP.md` for codebase overview
2. **Search efficiently:** Use glob patterns to find relevant files instead of reading everything
   - Example: Use `**/*ViewModel.cs` to find all ViewModels
   - Example: Use `**/MainWindow.axaml` to find the main UI
3. **Find similar features:** Search for existing features similar to what you're building
   - Example: For analysis features, check `Analysis/ParameterSweep*` files
   - Example: For UI features, check existing ViewModel patterns
4. **Implement complete solution:**
   - For NEW FEATURES: Core → ViewModel → View → Tests (full vertical slice)
   - For TESTS/BUGFIXES/INVESTIGATIONS: Just write tests or fix the bug (NO UI/ViewModel needed)
   - **"Investigate" issues = write diagnostic tests, NOT UI panels**
5. **Build and test iteratively:** Fix errors immediately, don't accumulate them
6. **PERSISTENCE:** Complex issues may take many attempts - keep trying until tests pass!

## EFFICIENCY TIPS

- Don't read entire files unless necessary - use grep/search first
- Reuse existing patterns from similar features
- Test early and often (dotnet build && dotnet test)
- Keep files under 250 lines (split if needed)

## 🔍 SEMANTIC SEARCH TOOL

You have access to a semantic code search tool that uses AI embeddings to find relevant code.

**IMPORTANT:** The tools are in a separate Python venv. Use the full path to the venv Python:

```bash
/home/aigner/connect-a-pic-agent/venv/bin/python3 /home/aigner/connect-a-pic-agent/tools/semantic_search.py "your search query"
```

**Examples:**
- `/home/aigner/connect-a-pic-agent/venv/bin/python3 /home/aigner/connect-a-pic-agent/tools/semantic_search.py "ViewModel for analysis features"`
- `/home/aigner/connect-a-pic-agent/venv/bin/python3 /home/aigner/connect-a-pic-agent/tools/semantic_search.py "where is bounding box calculation?"`
- `/home/aigner/connect-a-pic-agent/venv/bin/python3 /home/aigner/connect-a-pic-agent/tools/semantic_search.py "test files for parameter sweeping"`

This is MUCH better than grep for finding relevant code! Use it early and often.

## 🧪 SMART TEST TOOL

**IMPORTANT:** Do NOT use `dotnet test` directly! Use the smart test tool instead.

The tool is in a separate location - use the full path:

```bash
/home/aigner/connect-a-pic-agent/venv/bin/python3 /home/aigner/connect-a-pic-agent/tools/smart_test.py [optional-filter]
```

This filters output to show only summary instead of all 1193 test results!

**Examples:**
- `/home/aigner/connect-a-pic-agent/venv/bin/python3 /home/aigner/connect-a-pic-agent/tools/smart_test.py` - Run all tests, show compact summary
- `/home/aigner/connect-a-pic-agent/venv/bin/python3 /home/aigner/connect-a-pic-agent/tools/smart_test.py ParameterSweeper` - Run only ParameterSweeper tests
- `/home/aigner/connect-a-pic-agent/venv/bin/python3 /home/aigner/connect-a-pic-agent/tools/smart_test.py BoundingBox` - Run only BoundingBox-related tests
- `/home/aigner/connect-a-pic-agent/venv/bin/python3 /home/aigner/connect-a-pic-agent/tools/smart_test.py --file MyFeatureTests.cs` - Run specific test file

The tool shows:
- [OK]/[FAIL] Pass/Fail status
- Number of tests (passed/failed/skipped)
- Duration
- Failed test names (if any)

Much cleaner than raw dotnet output!"""


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
