# Multi-Role Agent (Worker + Reviewer + Worktrees) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Erweitere den Autonomous Issue Agent um (a) Reviewer-Rolle mit Iterations-Loop, (b) Git-Worktrees pro Issue, (c) Auto-Install der `python-dev-tools` mit dynamischer Pfad-Injektion in Prompts.

**Architecture:** Bestehender `Agent` (Worker) bleibt als Hauptklasse erhalten. Neue `Reviewer`-Klasse läuft nach `git push` per `ClaudeCode` mit reduziertem `max_turns` und liest den PR-Diff. `process_issue` wird zum Loop: Worker → Reviewer → ggf. erneut Worker mit Feedback → max. `MAX_REVIEW_ROUNDS` (Default 2). `WorktreeManager` legt isolierte Working-Trees pro Issue an. `tools_dir` wird zur Laufzeit aus Submodul oder Auto-Clone bestimmt und in alle Prompts injiziert.

**Tech Stack:** Python 3.10+, pytest, PyGithub, Claude Code CLI (headless). Bestehende Patterns: `dataclass`-Result-Typen, Logger `agent`, env-basierte Config.

---

## File Structure

**New files:**
- `src/worktree.py` — `WorktreeManager` für `git worktree`-Operationen
- `src/reviewer.py` — `Reviewer`-Klasse für PR-Review per Claude Code
- `src/tools_bootstrap.py` — Auto-Install/Detection der `python-dev-tools`
- `tests/test_worktree.py` — Tests für `WorktreeManager`
- `tests/test_reviewer.py` — Tests für `Reviewer`
- `tests/test_tools_bootstrap.py` — Tests für Tools-Bootstrap
- `tests/test_prompt_template.py` — Tests für Prompt-Rendering mit `tools_dir`

**Modified files:**
- `src/config.py` — neue Felder: `tools_dir`, `worktree_dir`, `max_review_rounds`, `reviewer_model_default`, `reviewer_model_critical`, `critical_label`
- `src/prompt_template.py` — hardcodierte Pfade durch `{tools_dir}` ersetzen, neuer `REVIEWER_TEMPLATE` und `WORKER_RETRY_TEMPLATE`
- `src/claude_code.py` — `model`-Parameter in `__init__` und CLI-Aufruf
- `src/agent.py:556-654` (`process_issue`) — Worktree-Setup + Iterations-Loop
- `src/agent.py` — neue Methoden `_run_reviewer`, `_should_retry_worker`, `_build_retry_prompt`
- `main.py` — neuer CLI-Flag `--cleanup-worktrees`
- `CLAUDE.md` — „Connect-A-PIC-Pro" → „Lunima"; Tool-Pfade auf Platzhalter
- `.env.example` — neue Variablen dokumentieren
- `README.md` — Reviewer-Pipeline + Worktree-Setup dokumentieren
- `tests/test_config.py` — Tests für neue Config-Felder

---

## Task 1: Auto-Install der `python-dev-tools` + Config-Feld `tools_dir`

**Files:**
- Create: `src/tools_bootstrap.py`
- Create: `tests/test_tools_bootstrap.py`
- Modify: `src/config.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1.1: Failing test für `tools_bootstrap.find_tools_dir()`**

Datei `tests/test_tools_bootstrap.py` neu anlegen:

```python
"""Tests for tools bootstrap (auto-install of python-dev-tools)."""

from pathlib import Path
import pytest

from src.tools_bootstrap import find_tools_dir, REQUIRED_TOOLS, TOOLS_REPO_URL


class TestFindToolsDir:
    """Test detection of tools directory."""

    def test_detects_submodule_tools_dir(self, tmp_path):
        """When tools/ submodule exists with all required tools, return it."""
        tools = tmp_path / "tools"
        tools.mkdir()
        for tool in REQUIRED_TOOLS:
            (tools / tool).write_text("#!/usr/bin/env python3\n")

        result = find_tools_dir(agent_root=tmp_path)
        assert result == tools

    def test_returns_none_when_tools_missing(self, tmp_path):
        """When required tools are missing, return None."""
        tools = tmp_path / "tools"
        tools.mkdir()
        # Only one of several required tools present
        (tools / "semantic_search.py").write_text("")

        result = find_tools_dir(agent_root=tmp_path)
        assert result is None

    def test_returns_none_when_dir_missing(self, tmp_path):
        """When tools/ dir doesn't exist, return None."""
        result = find_tools_dir(agent_root=tmp_path)
        assert result is None
```

- [ ] **Step 1.2: Run test, verify it fails**

```bash
cd /home/max/Projects/autonomous-issue-agent
python -m pytest tests/test_tools_bootstrap.py -v
```

Expected: ImportError — `src.tools_bootstrap` doesn't exist yet.

- [ ] **Step 1.3: Implement `find_tools_dir`**

Datei `src/tools_bootstrap.py` neu anlegen:

```python
"""Auto-install and detection of python-dev-tools.

The agent uses helper tools (semantic_search.py, smart_test.py, etc.) that live in
a separate repository. This module ensures they are present on disk and exposes
their absolute path for use in prompt templates.
"""

import logging
import subprocess
from pathlib import Path
from typing import Optional

log = logging.getLogger("agent")

REQUIRED_TOOLS = (
    "semantic_search.py",
    "smart_test.py",
    "build_errors.py",
    "find_symbol.py",
    "dotnet_deps.py",
)

TOOLS_REPO_URL = "https://github.com/aignermax/python-dev-tools.git"


def find_tools_dir(agent_root: Path) -> Optional[Path]:
    """Return path to tools dir if all REQUIRED_TOOLS are present, else None.

    Args:
        agent_root: Root of the agent installation (parent of `src/`).

    Returns:
        Absolute path to tools dir, or None if missing/incomplete.
    """
    candidate = agent_root / "tools"
    if not candidate.is_dir():
        return None
    for tool in REQUIRED_TOOLS:
        if not (candidate / tool).is_file():
            return None
    return candidate.resolve()
