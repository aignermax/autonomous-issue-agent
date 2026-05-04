"""Tests for tools bootstrap (install via official install.sh)."""

import subprocess
from pathlib import Path

import pytest

from src.tools_bootstrap import (
    REQUIRED_TOOLS,
    INSTALL_SCRIPT_URL,
    ToolsInstall,
    find_tools_install,
    ensure_tools_installed,
)


def _populate(install_dir: Path, with_venv: bool = True) -> None:
    """Helper: create a fake install dir with all required tools and a fake venv."""
    install_dir.mkdir(parents=True, exist_ok=True)
    for tool in REQUIRED_TOOLS:
        (install_dir / tool).write_text("")
    if with_venv:
        venv_bin = install_dir / "venv" / "bin"
        venv_bin.mkdir(parents=True, exist_ok=True)
        (venv_bin / "python3").write_text("#!/bin/bash\n")
        (venv_bin / "python3").chmod(0o755)


class TestFindToolsInstall:
    def test_returns_install_with_venv_python_when_present(self, tmp_path):
        install = tmp_path / ".cap-tools"
        _populate(install, with_venv=True)
        result = find_tools_install(install_dir=install)
        assert result is not None
        assert result.dir == install.resolve()
        assert result.python == install / "venv" / "bin" / "python3"

    def test_falls_back_to_system_python_when_venv_missing(self, tmp_path):
        install = tmp_path / ".cap-tools"
        _populate(install, with_venv=False)
        result = find_tools_install(install_dir=install)
        assert result is not None
        assert result.python == Path("python3")

    def test_returns_none_when_dir_missing(self, tmp_path):
        result = find_tools_install(install_dir=tmp_path / "nope")
        assert result is None

    def test_returns_none_when_a_tool_is_missing(self, tmp_path):
        install = tmp_path / ".cap-tools"
        install.mkdir()
        (install / "semantic_search.py").write_text("")  # only one of five
        result = find_tools_install(install_dir=install)
        assert result is None


class TestEnsureToolsInstalled:
    def test_returns_install_when_already_present(self, tmp_path, monkeypatch):
        install = tmp_path / ".cap-tools"
        _populate(install, with_venv=True)

        called = []
        monkeypatch.setattr(
            "src.tools_bootstrap.subprocess.run",
            lambda *a, **kw: called.append(a) or _ok(),
        )

        result = ensure_tools_installed(install_dir=install)
        assert result.dir == install.resolve()
        assert called == [], "should not invoke installer if tools present"

    def test_invokes_install_script_when_missing(self, tmp_path, monkeypatch):
        install = tmp_path / ".cap-tools"
        run_calls = []

        def fake_run(cmd, **kw):
            run_calls.append(cmd)
            # After the install script runs, simulate it populating the dir.
            _populate(install, with_venv=True)
            return _ok()

        monkeypatch.setattr("src.tools_bootstrap.subprocess.run", fake_run)
        result = ensure_tools_installed(install_dir=install)

        assert result.dir == install.resolve()
        assert any("curl" in " ".join(c) and INSTALL_SCRIPT_URL in " ".join(c)
                   for c in run_calls), "expected curl + install URL in invoked command"

    def test_raises_when_installer_returns_nonzero(self, tmp_path, monkeypatch):
        install = tmp_path / ".cap-tools"

        def fake_run(cmd, **kw):
            return subprocess.CompletedProcess(
                args=cmd, returncode=1, stdout="", stderr="permission denied",
            )

        monkeypatch.setattr("src.tools_bootstrap.subprocess.run", fake_run)
        with pytest.raises(RuntimeError) as exc_info:
            ensure_tools_installed(install_dir=install)
        assert "install.sh failed" in str(exc_info.value)
        assert "permission denied" in str(exc_info.value)

    def test_raises_when_tools_missing_after_install(self, tmp_path, monkeypatch):
        install = tmp_path / ".cap-tools"

        def fake_run(cmd, **kw):
            # Returns success but does NOT populate install dir.
            return _ok()

        monkeypatch.setattr("src.tools_bootstrap.subprocess.run", fake_run)
        with pytest.raises(RuntimeError) as exc_info:
            ensure_tools_installed(install_dir=install)
        assert "tools missing" in str(exc_info.value).lower()


def _ok():
    return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
