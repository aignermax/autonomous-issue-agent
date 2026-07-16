"""
Prompt templates for Claude Code execution.
"""

import re as _re

# Appended to every coder prompt (initial + continuation). The block is
# extracted via extract_pr_summary() and becomes the PR body — keeping PR
# reports short, dense and reviewable at a glance instead of dumping the
# worker's full final message.
PR_SUMMARY_INSTRUCTION = """

## 📝 PR Report Format — STRICT
End your final message with EXACTLY this block (it becomes the PR
description — the human reviews PRs quickly, so keep it DENSE):

=== PR SUMMARY ===
- <what changed, one bullet per change — short sentences, no filler>
- <key decisions incl. UX decisions + rejected alternatives, if any>
- <how it was verified: build/tests/screenshots>
=== END ===

Rules: 4-8 bullets total, max ~15 words each, no headings inside the
block, no code dumps, no restating the issue text.
"""

_PR_SUMMARY_RE = _re.compile(
    r"===\s*PR SUMMARY\s*===\s*(.*?)\s*===\s*END\s*===", _re.DOTALL
)


def extract_pr_summary(output: str, max_fallback_chars: int = 1200) -> str:
    """Pull the dense `=== PR SUMMARY ===` block out of worker output.

    Falls back to a bounded tail of the output so the PR body is never
    empty — but never the unbounded full message.
    """
    if not output:
        return ""
    m = _PR_SUMMARY_RE.search(output)
    if m and m.group(1).strip():
        return m.group(1).strip()
    tail = output.strip()
    if len(tail) > max_fallback_chars:
        tail = "...\n" + tail[-max_fallback_chars:]
    return tail


CONTINUATION_TEMPLATE = """Continuing work on issue #{issue_number}: {issue_title}

## Progress So Far

Session {session_number} - Total turns used: {total_turns}
Branch: {branch_name}{branch_note}

{recent_notes}

## Your Task

Continue where you left off:
1. Check build (use build_errors.py):
   ```bash
   {tools_python} {tools_dir}/build_errors.py --suggest-fixes
   ```
2. Run tests (use smart_test.py):
   ```bash
   {tools_python} {tools_dir}/smart_test.py
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
   {tools_python} {tools_dir}/build_errors.py --suggest-fixes
   ```
2. **Test** (use smart test tool):
   ```bash
   {tools_python} {tools_dir}/smart_test.py
   ```
3. Fix all errors/warnings
4. **Keep trying until it works**

## Issue #{issue_number}: {issue_title}

{issue_body}

## YOUR TASK

1. Read `CLAUDE.md` for architecture + `CODEBASE_MAP.md` for overview
2. **ALWAYS use semantic search first** (better than glob/grep):
   ```bash
   {tools_python} {tools_dir}/semantic_search.py "your natural language query"
   ```
   Examples: "ViewModel for analysis", "test files for bounding box", "where is GDS export?"
3. Find similar features to reuse patterns
4. Implement:
   - NEW FEATURES → Core + ViewModel + View + Tests
   - TESTS/BUGFIXES → Tests or fix only (NO UI)
5. **ALWAYS use smart test tool** (NOT `dotnet test` directly):
   ```bash
   {tools_python} {tools_dir}/smart_test.py [filter]
   ```
   Shows clean summary instead of 1000+ test results!
6. Build/test iteratively, fix errors immediately
7. **Keep trying until tests pass!**
8. **BEFORE final commit:** Review your own changes:
   - Check for code quality issues
   - Look for potential bugs or edge cases
   - Verify tests cover main scenarios
   - Fix any issues you find BEFORE committing

## ⚠️ CRITICAL: WiX Installer Projects in WSL
**WiX Toolset CANNOT build MSI installers in WSL!**
- If issue involves WiX projects (.wixproj) or MSI installers:
  - Implement the .NET/C# code changes ONLY
  - DO NOT attempt to build WiX projects
  - Add comment in PR: "WiX installer build requires Windows - test manually"
  - Mark as complete after .NET code works
- Attempting to build WiX in WSL wastes tokens and will always fail!

## 🚀 IMPORTANT: Always use tools/ folder tools!
- **build_errors.py** - Filtered build output + fix suggestions (instead of `dotnet build`)
- **semantic_search.py** - AI code search (instead of grep)
- **smart_test.py** - Filtered test output (instead of `dotnet test`)
- **find_symbol.py** - Find class/method definitions + usages (when refactoring/implementing)
- **dotnet_deps.py** - Check NuGet packages (when debugging references/conflicts)

These tools save 500-5000 tokens per use! Use them frequently!
"""


