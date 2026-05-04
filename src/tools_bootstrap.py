"""Auto-install and detection of python-dev-tools.

We rely on the official upstream installer at
https://github.com/aignermax/python-dev-tools/blob/main/install.sh which
populates ~/.cap-tools/ with all 5 tools and a venv containing the
runtime deps (openai, python-dotenv) that semantic_search.py needs.
"""

import logging
import shutil
import subprocess
from dataclasses import dataclass
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

DEFAULT_INSTALL_DIR = Path.home() / ".cap-tools"
INSTALL_SCRIPT_URL = (
    "https://raw.githubusercontent.com/aignermax/python-dev-tools/main/install.sh"
)


@dataclass(frozen=True)
class ToolsInstall:
    """Path information returned to the agent for prompt rendering."""
    dir: Path     # absolute path to the tools directory (e.g. ~/.cap-tools)
    python: Path  # absolute path to the python interpreter to invoke tools with


def find_tools_install(install_dir: Path = DEFAULT_INSTALL_DIR) -> Optional[ToolsInstall]:
    """Return ToolsInstall if all REQUIRED_TOOLS exist in install_dir, else None.

    Prefers the venv python at install_dir/venv/bin/python3. Falls back to
    the system python3 only if the venv is missing (degraded but functional
    for tools that do not need openai).
    """
    if not install_dir.is_dir():
        return None
    for tool in REQUIRED_TOOLS:
        if not (install_dir / tool).is_file():
            return None
    venv_python = install_dir / "venv" / "bin" / "python3"
    python_path = venv_python if venv_python.is_file() else Path("python3")
    return ToolsInstall(dir=install_dir.resolve(), python=python_path)


def ensure_tools_installed(install_dir: Path = DEFAULT_INSTALL_DIR) -> ToolsInstall:
    """Install tools via the official installer if absent, then return ToolsInstall.

    Raises:
        RuntimeError: if install.sh fails or tools are still missing afterwards.
    """
    existing = find_tools_install(install_dir)
    if existing:
        log.info(f"python-dev-tools present: {existing.dir} (python: {existing.python})")
        return existing

    log.info(f"Installing python-dev-tools via {INSTALL_SCRIPT_URL}...")
    if not shutil.which("curl"):
        raise RuntimeError(
            f"curl is required to install python-dev-tools but was not found. "
            f"Install curl, then retry. Manual fix: curl -sSL {INSTALL_SCRIPT_URL} | bash"
        )
    # We pipe the script through bash. `set -e -o pipefail` is set inside the
    # script itself; here we capture combined output to surface failures.
    result = subprocess.run(
        ["bash", "-c", f"curl -fsSL {INSTALL_SCRIPT_URL} | bash"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"python-dev-tools install.sh failed (exit {result.returncode}). "
            f"stdout: {result.stdout[-500:]}\nstderr: {result.stderr[-500:]}\n"
            f"Manual fix: curl -sSL {INSTALL_SCRIPT_URL} | bash"
        )

    final = find_tools_install(install_dir)
    if not final:
        missing = [t for t in REQUIRED_TOOLS if not (install_dir / t).is_file()]
        raise RuntimeError(
            f"python-dev-tools install completed but tools missing: {missing}. "
            f"Manual fix: curl -sSL {INSTALL_SCRIPT_URL} | bash"
        )
    return final