```

- [ ] **Step 1.4: Run tests, verify they pass**

```bash
python -m pytest tests/test_tools_bootstrap.py -v
```

Expected: 3 passed.

- [ ] **Step 1.5: Failing tests für `ensure_tools_installed()`**

Anhängen an `tests/test_tools_bootstrap.py`:

```python
class TestEnsureToolsInstalled:
    """Test bootstrap that initializes submodule or clones tools repo."""

    def test_returns_path_when_already_present(self, tmp_path, monkeypatch):
        """If tools already complete, no install action needed."""
        from src.tools_bootstrap import ensure_tools_installed

        tools = tmp_path / "tools"
        tools.mkdir()
        for tool in REQUIRED_TOOLS:
            (tools / tool).write_text("")

        called = []
        monkeypatch.setattr("subprocess.run", lambda *a, **kw: called.append(a) or _ok())

        result = ensure_tools_installed(agent_root=tmp_path)

        assert result == tools.resolve()
        assert called == [], "should not invoke subprocess when tools already present"

    def test_initializes_submodule_when_dir_empty(self, tmp_path, monkeypatch):
        """If tools/ exists empty (uninit submodule), run submodule update."""
        from src.tools_bootstrap import ensure_tools_installed

        (tmp_path / "tools").mkdir()
        (tmp_path / ".gitmodules").write_text("[submodule \"tools\"]\n")

        run_calls = []

        def fake_run(cmd, **kw):
            run_calls.append(cmd)
            # After "submodule update", populate the dir
            if "submodule" in cmd:
                for tool in REQUIRED_TOOLS:
                    (tmp_path / "tools" / tool).write_text("")
            return _ok()

        monkeypatch.setattr("subprocess.run", fake_run)

        result = ensure_tools_installed(agent_root=tmp_path)

        assert result == (tmp_path / "tools").resolve()
        assert any("submodule" in c for c in run_calls)

    def test_clones_when_no_submodule_and_no_dir(self, tmp_path, monkeypatch):
        """If no submodule config and no tools/, clone repo into tools/."""
        from src.tools_bootstrap import ensure_tools_installed

        run_calls = []

        def fake_run(cmd, **kw):
            run_calls.append(cmd)
            if "clone" in cmd:
                tools = tmp_path / "tools"
                tools.mkdir()
                for tool in REQUIRED_TOOLS:
                    (tools / tool).write_text("")
            return _ok()

        monkeypatch.setattr("subprocess.run", fake_run)

        result = ensure_tools_installed(agent_root=tmp_path)

        assert result == (tmp_path / "tools").resolve()
        assert any("clone" in c and TOOLS_REPO_URL in c for c in run_calls)


def _ok():
    """Helper: minimal CompletedProcess stand-in."""
    import subprocess
    return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