def build_prompt(issue, state=None, repo_name=None, tools_dir: str = "tools",
                 tools_python: str = "python3", complexity: str = "REGULAR") -> str:
    """
    Build the implementation prompt for Claude Code.

    Args:
        issue: GitHub Issue object
        state: Optional session state for continuation
        repo_name: Current repository name (e.g., "Akhetonics/akhetonics-desktop");
                   triggers workspace-aware notes when set.
        tools_dir: Absolute path to python-dev-tools install dir
        tools_python: Path to the python interpreter that has the tools' deps
                      (e.g. ~/.cap-tools/venv/bin/python3). Defaults to plain
                      "python3" for backwards compatibility.
        complexity: "COMPLEX" or "REGULAR". On "COMPLEX", a UX design pass is
                    appended so the coder designs the interaction a real user
                    needs (personas, flows) — not just the core logic.

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

    # Add workspace note if working on akhetonics-desktop
    workspace_note = ""
    if repo_name and "akhetonics-desktop" in repo_name.lower():
        workspace_note = """

## 📦 IMPORTANT: Dependency Workspace Available
**You have access to ALL dependency repositories at:**
`/mnt/c/Users/MaxAigner/akhetonics-workspace/`

**Available repos:**
- `akhetonics-desktop/` — this project
- `SAPPHIRE-Compiler/` — the compiler (raycore-isa and raycore-assembler are also pulled in as submodules; top-level copies live alongside)
- `raycore-isa/` — instruction-set definition consumed by the compiler
- `raycore-assembler/` — assembler consumed by the compiler
- `phridge-blades-simulator/` — blade simulator belonging to the ISA stack
- `Phridge-Dispatcher/` — dispatcher belonging to the ISA stack
- `raycore-vulkan-icd/` — Vulkan ICD (vulkan-raycore-ICD)
- `raycore-vulkan-layer/` — Vulkan implicit layer
- `Lunima/` — photonic simulation tool

**When you need NuGet-consumed source code, or need to understand a
type/function that lives in one of these packages instead of in this
repo:**
1. Use `{tools_python} {tools_dir}/semantic_search.py --path /mnt/c/Users/MaxAigner/akhetonics-workspace --query "your search"`
2. Or scope to a specific dep, e.g. `--path /mnt/c/Users/MaxAigner/akhetonics-workspace/SAPPHIRE-Compiler`
3. `{tools_python} {tools_dir}/find_symbol.py SymbolName` also accepts `--path`
4. **DO NOT waste tokens guessing** — the source code is available locally!
""".format(tools_dir=tools_dir, tools_python=tools_python)

    # UX design pass — only for COMPLEX issues. Pushes the coder past bare
    # core logic into designing the interaction a real user actually needs.
    ux_note = ""
    if complexity == "COMPLEX":
        ux_note = f"""

