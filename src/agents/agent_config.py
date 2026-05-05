"""
Per-project configuration loader.

Reads `.agent.toml` from a target repository's root and exposes
build/test commands plus agent opt-ins. Falls back to safe defaults
when the file is missing so existing repositories keep working.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

log = logging.getLogger("agent")


# Python 3.11+ has tomllib in stdlib. We fall back to tomli if available
# but do not declare it as a hard dependency.
if sys.version_info >= (3, 11):
    import tomllib as _toml
else:  # pragma: no cover - exercised only on older interpreters
    try:
        import tomli as _toml  # type: ignore[import-not-found]
    except ImportError:
        _toml = None  # type: ignore[assignment]


CONFIG_FILENAME = ".agent.toml"


@dataclass
class ProjectConfig:
    """Per-repository configuration read from `.agent.toml`."""

    build_cmd: str = ""
    test_cmd: str = ""
    ui_test_cmd: str = ""
    tech_stack: list[str] = field(default_factory=list)
    agents_enabled: list[str] = field(default_factory=lambda: ["coder"])
    # Optional: command timeout in seconds for build/test runs.
    command_timeout_sec: int = 1800

    @property
    def has_build(self) -> bool:
        return bool(self.build_cmd.strip())

    @property
    def has_tests(self) -> bool:
        return bool(self.test_cmd.strip())

    @property
    def has_ui_tests(self) -> bool:
        return bool(self.ui_test_cmd.strip())

    def is_agent_enabled(self, role: str) -> bool:
        return role in self.agents_enabled


def load_project_config(repo_root: Path) -> ProjectConfig:
    """Load `.agent.toml` from a repository root, returning defaults if absent."""
    config_path = repo_root / CONFIG_FILENAME
    if not config_path.exists():
        log.info(f"No {CONFIG_FILENAME} in {repo_root} — using defaults")
        return ProjectConfig()

    if _toml is None:
        log.warning(
            f"Found {config_path} but no TOML parser available "
            "(need Python 3.11+ or `tomli` installed). Using defaults."
        )
        return ProjectConfig()

    try:
        with config_path.open("rb") as fh:
            raw = _toml.load(fh)
    except Exception as e:
        log.error(f"Failed to parse {config_path}: {e}. Using defaults.")
        return ProjectConfig()

    return ProjectConfig(
        build_cmd=str(raw.get("build_cmd", "")).strip(),
        test_cmd=str(raw.get("test_cmd", "")).strip(),
        ui_test_cmd=str(raw.get("ui_test_cmd", "")).strip(),
        tech_stack=_as_str_list(raw.get("tech_stack", [])),
        agents_enabled=_as_str_list(raw.get("agents_enabled", ["coder"])) or ["coder"],
        command_timeout_sec=int(raw.get("command_timeout_sec", 1800)),
    )


def _as_str_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
    if isinstance(value, Iterable):
        return [str(v).strip() for v in value if str(v).strip()]
    return []
