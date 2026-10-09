"""
Prompt templates for Claude Code execution.
"""

import re as _re
import logging as _logging
import os as _os
from pathlib import Path as _Path

_log = _logging.getLogger("agent")

# ------------------------------------------------------------------
# Prompt files. Built-in prompts live in src/prompts/<name>.md; a file
# prompts/<name>.md in the agent folder (or AGENT_PROMPTS_DIR) overrides it.
# The Control Center edits those overrides.
# ------------------------------------------------------------------
_BUILTIN_DIR = _Path(__file__).resolve().parent / "prompts"
PROMPT_NAMES = ("coder-initial", "coder-continuation", "reviewer", "coder-retry", "qa-review", "qa-fix", "pr-feedback")
_BUILTIN = {name: (_BUILTIN_DIR / f"{name}.md").read_text(encoding="utf-8") for name in PROMPT_NAMES}


def overrides_dir() -> _Path:
    return _Path(_os.environ.get("AGENT_PROMPTS_DIR") or _Path(__file__).resolve().parent.parent / "prompts")


def _render(name: str, **values) -> str:
    """Formats the override for `name` if one exists, else the built-in prompt.
    A broken override (unknown/unbalanced placeholder) falls back with a warning
    instead of failing the run."""
    path = overrides_dir() / f"{name}.md"
    if path.is_file():
        try:
            return path.read_text(encoding="utf-8").format(**values)
        except (KeyError, IndexError, ValueError) as e:
            _log.warning(f"Prompt override {path} unusable ({e!r}) — using the built-in prompt")
    return _BUILTIN[name].format(**values)



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


CONTINUATION_TEMPLATE = _BUILTIN["coder-continuation"]

INITIAL_TEMPLATE = _BUILTIN["coder-initial"]


def build_prompt(issue, state=None, repo_name=None, tools_dir: str = "tools",
                 tools_python: str = "python3", complexity: str = "REGULAR",
                 org_read_access: str = "") -> str:
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

    # Cross-repo reference access: org repos often depend on sibling repos
    # (ISA definitions, compilers, SDKs). Let the worker consult the source
    # instead of guessing.
    org_note = ""
    if org_read_access:
        org_note = f"""

## 🔎 Cross-repo reference access (read-only)
You have READ access to every repository in the `{org_read_access}` GitHub
org. When this task depends on a sibling repo — an ISA definition (e.g.
raycore-isa is the source of truth for assembly), a compiler, a shared SDK —
consult the actual source instead of guessing:
```bash
git clone --depth 1 https://x-access-token:${{GITHUB_TOKEN}}@github.com/{org_read_access}/<repo>.git /tmp/ref-<repo>
```
Rules: reference clones are read-only — never commit or push to them, and
never copy secrets or wholesale code from them into this repo.
"""

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
        return _render("coder-continuation", 
            issue_number=issue.number,
            issue_title=issue.title,
            session_number=state.session_count + 1,
            total_turns=state.total_turns_used,
            branch_name=state.branch_name,
            branch_note=branch_note,
            recent_notes=recent_notes,
            tools_dir=tools_dir,
            tools_python=tools_python,
        ) + workspace_note + org_note + ux_note + PR_SUMMARY_INSTRUCTION
    return _render("coder-initial", 
        issue_number=issue.number,
        issue_title=issue.title,
        branch_note=branch_note,
        issue_body=issue.body or "No description provided.",
        tools_dir=tools_dir,
        tools_python=tools_python,
    ) + workspace_note + org_note + ux_note + PR_SUMMARY_INSTRUCTION


REVIEWER_TEMPLATE = _BUILTIN["reviewer"]


def build_reviewer_prompt(issue, pr, branch: str, base_branch: str,
                          tools_dir: str, tools_python: str = "python3") -> str:
    """Build the reviewer prompt for a given PR."""
    return _render("reviewer", 
        pr_number=pr.number,
        issue_number=issue.number,
        issue_title=issue.title,
        issue_body=issue.body or "No description provided.",
        branch=branch,
        base_branch=base_branch,
        tools_dir=tools_dir,
        tools_python=tools_python,
    )


WORKER_RETRY_TEMPLATE = _BUILTIN["coder-retry"]


QA_REVIEW_TEMPLATE = _BUILTIN["qa-review"]


def build_qa_review_prompt(pr, branch: str, base_branch: str,
                           tools_dir: str = "tools",
                           tools_python: str = "python3",
                           screenshots_dir: str = "docs/pr-media") -> str:
    """Build the QA-reviewer prompt for a given PR.

    Unlike the implementation Reviewer, this one is PR-centric and does not
    require an Issue object — QA may run against PRs whose linking issue is
    stale or absent.

    screenshots_dir: where the visual walkthrough PNGs live on the branch.
    Default is docs/pr-media (pr_media publishes per-issue subfolders there;
    the transient artifacts/ copies are removed before commit).
    """
    return _render("qa-review", 
        pr_number=pr.number,
        pr_title=getattr(pr, "title", ""),
        branch=branch,
        base_branch=base_branch,
        tools_dir=tools_dir,
        tools_python=tools_python,
        screenshots_dir=screenshots_dir,
    )


QA_FIX_TEMPLATE = _BUILTIN["qa-fix"]


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
    return _render("qa-fix", 
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
    return _render("coder-retry", 
        issue_number=issue.number,
        issue_title=issue.title,
        issue_body=issue.body or "No description provided.",
        review_summary=review.summary,
        findings_text=findings_text,
        branch=branch,
        tools_dir=tools_dir,
        tools_python=tools_python,
    )


PR_FEEDBACK_TEMPLATE = _BUILTIN["pr-feedback"]


def build_pr_feedback_prompt(pr, branch: str, comment_body: str,
                             issue_number: int, tools_dir: str = "tools",
                             tools_python: str = "python3") -> str:
    """Build the prompt for the PR-feedback worker (human comment → fix)."""
    return _render("pr-feedback", 
        pr_number=pr.number,
        pr_title=getattr(pr, "title", ""),
        branch=branch,
        comment_body=comment_body or "(empty comment)",
        issue_number=issue_number,
        tools_dir=tools_dir,
        tools_python=tools_python,
    )