## 🎨 UX Design Pass
Don't stop at the core business logic — design the *interaction* a real user needs.
1. **Personas:** Look for a "Personas" section in CLAUDE.md. If present, design explicitly from those personas' perspective — and if that section references another file (e.g. personas.md), read it first. If absent, reason briefly about the likely primary user — but don't fabricate elaborate personas.
2. **Ask the design question, not just the code question:** decide the *right* interaction — is a plain button enough, or does the user need a dialog/wizard to understand it, inline validation, sensible defaults — or should the action just happen automatically (with feedback) so there's nothing to click at all? Consider discoverability, feedback, and error states.
3. **Reuse existing patterns:** match the app's existing dialogs, styles, and MVVM conventions — don't invent inconsistent new UI.
4. **You have full autonomy** to add whatever UI/flows/affordances make the feature genuinely understandable — implement them as part of this ticket (still a complete vertical slice with tests). Note the key UX decisions (and rejected alternatives) as bullets in your PR SUMMARY block.
5. **Visual walkthrough (for the PR):** If this change adds or alters UI, capture the user flow so a reviewer sees it without checking out. Using the headless screenshot harness (see `UnitTests/UI/UiScreenshotTests.cs` for the Avalonia + Skia pattern), render the relevant view(s) in **each meaningful state** and save PNGs to `artifacts/ui-screenshots/issue-{issue.number}/` named in step order (e.g. `01-initial.png`, `02-after-click.png`, `03-result.png`), plus a `manifest.json` — a JSON array of `{{"file": "01-initial.png", "caption": "..."}}` in order. Captions: ONE short sentence — what the user sees/does in that step. The agent embeds these into the PR automatically — you do NOT need to touch the PR body.
"""

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
            tools_python=tools_python,
        ) + workspace_note + ux_note + PR_SUMMARY_INSTRUCTION
    return INITIAL_TEMPLATE.format(
        issue_number=issue.number,
        issue_title=issue.title,
        branch_note=branch_note,
        issue_body=issue.body or "No description provided.",
        tools_dir=tools_dir,
        tools_python=tools_python,
    ) + workspace_note + ux_note + PR_SUMMARY_INSTRUCTION


REVIEWER_TEMPLATE = """You are a senior code reviewer. Review PR #{pr_number} for issue #{issue_number}.

## Issue
**Title:** {issue_title}

{issue_body}

## Your Job
1. Read CLAUDE.md and AGENTS.md (if present) for project conventions.
2. Inspect the PR diff:
   ```bash
   git fetch origin +{branch}:refs/remotes/origin/{branch}
   git diff origin/{base_branch}..origin/{branch}
   ```
3. For deeper inspection, use:
   ```bash
   {tools_python} {tools_dir}/semantic_search.py "your query"
   {tools_python} {tools_dir}/find_symbol.py SymbolName
   ```
4. Verify (in this order):
   - Does the diff actually solve the issue's acceptance criteria?
   - Are there obvious correctness bugs (off-by-one, null deref, unhandled error paths)?
   - Tests: do they exist for new logic? Do they assert real behaviour, not just call shape?
   - Architecture: does it follow CLAUDE.md? Hard rules violated?
   - Security: any input validation gaps, secret logging, path traversal?

## Output Format — STRICT

End your review with EXACTLY this block (parsed by tooling):

```
=== REVIEW RESULT ===
VERDICT: <OK | BLOCKING>
SUMMARY: <one sentence>
=== FINDINGS ===
- [SEVERITY] <file:line> — <issue> — <suggested fix>
- [SEVERITY] <file:line> — <issue> — <suggested fix>
=== END ===
```

Severity levels: BLOCKING (must fix), NIT (suggestion). Use BLOCKING only for real
correctness/security/spec issues — not style.

If verdict is OK, the FINDINGS list may be empty.

DO NOT modify any files. DO NOT commit. Read-only review."""


def build_reviewer_prompt(issue, pr, branch: str, base_branch: str,
                          tools_dir: str, tools_python: str = "python3") -> str:
    """Build the reviewer prompt for a given PR."""
    return REVIEWER_TEMPLATE.format(
        pr_number=pr.number,
        issue_number=issue.number,
        issue_title=issue.title,
        issue_body=issue.body or "No description provided.",
        branch=branch,
        base_branch=base_branch,
        tools_dir=tools_dir,
        tools_python=tools_python,
    )


WORKER_RETRY_TEMPLATE = """Reviewer found issues on your PR for issue #{issue_number}.