```

- [ ] **Step 1.6: Implement `ensure_tools_installed`**

Anhängen an `src/tools_bootstrap.py`:

```python
def ensure_tools_installed(agent_root: Path) -> Path:
    """Ensure python-dev-tools are installed, return absolute path.

    Strategy:
    1. If all required tools already present in <agent_root>/tools/, return path.
    2. Else if .gitmodules declares the submodule, run `git submodule update --init`.
    3. Else clone TOOLS_REPO_URL into <agent_root>/tools/.

    Raises:
        RuntimeError: if all strategies fail to make tools available.
    """
    existing = find_tools_dir(agent_root)
    if existing:
        log.info(f"python-dev-tools present: {existing}")
        return existing

    tools_dir = agent_root / "tools"
    gitmodules = agent_root / ".gitmodules"

    if gitmodules.is_file() and "tools" in gitmodules.read_text():
        log.info("Initializing python-dev-tools submodule...")
        result = subprocess.run(
            ["git", "submodule", "update", "--init", "--recursive", "tools"],
            cwd=agent_root,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            log.warning(f"submodule update failed: {result.stderr}")
    else:
        log.info(f"Cloning python-dev-tools from {TOOLS_REPO_URL}...")
        result = subprocess.run(
            ["git", "clone", TOOLS_REPO_URL, str(tools_dir)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Failed to clone tools repo: {result.stderr}")

    final = find_tools_dir(agent_root)
    if not final:
        missing = [t for t in REQUIRED_TOOLS if not (tools_dir / t).is_file()]
        raise RuntimeError(
            f"python-dev-tools install incomplete. Missing: {missing}. "
            f"Manual fix: clone {TOOLS_REPO_URL} into {tools_dir}"
        )
    return final
```

- [ ] **Step 1.7: Run tests, verify they pass**

```bash
python -m pytest tests/test_tools_bootstrap.py -v
```

Expected: 6 passed.

- [ ] **Step 1.8: Add `tools_dir` to Config**

In `src/config.py`, im `__init__` nach `self.session_dir = ...` einfügen:

```python
        # Tools directory (auto-detected via tools_bootstrap; lazy init in Agent)
        self.tools_dir: Optional[Path] = None
```

Außerdem oben: `from typing import Optional` ist schon da.

- [ ] **Step 1.9: Test `tools_dir` field exists with default None**

Anhängen an `tests/test_config.py` in `class TestConfig`:

```python
    def test_tools_dir_default_none(self, monkeypatch):
        """tools_dir starts as None and is populated lazily."""
        monkeypatch.setenv("GITHUB_TOKEN", "t")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
        config = Config()
        assert config.tools_dir is None
```

- [ ] **Step 1.10: Run tests**

```bash
python -m pytest tests/test_config.py tests/test_tools_bootstrap.py -v
```

Expected: all passed.

- [ ] **Step 1.11: Commit**

```bash
git add src/tools_bootstrap.py src/config.py tests/test_tools_bootstrap.py tests/test_config.py
git commit -m "feat: auto-install python-dev-tools and expose tools_dir

Adds tools_bootstrap module with find_tools_dir / ensure_tools_installed.
Replaces hardcoded /home/aigner/... paths with runtime detection.
Adds tools_dir field on Config (populated lazily by Agent)."
```

---

## Task 2: Dynamic `{tools_dir}` injection in prompt templates

**Files:**
- Modify: `src/prompt_template.py`
- Create: `tests/test_prompt_template.py`

- [ ] **Step 2.1: Failing tests for prompt rendering**

Datei `tests/test_prompt_template.py` neu anlegen:

```python
"""Tests for prompt template rendering."""

from unittest.mock import MagicMock

from src.prompt_template import build_prompt, INITIAL_TEMPLATE, CONTINUATION_TEMPLATE


def _make_issue(number=42, title="Test issue", body="Implement X"):
    issue = MagicMock()
    issue.number = number
    issue.title = title
    issue.body = body
    return issue


class TestPromptTemplate:
    """Test prompt rendering with tools_dir."""

    def test_initial_prompt_substitutes_tools_dir(self):
        """tools_dir placeholder is replaced with actual path."""
        prompt = build_prompt(_make_issue(), tools_dir="/opt/aia/tools")

        assert "/opt/aia/tools/semantic_search.py" in prompt
        assert "/opt/aia/tools/smart_test.py" in prompt
        assert "/opt/aia/tools/build_errors.py" in prompt
        assert "{tools_dir}" not in prompt
        assert "/home/aigner/connect-a-pic-agent" not in prompt

    def test_continuation_prompt_substitutes_tools_dir(self):
        """tools_dir placeholder is replaced in continuation template."""
        state = MagicMock()
        state.session_count = 1
        state.total_turns_used = 50
        state.branch_name = "agent/issue-42"
        state.notes = ["did X", "did Y"]

        prompt = build_prompt(_make_issue(), state=state, tools_dir="/x/tools")

        assert "/x/tools/smart_test.py" in prompt
        assert "{tools_dir}" not in prompt

    def test_initial_template_has_tools_dir_placeholder(self):
        """Source template contains placeholder, not absolute path."""
        assert "{tools_dir}" in INITIAL_TEMPLATE
        assert "/home/aigner" not in INITIAL_TEMPLATE

    def test_continuation_template_has_tools_dir_placeholder(self):
        """Continuation template contains placeholder."""
        assert "{tools_dir}" in CONTINUATION_TEMPLATE
        assert "/home/aigner" not in CONTINUATION_TEMPLATE
```

- [ ] **Step 2.2: Run tests, verify they fail**

```bash
python -m pytest tests/test_prompt_template.py -v
```

Expected: FAIL (placeholder not present, hardcoded path still there, build_prompt has no tools_dir param).

- [ ] **Step 2.3: Replace hardcoded paths in `prompt_template.py`**

In `src/prompt_template.py`: ersetze alle Vorkommen von `/home/aigner/connect-a-pic-agent/venv/bin/python3 /home/aigner/connect-a-pic-agent/tools/<TOOL>.py` durch `python3 {tools_dir}/<TOOL>.py`. Gilt sowohl in `INITIAL_TEMPLATE` als auch `CONTINUATION_TEMPLATE`.

Konkretes sed-Pattern (oder per Edit-Tool manuell):

```
/home/aigner/connect-a-pic-agent/venv/bin/python3 /home/aigner/connect-a-pic-agent/tools/  →  python3 {tools_dir}/
```

Beispielzeile vorher:
```
   /home/aigner/connect-a-pic-agent/venv/bin/python3 /home/aigner/connect-a-pic-agent/tools/semantic_search.py
```
nachher:
```
   python3 {tools_dir}/semantic_search.py
```

- [ ] **Step 2.4: Update `build_prompt()` to accept tools_dir**

In `src/prompt_template.py`, ersetze `def build_prompt(issue, state=None) -> str:` durch:

```python
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
```

- [ ] **Step 2.5: Run prompt template tests**

```bash
python -m pytest tests/test_prompt_template.py -v
```

Expected: 4 passed.

- [ ] **Step 2.6: Update `Agent._build_prompt` to pass tools_dir**

In `src/agent.py`, finde `def _build_prompt(self, issue, state: Optional[SessionState] = None) -> str:` (~line 542). Ersetze den `return build_prompt(issue, state)` durch:

```python
        tools_dir = str(self.config.tools_dir) if self.config.tools_dir else "tools"
        return build_prompt(issue, state=state, tools_dir=tools_dir)
```

- [ ] **Step 2.7: Initialize tools_dir in Agent constructor**

In `src/agent.py`, in `Agent.__init__` (nach `self.session_manager = ...`), einfügen:

```python
        # Bootstrap python-dev-tools and expose path for prompts
        from .tools_bootstrap import ensure_tools_installed
        agent_root = Path(__file__).resolve().parent.parent
        try:
            self.config.tools_dir = ensure_tools_installed(agent_root)
        except RuntimeError as e:
            log.warning(f"Tools bootstrap failed: {e}. Prompts will reference relative 'tools/'.")
```

- [ ] **Step 2.8: Run all tests**

```bash
python -m pytest -v
```

Expected: all green (no regressions in test_config.py / test_session_state.py / test_github_client.py).

- [ ] **Step 2.9: Commit**

```bash
git add src/prompt_template.py src/agent.py tests/test_prompt_template.py
git commit -m "feat: inject tools_dir into prompts dynamically

Replaces hardcoded /home/aigner/connect-a-pic-agent/... with {tools_dir}
placeholder. Agent populates tools_dir via tools_bootstrap on init."
```

---

## Task 3: `WorktreeManager` class

**Files:**
- Create: `src/worktree.py`
- Create: `tests/test_worktree.py`

- [ ] **Step 3.1: Failing tests for `WorktreeManager`**

Datei `tests/test_worktree.py` neu anlegen:

```python
"""Tests for WorktreeManager."""

import subprocess
from pathlib import Path

import pytest

from src.worktree import WorktreeManager


@pytest.fixture
def repo(tmp_path):
    """Create a real git repo for worktree integration tests."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    (repo / "README.md").write_text("hi")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)
    return repo


class TestWorktreeManager:
    def test_create_worktree_for_new_branch(self, repo, tmp_path):
        """create() makes a new branch and worktree at expected location."""
        wt_root = tmp_path / "worktrees"
        mgr = WorktreeManager(worktree_root=wt_root)

        path = mgr.create(repo_path=repo, branch="agent/issue-1", base="main")

        assert path.is_dir()
        assert (path / ".git").exists()
        assert (path / "README.md").is_file()
        # Branch checked out in worktree
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=path, capture_output=True, text=True,
        )
        assert result.stdout.strip() == "agent/issue-1"

    def test_create_is_idempotent(self, repo, tmp_path):
        """Calling create() twice with same branch returns existing worktree."""
        wt_root = tmp_path / "worktrees"
        mgr = WorktreeManager(worktree_root=wt_root)

        p1 = mgr.create(repo_path=repo, branch="agent/issue-2", base="main")
        p2 = mgr.create(repo_path=repo, branch="agent/issue-2", base="main")

        assert p1 == p2

    def test_remove_worktree(self, repo, tmp_path):
        """remove() detaches worktree and deletes the directory."""
        wt_root = tmp_path / "worktrees"
        mgr = WorktreeManager(worktree_root=wt_root)
        path = mgr.create(repo_path=repo, branch="agent/issue-3", base="main")
        assert path.is_dir()

        mgr.remove(repo_path=repo, branch="agent/issue-3")

        assert not path.exists()
        # Branch still exists in repo, just not checked out
        result = subprocess.run(
            ["git", "branch", "--list", "agent/issue-3"],
            cwd=repo, capture_output=True, text=True,
        )
        assert "agent/issue-3" in result.stdout

    def test_list_worktrees(self, repo, tmp_path):
        """list() returns all known worktrees for the repo."""
        wt_root = tmp_path / "worktrees"
        mgr = WorktreeManager(worktree_root=wt_root)
        mgr.create(repo_path=repo, branch="agent/issue-4", base="main")
        mgr.create(repo_path=repo, branch="agent/issue-5", base="main")

        wts = mgr.list(repo_path=repo)

        branches = {wt.branch for wt in wts}
        assert "agent/issue-4" in branches
        assert "agent/issue-5" in branches
```

- [ ] **Step 3.2: Run tests, verify they fail**

```bash
python -m pytest tests/test_worktree.py -v
```

Expected: ImportError.

- [ ] **Step 3.3: Implement `WorktreeManager`**

Datei `src/worktree.py` neu anlegen:

```python
"""Git worktree management for isolated per-issue working directories.

Each issue gets its own worktree under <worktree_root>/<repo-name>/<branch>/.
This isolates parallel issue processing and prevents working-directory
contamination between runs.
"""

import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List

log = logging.getLogger("agent")


@dataclass(frozen=True)
class WorktreeInfo:
    """One row from `git worktree list`."""
    path: Path
    branch: str
    head: str


class WorktreeManager:
    """Creates and removes git worktrees for the agent."""

    def __init__(self, worktree_root: Path):
        """
        Args:
            worktree_root: Base directory for all agent worktrees
                           (e.g. ~/.aia-worktrees).
        """
        self.worktree_root = worktree_root.expanduser()
        self.worktree_root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, repo_path: Path, branch: str) -> Path:
        repo_name = repo_path.resolve().name
        safe = branch.replace("/", "_")
        return self.worktree_root / repo_name / safe

    def create(self, repo_path: Path, branch: str, base: str) -> Path:
        """Create a worktree for `branch` derived from `base`.

        If the worktree already exists, returns its path without re-creating.

        Args:
            repo_path: Main checkout (where .git lives).
            branch: Branch name to create or check out.
            base: Branch to derive from when creating new branch.

        Returns:
            Absolute path of the worktree.
        """
        target = self._path_for(repo_path, branch)
        if target.is_dir() and (target / ".git").exists():
            log.info(f"Worktree already exists: {target}")
            return target

        target.parent.mkdir(parents=True, exist_ok=True)

        # Check if branch already exists locally
        local = subprocess.run(
            ["git", "rev-parse", "--verify", branch],
            cwd=repo_path, capture_output=True, text=True,
        )
        if local.returncode == 0:
            cmd = ["git", "worktree", "add", str(target), branch]
        else:
            cmd = ["git", "worktree", "add", "-b", branch, str(target), base]

        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"git worktree add failed: {result.stderr}")
        log.info(f"Created worktree: {target} (branch {branch})")
        return target

    def remove(self, repo_path: Path, branch: str) -> None:
        """Remove a worktree by branch. Does not delete the branch itself."""
        target = self._path_for(repo_path, branch)
        if not target.exists():
            log.info(f"Worktree already gone: {target}")
            return
        result = subprocess.run(
            ["git", "worktree", "remove", "--force", str(target)],
            cwd=repo_path, capture_output=True, text=True,
        )
        if result.returncode != 0:
            log.warning(f"git worktree remove failed, falling back to manual delete: {result.stderr}")
            import shutil
            shutil.rmtree(target, ignore_errors=True)
            subprocess.run(
                ["git", "worktree", "prune"],
                cwd=repo_path, capture_output=True, text=True,
            )

    def list(self, repo_path: Path) -> List[WorktreeInfo]:
        """List all worktrees registered in `repo_path`."""
        result = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            cwd=repo_path, capture_output=True, text=True,
        )
        if result.returncode != 0:
            return []

        worktrees: List[WorktreeInfo] = []
        current = {}
        for line in result.stdout.splitlines():
            if not line.strip():
                if current.get("worktree"):
                    worktrees.append(WorktreeInfo(
                        path=Path(current["worktree"]),
                        branch=current.get("branch", "").replace("refs/heads/", ""),
                        head=current.get("HEAD", ""),
                    ))
                current = {}
                continue
            m = re.match(r"^(\S+)\s*(.*)$", line)
            if m:
                current[m.group(1)] = m.group(2)
        if current.get("worktree"):
            worktrees.append(WorktreeInfo(
                path=Path(current["worktree"]),
                branch=current.get("branch", "").replace("refs/heads/", ""),
                head=current.get("HEAD", ""),
            ))
        # Drop the main checkout (no branch ref or first entry)
        return [w for w in worktrees if w.path.resolve() != repo_path.resolve()]
```

- [ ] **Step 3.4: Run tests, verify they pass**

```bash
python -m pytest tests/test_worktree.py -v
```

Expected: 4 passed.

- [ ] **Step 3.5: Commit**

```bash
git add src/worktree.py tests/test_worktree.py
git commit -m "feat: add WorktreeManager for per-issue isolation

Creates/removes git worktrees under ~/.aia-worktrees/<repo>/<branch>/.
Idempotent create, force-remove with prune fallback."
```

---

## Task 4: Integrate worktrees into `Agent.process_issue`

**Files:**
- Modify: `src/config.py`
- Modify: `src/agent.py`
- Modify: `main.py`

- [ ] **Step 4.1: Add `worktree_dir` to Config**

In `src/config.py`, im `__init__` nach `self.session_dir = ...`:

```python
        # Worktree base directory (one subdir per repo+branch)
        self.worktree_dir: Path = Path(
            os.environ.get("AGENT_WORKTREE_DIR", "~/.aia-worktrees")
        ).expanduser()
```

- [ ] **Step 4.2: Add config test**

In `tests/test_config.py` an `class TestConfig` anhängen:

```python
    def test_worktree_dir_default(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "t")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
        config = Config()
        assert str(config.worktree_dir).endswith(".aia-worktrees")

    def test_worktree_dir_override(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GITHUB_TOKEN", "t")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
        monkeypatch.setenv("AGENT_WORKTREE_DIR", str(tmp_path / "wt"))
        config = Config()
        assert config.worktree_dir == tmp_path / "wt"
```

- [ ] **Step 4.3: Run config tests**

```bash
python -m pytest tests/test_config.py -v
```

Expected: all passed.

- [ ] **Step 4.4: Inject WorktreeManager into Agent**

In `src/agent.py`, `Agent.__init__`, ersetze `self.session_manager = SessionManager(config.session_dir)` durch:

```python
        self.session_manager = SessionManager(config.session_dir)
        from .worktree import WorktreeManager
        self.worktrees = WorktreeManager(worktree_root=config.worktree_dir)
```

- [ ] **Step 4.5: Switch ClaudeCode + GitRepo to use worktree path**

In `src/agent.py`, `_setup_for_repo` (~line 654), nach dem Setup von `self.git`:

Finde den Codeabschnitt, in dem `self.claude = ClaudeCode(...)` initialisiert wird (Suche nach `self.claude =` in `_setup_for_repo`). Ändere die `working_dir` so, dass sie pro Issue gesetzt wird statt einmal in `_setup_for_repo`. Konkret: lasse `self.claude` in `_setup_for_repo` weiterhin auf den Hauptcheckout zeigen (für initiale Validierung), aber in `process_issue` überschreibe `self.claude` für jedes Issue mit einem neuen `ClaudeCode(working_dir=worktree_path, ...)`.

In `process_issue` (~line 556), unmittelbar nach `branch = self._claim_issue_and_create_branch(issue)` (etwa nach line 580 — Position varies; suche nach „branch =" in `process_issue`), einfügen:

```python
        # Create isolated worktree for this issue
        worktree_path = self.worktrees.create(
            repo_path=self.config.local_path,
            branch=branch,
            base=self.git.get_working_branch(),
        )
        log.info(f"Using worktree: {worktree_path}")

        # Re-target git operations and Claude Code at the worktree
        worktree_git = GitRepo(
            path=worktree_path,
            remote_url=self.git.remote_url,
            default_branch=self.git.default_branch,
        )
        from .claude_code import ClaudeCode
        max_turns, _, _ = self._detect_issue_complexity(issue)
        worktree_claude = ClaudeCode(working_dir=worktree_path, max_turns=max_turns)

        # Save originals; swap in worktree-bound versions for this run
        original_git, original_claude = self.git, self.claude
        self.git, self.claude = worktree_git, worktree_claude
        try:
            return self._process_issue_in_worktree(issue, branch, worktree_path)
        finally:
            self.git, self.claude = original_git, original_claude
```

Hinweis: Das verlangt einen Refactor — der eigentliche Issue-Processing-Code muss in `_process_issue_in_worktree` umbenannt werden. Mache das, indem du den **gesamten** Body von `process_issue` (außer dem oben eingefügten Wrapper) in eine neue Methode `_process_issue_in_worktree(self, issue, branch, worktree_path)` verschiebst und am Methodenende den Body verschiebst. **Wichtig**: Der originale `branch = self._claim_issue_and_create_branch(issue)` muss VOR dem Wrapper passieren, damit `branch` im Wrapper zur Verfügung steht.

Korrigiertes Pattern (in `src/agent.py` ersetzt das alte `process_issue`):

```python
    def process_issue(self, issue) -> IssueResult:
        """Process one issue, isolated in its own git worktree."""
        branch = self._claim_issue_and_create_branch(issue)

        worktree_path = self.worktrees.create(
            repo_path=self.config.local_path,
            branch=branch,
            base=self.git.get_working_branch(),
        )
        log.info(f"Using worktree: {worktree_path}")

        from .claude_code import ClaudeCode
        max_turns, _, _ = self._detect_issue_complexity(issue)
        worktree_git = GitRepo(
            path=worktree_path,
            remote_url=self.git.remote_url,
            default_branch=self.git.default_branch,
        )
        worktree_claude = ClaudeCode(working_dir=worktree_path, max_turns=max_turns)

        original_git, original_claude = self.git, self.claude
        self.git, self.claude = worktree_git, worktree_claude
        try:
            return self._process_issue_in_worktree(issue, branch, worktree_path)
        finally:
            self.git, self.claude = original_git, original_claude
```

Und benenne den restlichen alten Body um in:

```python
    def _process_issue_in_worktree(self, issue, branch: str, worktree_path: Path) -> IssueResult:
        """Run worker (and later reviewer loop) inside the worktree.

        Args:
            issue: GitHub Issue object
            branch: Already-claimed branch name
            worktree_path: Path to the worktree (used by self.git/self.claude)
        """
        # ... der bisherige Body von process_issue, OHNE den
        # `branch = self._claim_issue_and_create_branch(issue)` Aufruf, den
        # haben wir bereits im Wrapper erledigt.
```

(Im alten `process_issue` lass den ersten Aufruf `self._claim_issue_and_create_branch(issue)` raus — er wandert in den neuen Wrapper. Der Rest bleibt unverändert.)

- [ ] **Step 4.6: Cleanup worktree on success**

In `_create_or_find_pr` (oder am Ende von `_process_issue_in_worktree`, nach erfolgreichem PR-Create), füge hinzu:

```python
        # Worktree cleanup happens externally via --cleanup-worktrees;
        # we keep the worktree until PR is merged so reviewer loop can iterate.
```

(Bewusst KEIN sofortiger Cleanup — der Reviewer-Loop in Task 7 nutzt das Worktree noch.)

- [ ] **Step 4.7: Add `--cleanup-worktrees` CLI flag**

In `main.py`, im argparse-Block ergänzen:

```python
    parser.add_argument("--cleanup-worktrees", action="store_true",
                        help="Remove worktrees for closed/merged PRs and exit")
```

Im Body, nach `agent = Agent(config)`, vor dem `if args.once is not None:` Block einfügen:

```python
    if args.cleanup_worktrees:
        agent.cleanup_merged_worktrees()
        sys.exit(0)
```

In `src/agent.py`, neue Methode in `Agent`:

```python
    def cleanup_merged_worktrees(self) -> None:
        """Remove worktrees for branches whose PRs are closed or merged."""
        for repo_name in self.config.repo_names:
            self._setup_for_repo(repo_name)
            for wt in self.worktrees.list(self.config.local_path):
                if not wt.branch.startswith("agent/"):
                    continue
                pr = self.github.get_pr_by_branch(wt.branch)
                if pr is None:
                    log.info(f"No open PR for {wt.branch} — removing worktree")
                    self.worktrees.remove(self.config.local_path, wt.branch)
```

- [ ] **Step 4.8: Smoke test — agent imports and constructs without error**

```bash
python -c "from src.config import Config; import os; os.environ['GITHUB_TOKEN']='x'; os.environ['ANTHROPIC_API_KEY']='x'; from src.agent import Agent; print('ok')"
```

Expected: `ok` (no import or constructor error).

- [ ] **Step 4.9: Run all tests**

```bash
python -m pytest -v
```

Expected: all green.

- [ ] **Step 4.10: Commit**

```bash
git add src/config.py src/agent.py main.py tests/test_config.py
git commit -m "feat: process each issue in isolated git worktree

Worktrees live under config.worktree_dir (default ~/.aia-worktrees).
Adds --cleanup-worktrees CLI flag to drop worktrees for closed PRs."
```

---

## Task 5: `ClaudeCode` model parameter

**Files:**
- Modify: `src/claude_code.py`

- [ ] **Step 5.1: Add `model` parameter to `ClaudeCode.__init__`**

In `src/claude_code.py`, ändere die `__init__`-Signatur und das `cmd`-Array in `execute`.

Signatur:

```python
    def __init__(self, working_dir: Path, max_turns: int = 300, model: Optional[str] = None):
        """
        Initialize Claude Code runner.

        Args:
            working_dir: Directory where Claude Code should execute
            max_turns: Maximum number of tool call turns
            model: Optional model override (e.g. "claude-opus-4-7"). None = CLI default.
        """
        self.working_dir = working_dir
        self.max_turns = max_turns
        self.model = model
        self.claude_cli = find_claude_cli()
        self._verify_installation()
```

In `execute()`, im `cmd`-Array nach dem `--max-turns`-Eintrag einfügen:

```python
        if self.model:
            cmd.extend(["--model", self.model])
```

- [ ] **Step 5.2: Quick verification**

```bash
python -c "from src.claude_code import ClaudeCode; print(ClaudeCode.__init__.__doc__)"
```

Expected: docstring contains "model".

- [ ] **Step 5.3: Commit**

```bash
git add src/claude_code.py
git commit -m "feat: add optional model parameter to ClaudeCode

Allows callers (e.g. Reviewer) to pin a specific model via --model flag."
```

---

## Task 6: `Reviewer` class + prompt template

**Files:**
- Modify: `src/prompt_template.py`
- Create: `src/reviewer.py`
- Create: `tests/test_reviewer.py`
- Modify: `src/config.py`
- Modify: `tests/test_config.py`

- [ ] **Step 6.1: Add reviewer config fields**

In `src/config.py`, in `__init__`:

```python
        # Reviewer settings
        self.max_review_rounds: int = int(os.environ.get("AGENT_MAX_REVIEW_ROUNDS", "2"))
        self.reviewer_model_default: str = os.environ.get(
            "AGENT_REVIEWER_MODEL", "claude-sonnet-4-6")
        self.reviewer_model_critical: str = os.environ.get(
            "AGENT_REVIEWER_MODEL_CRITICAL", "claude-opus-4-7")
        self.critical_label: str = os.environ.get("AGENT_CRITICAL_LABEL", "critical")
        self.reviewer_max_turns: int = int(os.environ.get("AGENT_REVIEWER_MAX_TURNS", "50"))
```

- [ ] **Step 6.2: Config tests**

In `tests/test_config.py`, an `class TestConfig` anhängen:

```python
    def test_reviewer_defaults(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "t")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
        c = Config()
        assert c.max_review_rounds == 2
        assert c.reviewer_model_default == "claude-sonnet-4-6"
        assert c.reviewer_model_critical == "claude-opus-4-7"
        assert c.critical_label == "critical"
        assert c.reviewer_max_turns == 50

    def test_reviewer_overrides(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "t")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
        monkeypatch.setenv("AGENT_MAX_REVIEW_ROUNDS", "4")
        monkeypatch.setenv("AGENT_REVIEWER_MODEL", "x")
        c = Config()
        assert c.max_review_rounds == 4
        assert c.reviewer_model_default == "x"
```

- [ ] **Step 6.3: Run config tests**

```bash
python -m pytest tests/test_config.py -v
```

Expected: passed.

- [ ] **Step 6.4: Add `REVIEWER_TEMPLATE` to prompt_template.py**

In `src/prompt_template.py`, anhängen:

```python
REVIEWER_TEMPLATE = """You are a senior code reviewer. Review PR #{pr_number} for issue #{issue_number}.

## Issue
**Title:** {issue_title}

{issue_body}

## Your Job
1. Read CLAUDE.md and AGENTS.md (if present) for project conventions.
2. Inspect the PR diff:
   ```bash
   git fetch origin {branch}
   git diff origin/{base_branch}..origin/{branch}
   ```
3. For deeper inspection, use:
   ```bash
   python3 {tools_dir}/semantic_search.py "your query"
   python3 {tools_dir}/find_symbol.py SymbolName
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


def build_reviewer_prompt(issue, pr, branch: str, base_branch: str, tools_dir: str) -> str:
    """Build the reviewer prompt for a given PR."""
    return REVIEWER_TEMPLATE.format(
        pr_number=pr.number,
        issue_number=issue.number,
        issue_title=issue.title,
        issue_body=issue.body or "No description provided.",
        branch=branch,
        base_branch=base_branch,
        tools_dir=tools_dir,
    )
```

- [ ] **Step 6.5: Failing tests for `Reviewer`**

Datei `tests/test_reviewer.py` neu anlegen:

```python
"""Tests for Reviewer."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.reviewer import Reviewer, ReviewResult, parse_review_output


class TestParseReviewOutput:
    def test_parse_ok_verdict(self):
        out = """blah blah
=== REVIEW RESULT ===
VERDICT: OK
SUMMARY: All good.
=== FINDINGS ===
=== END ===
"""
        r = parse_review_output(out)
        assert r.verdict == "OK"
        assert r.summary == "All good."
        assert r.findings == []

    def test_parse_blocking_with_findings(self):
        out = """preamble
=== REVIEW RESULT ===
VERDICT: BLOCKING
SUMMARY: Two correctness bugs.
=== FINDINGS ===
- [BLOCKING] foo.py:12 — null deref — add null guard
- [NIT] bar.py:8 — naming — rename xyz
=== END ===
trailing"""
        r = parse_review_output(out)
        assert r.verdict == "BLOCKING"
        assert len(r.findings) == 2
        assert r.findings[0].severity == "BLOCKING"
        assert "null deref" in r.findings[0].text

    def test_parse_missing_block_treated_as_blocking(self):
        """If reviewer output lacks the result block, treat as BLOCKING (fail-safe)."""
        r = parse_review_output("just some text without the markers")
        assert r.verdict == "BLOCKING"
        assert "could not parse" in r.summary.lower()


class TestReviewer:
    def test_review_invokes_claude_with_correct_model(self, tmp_path):
        """Critical-label issues get the opus model; otherwise sonnet."""
        config = MagicMock()
        config.reviewer_model_default = "sonnet"
        config.reviewer_model_critical = "opus"
        config.critical_label = "critical"
        config.reviewer_max_turns = 30
        config.tools_dir = Path("/tmp/tools")

        github = MagicMock()
        claude_cls = MagicMock()
        instance = MagicMock()
        instance.execute.return_value = (
            "=== REVIEW RESULT ===\nVERDICT: OK\nSUMMARY: ok\n=== FINDINGS ===\n=== END ===",
            False,
            MagicMock(total_tokens=100, estimated_cost_usd=0.01),
        )
        claude_cls.return_value = instance

        rv = Reviewer(config=config, github=github, claude_factory=claude_cls)

        issue = MagicMock()
        issue.labels = [MagicMock(name="critical")]
        # MagicMock label objects need .name set as string
        issue.labels[0].name = "critical"
        pr = MagicMock(number=99)

        rv.review(issue=issue, pr=pr, branch="agent/issue-1", base_branch="main",
                  worktree_path=tmp_path)

        kwargs = claude_cls.call_args.kwargs
        assert kwargs["model"] == "opus"

    def test_review_posts_pr_comment(self, tmp_path):
        config = MagicMock()
        config.reviewer_model_default = "sonnet"
        config.reviewer_model_critical = "opus"
        config.critical_label = "critical"
        config.reviewer_max_turns = 30
        config.tools_dir = Path("/tmp/tools")
        github = MagicMock()
        claude_cls = MagicMock()
        instance = MagicMock()
        instance.execute.return_value = (
            "=== REVIEW RESULT ===\nVERDICT: BLOCKING\nSUMMARY: bug\n"
            "=== FINDINGS ===\n- [BLOCKING] x:1 — y — z\n=== END ===",
            False,
            MagicMock(total_tokens=100, estimated_cost_usd=0.01),
        )
        claude_cls.return_value = instance

        rv = Reviewer(config=config, github=github, claude_factory=claude_cls)
        issue = MagicMock(); issue.labels = []
        pr = MagicMock(number=99)

        result = rv.review(issue=issue, pr=pr, branch="b", base_branch="main",
                           worktree_path=tmp_path)

        assert result.verdict == "BLOCKING"
        pr.create_issue_comment.assert_called_once()
        body = pr.create_issue_comment.call_args.args[0]
        assert "BLOCKING" in body
```

- [ ] **Step 6.6: Implement `Reviewer`**

Datei `src/reviewer.py` neu anlegen:

```python
"""Reviewer role: inspects a PR via Claude Code and posts findings."""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Callable

log = logging.getLogger("agent")


@dataclass
class Finding:
    severity: str  # "BLOCKING" or "NIT"
    text: str


@dataclass
class ReviewResult:
    verdict: str  # "OK" or "BLOCKING"
    summary: str
    findings: List[Finding] = field(default_factory=list)
    raw_output: str = ""

    @property
    def has_blocking(self) -> bool:
        return self.verdict == "BLOCKING"


_RESULT_BLOCK = re.compile(
    r"=== REVIEW RESULT ===\s*\n"
    r"VERDICT:\s*(\S+)\s*\n"
    r"SUMMARY:\s*([^\n]+)\n"
    r"=== FINDINGS ===\s*\n"
    r"(.*?)"
    r"=== END ===",
    re.DOTALL,
)
_FINDING_LINE = re.compile(r"^-\s*\[(\w+)\]\s*(.+)$", re.MULTILINE)


def parse_review_output(output: str) -> ReviewResult:
    """Parse the structured trailing block from a reviewer's output."""
    m = _RESULT_BLOCK.search(output)
    if not m:
        return ReviewResult(
            verdict="BLOCKING",
            summary="Could not parse reviewer output — treating as BLOCKING.",
            raw_output=output,
        )
    verdict = m.group(1).strip().upper()
    summary = m.group(2).strip()
    findings_block = m.group(3)
    findings = [
        Finding(severity=fm.group(1).strip().upper(), text=fm.group(2).strip())
        for fm in _FINDING_LINE.finditer(findings_block)
    ]
    return ReviewResult(verdict=verdict, summary=summary, findings=findings,
                        raw_output=output)


class Reviewer:
    """Runs Claude Code in review mode against a PR diff."""

    def __init__(self, config, github, claude_factory: Callable):
        """
        Args:
            config: Config instance (for model/label settings).
            github: GitHubClient (for PR comments).
            claude_factory: Callable that returns a ClaudeCode-like object;
                            in production this is the ClaudeCode class itself.
        """
        self.config = config
        self.github = github
        self.claude_factory = claude_factory

    def _select_model(self, issue) -> str:
        labels = {(getattr(label, "name", "") or "").lower() for label in (issue.labels or [])}
        if self.config.critical_label.lower() in labels:
            return self.config.reviewer_model_critical
        return self.config.reviewer_model_default

    def review(self, issue, pr, branch: str, base_branch: str,
               worktree_path: Path) -> ReviewResult:
        """Run a review pass on `pr` and post findings as a PR comment."""
        from .prompt_template import build_reviewer_prompt

        tools_dir = str(self.config.tools_dir) if self.config.tools_dir else "tools"
        prompt = build_reviewer_prompt(
            issue=issue, pr=pr, branch=branch, base_branch=base_branch,
            tools_dir=tools_dir,
        )

        model = self._select_model(issue)
        log.info(f"Reviewer running on PR #{pr.number} with model={model}")

        claude = self.claude_factory(
            working_dir=worktree_path,
            max_turns=self.config.reviewer_max_turns,
            model=model,
        )
        output, _maxed, usage = claude.execute(prompt)
        result = parse_review_output(output)

        comment = self._format_comment(result, model)
        try:
            pr.create_issue_comment(comment)
        except Exception as e:
            log.warning(f"Failed to post reviewer comment on PR #{pr.number}: {e}")

        log.info(
            f"Review verdict: {result.verdict} ({len(result.findings)} findings, "
            f"~${usage.estimated_cost_usd:.3f})"
        )
        return result

    @staticmethod
    def _format_comment(result: ReviewResult, model: str) -> str:
        lines = [
            f"## 🤖 Automated Review — verdict: **{result.verdict}**",
            f"_Model: `{model}`_",
            "",
            result.summary,
        ]
        if result.findings:
            lines.append("")
            lines.append("### Findings")
            for f in result.findings:
                lines.append(f"- **[{f.severity}]** {f.text}")
        return "\n".join(lines)
```

- [ ] **Step 6.7: Run reviewer tests**

```bash
python -m pytest tests/test_reviewer.py -v
```

Expected: 5 passed.

- [ ] **Step 6.8: Commit**

```bash
git add src/reviewer.py src/prompt_template.py src/config.py \
        tests/test_reviewer.py tests/test_config.py
git commit -m "feat: add Reviewer role with structured output parsing

Reviewer reads PR diff, runs Claude Code with reviewer-specific prompt,
parses verdict (OK/BLOCKING) + findings, and posts a PR comment.
Model selection: opus for 'critical'-labelled issues, sonnet otherwise."
```

---

## Task 7: Worker → Reviewer iteration loop in `process_issue`

**Files:**
- Modify: `src/agent.py`
- Modify: `src/prompt_template.py`

- [ ] **Step 7.1: Add `WORKER_RETRY_TEMPLATE`**

In `src/prompt_template.py`, anhängen:

```python
WORKER_RETRY_TEMPLATE = """Reviewer found issues on your PR for issue #{issue_number}.

## Reviewer Verdict: BLOCKING
{review_summary}

## Reviewer Findings
{findings_text}

## Your Task

Address every BLOCKING finding above. NIT findings are optional but
appreciated. Use the same tools as before:
- `python3 {tools_dir}/semantic_search.py "..."` to locate code
- `python3 {tools_dir}/build_errors.py --suggest-fixes` for build issues
- `python3 {tools_dir}/smart_test.py` to run tests

After fixing, commit and push to the same branch (`{branch}`). The reviewer
will re-run automatically.

## Original Issue
{issue_title}

{issue_body}
"""


def build_retry_prompt(issue, branch: str, review, tools_dir: str) -> str:
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
    )
```

- [ ] **Step 7.2: Wire reviewer + retry loop into `_process_issue_in_worktree`**

In `src/agent.py`, am Ende von `_process_issue_in_worktree` (nach erfolgreichem `_create_or_find_pr`), vor dem `return IssueResult(success=True, ...)`, einfügen:

```python
        pr = self.github.get_pr_by_branch(branch)
        if pr is not None:
            self._run_review_loop(issue, pr, branch, worktree_path)
```

Neue Methode in `Agent`:

```python
    def _run_review_loop(self, issue, pr, branch: str, worktree_path: Path) -> None:
        """Iterate Worker → Reviewer up to max_review_rounds; tag if exhausted."""
        from .reviewer import Reviewer
        from .claude_code import ClaudeCode
        from .prompt_template import build_retry_prompt

        reviewer = Reviewer(self.config, self.github, claude_factory=ClaudeCode)
        base_branch = self.git.default_branch

        for round_num in range(1, self.config.max_review_rounds + 1):
            log.info(f"Review round {round_num}/{self.config.max_review_rounds} for PR #{pr.number}")
            result = reviewer.review(
                issue=issue, pr=pr, branch=branch,
                base_branch=base_branch, worktree_path=worktree_path,
            )
            if not result.has_blocking:
                log.info(f"Reviewer verdict OK on round {round_num} — done")
                return

            if round_num == self.config.max_review_rounds:
                log.warning(f"Max review rounds reached; flagging PR #{pr.number}")
                self._flag_for_human(issue, pr, result)
                return

            # Retry: rerun worker with reviewer findings in prompt
            tools_dir = str(self.config.tools_dir) if self.config.tools_dir else "tools"
            retry_prompt = build_retry_prompt(
                issue=issue, branch=branch, review=result, tools_dir=tools_dir,
            )
            max_turns, _, _ = self._detect_issue_complexity(issue)
            worker = ClaudeCode(working_dir=worktree_path, max_turns=max_turns)
            log.info(f"Re-running worker on round {round_num + 1}")
            output, _, _ = worker.execute(retry_prompt)

            # Push any new commits the worker produced
            self.git.commit_and_push(
                branch=branch,
                message=f"Address review feedback (round {round_num + 1})",
                base_branch=base_branch,
            )

    def _flag_for_human(self, issue, pr, result) -> None:
        """Add `needs-human` label and post escalation comment."""
        try:
            issue.add_to_labels("needs-human")
        except Exception as e:
            log.warning(f"Could not add needs-human label: {e}")
        try:
            pr.create_issue_comment(
                f"⚠️ Reached max review rounds ({self.config.max_review_rounds}) "
                f"with BLOCKING findings remaining. Last summary: {result.summary}"
            )
        except Exception as e:
            log.warning(f"Could not post escalation comment: {e}")
```

- [ ] **Step 7.3: Smoke test imports**

```bash
python -c "from src.agent import Agent; print('ok')"
```

Expected: `ok`.

- [ ] **Step 7.4: Run full test suite**

```bash
python -m pytest -v
```

Expected: all green.

- [ ] **Step 7.5: Commit**

```bash
git add src/agent.py src/prompt_template.py
git commit -m "feat: Worker→Reviewer iteration loop with max-rounds escalation

After PR creation, runs reviewer; on BLOCKING verdict, re-invokes worker
with reviewer findings in the prompt. After max_review_rounds, adds
'needs-human' label and posts escalation comment."
```

---

## Task 8: Update CLAUDE.md, README, and .env.example

**Files:**
- Modify: `CLAUDE.md`
- Modify: `README.md`
- Modify: `.env.example`

- [ ] **Step 8.1: Update CLAUDE.md project name**

In `CLAUDE.md`, ersetze (replace_all wenn möglich):
- `Connect-A-PIC-Pro` → `Lunima`
- `Connect-A-Pic-Core/` → `Lunima.Core/`  *(nur wenn Lunima diese neuen Pfade verwendet — wenn Pfade gleich blieben, nicht ändern)*
- `CAP.Avalonia/` → `Lunima.Avalonia/`  *(s.o.)*

Hinweis: ob die Verzeichnisse mit umbenannt wurden, ist offen. Wenn die Repo-Inhalte gleich blieben, nur den **Projektnamen** im einleitenden Satz korrigieren:

```
# Agent Instructions for Lunima

**NOTE:** This is an example `CLAUDE.md` file configured for **Lunima** (formerly
Connect-A-PIC-Pro; C# / Avalonia / MVVM project).
```

- [ ] **Step 8.2: Replace hardcoded tool paths in CLAUDE.md**

Suche im File: `/home/aigner/connect-a-pic-agent/`. Ersetze durch `<TOOLS_DIR>/` Platzhalter und ergänze einen Hinweis-Block am Anfang:

```
> **Tool paths:** This document references `<TOOLS_DIR>` as the absolute path to
> python-dev-tools (auto-installed by the agent). At runtime, the agent injects
> the real path into prompts; for human readers, replace `<TOOLS_DIR>` mentally.
```

- [ ] **Step 8.3: Document new env vars in `.env.example`**

In `.env.example`, am Ende anhängen:

```
# ==============================
# WORKTREES & REVIEWER (multi-role agent)
# ==============================

# Base directory for per-issue git worktrees
AGENT_WORKTREE_DIR=~/.aia-worktrees

# Reviewer settings
AGENT_MAX_REVIEW_ROUNDS=2              # Worker → Reviewer iterations before escalation
AGENT_REVIEWER_MODEL=claude-sonnet-4-6 # Default reviewer model
AGENT_REVIEWER_MODEL_CRITICAL=claude-opus-4-7  # Used when issue has 'critical' label
AGENT_CRITICAL_LABEL=critical          # Label that triggers the higher-tier reviewer
AGENT_REVIEWER_MAX_TURNS=50            # Max turns for one review pass
```

- [ ] **Step 8.4: Add "Reviewer Pipeline" section to README.md**

In `README.md`, nach dem bestehenden „How it works"-Diagramm einen neuen Abschnitt einfügen:

```markdown
## Multi-Role Pipeline (since v1.x)

Each issue runs through a Worker → Reviewer loop in an isolated git worktree:

```
GitHub Issue (label: agent-task)
       │
       ▼
[Worktree] git worktree add ~/.aia-worktrees/<repo>/<branch>/
       │
       ▼
[Worker]   Claude Code (sonnet/opus) → commit + push → open PR
       │
       ▼
[Reviewer] Claude Code (sonnet, opus for `critical` label)
           reads diff, posts structured PR comment
       │
   verdict?
       │
   ┌───┴────┐
   │        │
   OK    BLOCKING
   │        │
   │   round < max?  ──yes──► [Worker] retry with findings
   │        │ no
   │        ▼
   │   add label `needs-human`, escalate
   │
   ▼
PR ready for human merge
```

**Configuration:** see `.env.example` for `AGENT_MAX_REVIEW_ROUNDS`,
`AGENT_REVIEWER_MODEL`, `AGENT_CRITICAL_LABEL`, `AGENT_WORKTREE_DIR`.

**Cleanup:** `python main.py --cleanup-worktrees` removes worktrees for
branches without an open PR.
```

- [ ] **Step 8.5: Verify nothing breaks**

```bash
python -m pytest -v
python -c "from src.agent import Agent; print('ok')"
```

Expected: all green, `ok`.

- [ ] **Step 8.6: Commit**

```bash
git add CLAUDE.md README.md .env.example
git commit -m "docs: document multi-role pipeline and Lunima rename

CLAUDE.md: project rename Connect-A-PIC-Pro → Lunima; tool paths use
<TOOLS_DIR> placeholder. README.md: new section on Worker→Reviewer
pipeline with worktrees. .env.example: reviewer + worktree env vars."
```

---

## Self-Review Checklist (run by plan author)

- [x] Spec coverage:
  - Tools auto-install (Q5) → Task 1
  - Worktrees (request) → Tasks 3 + 4
  - Reviewer role → Tasks 5 + 6
  - Iteration loop with rounds (Q3) → Task 7
  - Reviewer model selection sonnet/opus (Q2) → Task 6 (Reviewer._select_model)
  - max_review_rounds=2 default (Q3) → Task 6 config
  - Auto worktree cleanup (Q4) → Task 4 (`--cleanup-worktrees`)
  - python-dev-tools from aignermax only (Q5) → Task 1 (`TOOLS_REPO_URL`)
  - PM role deferred (Q1) → not in this plan; documented in conversation
  - CLAUDE.md update → Task 8
- [x] No `TBD` / `TODO` / `Add appropriate error handling` placeholders.
- [x] Type consistency:
  - `tools_dir`: `Optional[Path]` on Config; passed as `str` to prompts
  - `WorktreeManager.create()` signature consistent across tasks
  - `Reviewer.review()` signature consistent: `issue, pr, branch, base_branch, worktree_path`
  - `parse_review_output` returns `ReviewResult` with `.has_blocking` property used in Task 7
- [x] All referenced helpers (`build_retry_prompt`, `parse_review_output`, `WorktreeInfo`) defined in earlier tasks.

---

## Notes for Executor

- Tests use `pytest` and existing patterns from `tests/test_config.py` (monkeypatch for env). Prefer `tmp_path` and `monkeypatch` fixtures over global state.
- The `process_issue` refactor in Task 4 is the riskiest step — read the existing 100-line method carefully, then move the body into `_process_issue_in_worktree` while keeping the `branch = self._claim_issue_and_create_branch(issue)` call in the new wrapper.
- Do NOT remove the existing self-review note in `INITIAL_TEMPLATE` ("BEFORE final commit: Review your own changes") — the new external Reviewer is additive, not a replacement.
- After Task 7, the agent.py file will exceed 1100 lines. Defer any split refactor to a follow-up plan.
