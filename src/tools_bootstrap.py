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