## Reviewer Verdict: BLOCKING
{review_summary}

## Reviewer Findings
{findings_text}

## Your Task

Address every BLOCKING finding above. NIT findings are optional but
appreciated. Use the same tools as before:
- `{tools_python} {tools_dir}/semantic_search.py "..."` to locate code
- `{tools_python} {tools_dir}/build_errors.py --suggest-fixes` for build issues
- `{tools_python} {tools_dir}/smart_test.py` to run tests

After fixing, commit and push to the same branch (`{branch}`). The reviewer
will re-run automatically.

## Original Issue
{issue_title}

{issue_body}
"""


QA_REVIEW_TEMPLATE = """You are a QA reviewer running on a PR after build/test
have already passed mechanically. Verify the PR diff is actually shippable.

## PR
**Number:** #{pr_number}
**Branch:** `{branch}` (base `{base_branch}`)
**Title:** {pr_title}

## Your Job
1. Read CLAUDE.md / AGENTS.md if present for project conventions.
2. Inspect the diff:
   ```bash
   git diff origin/{base_branch}...origin/{branch}
   ```
3. Optional deeper inspection:
   ```bash
   {tools_python} {tools_dir}/semantic_search.py "your query"
   {tools_python} {tools_dir}/find_symbol.py SymbolName
   ```
4. Check for, in order:
   - Correctness bugs (off-by-one, null deref, unhandled error paths,
     resource leaks)
   - Tests: do new code paths have tests? Do tests assert real behaviour
     vs. just calling the API?
   - Architecture: hard rules from CLAUDE.md violated?
   - Security: input validation gaps, secret logging, path traversal,
     command injection
   - Scope creep: changes unrelated to the PR's stated purpose

## Output Format — STRICT

End your review with EXACTLY this block (parsed by tooling):

```
=== REVIEW RESULT ===
VERDICT: <OK | BLOCKING>
SUMMARY: <one sentence>
=== FINDINGS ===
- [SEVERITY] <file:line> — <issue> — <suggested fix>
- [SEVERITY] <file:line> — <issue> — <suggested fix>
=== END ===
```

Severity levels: BLOCKING (must fix), NIT (suggestion). Use BLOCKING only
for real correctness/security/spec issues — not style.

If verdict is OK, the FINDINGS list may be empty.

DO NOT modify any files. DO NOT commit. Read-only review."""


def build_qa_review_prompt(pr, branch: str, base_branch: str,
                           tools_dir: str = "tools",
                           tools_python: str = "python3") -> str:
    """Build the QA-reviewer prompt for a given PR.

    Unlike the implementation Reviewer, this one is PR-centric and does not
    require an Issue object — QA may run against PRs whose linking issue is
    stale or absent.
    """
    return QA_REVIEW_TEMPLATE.format(
        pr_number=pr.number,
        pr_title=getattr(pr, "title", ""),
        branch=branch,
        base_branch=base_branch,
        tools_dir=tools_dir,
        tools_python=tools_python,
    )


QA_FIX_TEMPLATE = """A previous QA pass on PR #{pr_number} (branch
`{branch}`) FAILED. Fix the issues described below and push to the same
branch — QA will rerun automatically.

## Original Issue
**#{issue_number}: {issue_title}**

{issue_body}

## QA Verdict (latest)
{qa_summary}

## QA Failure Details
{qa_details}

## Your Task
1. Read CLAUDE.md for project conventions.
2. Reproduce the failure locally if it is a build/test failure:
   ```bash
   {tools_python} {tools_dir}/build_errors.py --suggest-fixes
   {tools_python} {tools_dir}/smart_test.py
   ```
3. Address EVERY BLOCKING finding above. NIT findings are optional.
4. Add or update tests so the failure can't reappear silently.
5. Commit and push to branch `{branch}`. Do NOT open a new PR — the
   existing one (#{pr_number}) will pick the new commits up.

Do not refactor unrelated code. Keep the diff focused on the QA failure.
"""


def build_qa_fix_prompt(issue, pr, branch: str, qa_summary: str,
                        qa_details: str, tools_dir: str = "tools",
                        tools_python: str = "python3") -> str:
    """Build a fix prompt for a coder retrying after QA failure.

    `issue` may be None when the linked issue could not be resolved; in
    that case we fall back to the PR title for context.
    """
    issue_number = issue.number if issue is not None else "?"
    issue_title = issue.title if issue is not None else getattr(pr, "title", "")
    issue_body = (issue.body if issue is not None else "") or "No description provided."
    return QA_FIX_TEMPLATE.format(
        issue_number=issue_number,
        issue_title=issue_title,
        issue_body=issue_body,
        pr_number=pr.number,
        branch=branch,
        qa_summary=qa_summary or "(no summary provided)",
        qa_details=qa_details or "(no detail block provided)",
        tools_dir=tools_dir,
        tools_python=tools_python,
    )


def build_retry_prompt(issue, branch: str, review, tools_dir: str,
                       tools_python: str = "python3") -> str:
    """Build a worker retry prompt that includes reviewer findings."""
    findings_text = "\n".join(
        f"- [{f.severity}] {f.text}" for f in review.findings
    ) or "(no specific findings; verdict was BLOCKING — see summary)"
    return WORKER_RETRY_TEMPLATE.format(
        issue_number=issue.number,
        issue_title=issue.title,
        issue_body=issue.body or "No description provided.",
        review_summary=review.summary,
        findings_text=findings_text,
        branch=branch,
        tools_dir=tools_dir,
        tools_python=tools_python,
    )


PR_FEEDBACK_TEMPLATE = """A human reviewer left feedback on PR #{pr_number}
(branch `{branch}`, title: {pr_title}). Implement what they asked for and
push to the same branch.

## Reviewer Feedback (verbatim)
{comment_body}

## Your Task
1. Read CLAUDE.md for project conventions.
2. Implement the requested change. Stay focused — only what the feedback
   asks for (plus tests). Do not refactor unrelated code.
3. Build and test:
   ```bash
   {tools_python} {tools_dir}/build_errors.py --suggest-fixes
   {tools_python} {tools_dir}/smart_test.py
   ```
4. **If the change affects UI:** re-render the visual walkthrough so the
   reviewer sees the new state without checking out. Using the headless
   screenshot harness (see `UnitTests/UI/UiScreenshotTests.cs` for the
   Avalonia + Skia pattern), save step-ordered PNGs to
   `artifacts/ui-screenshots/issue-{issue_number}/` (e.g. `01-initial.png`,
   `02-after-click.png`) plus a `manifest.json` array of
   `{{"file": "...", "caption": "..."}}` entries (captions: ONE short
   sentence each). They are embedded into a reply comment automatically.
5. Commit to branch `{branch}`. Do NOT open a new PR.

End your final message with EXACTLY this block (parsed by tooling; 3-6
short bullet lines describing what you changed and why):

=== FEEDBACK REPORT ===
- <what changed>
- <what changed>
=== END ===
"""


def build_pr_feedback_prompt(pr, branch: str, comment_body: str,
                             issue_number: int, tools_dir: str = "tools",
                             tools_python: str = "python3") -> str:
    """Build the prompt for the PR-feedback worker (human comment → fix)."""
    return PR_FEEDBACK_TEMPLATE.format(
        pr_number=pr.number,
        pr_title=getattr(pr, "title", ""),
        branch=branch,
        comment_body=comment_body or "(empty comment)",
        issue_number=issue_number,
        tools_dir=tools_dir,
        tools_python=tools_python,
    )
