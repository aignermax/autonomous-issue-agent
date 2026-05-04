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
        assert result == tools.resolve()

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
        monkeypatch.setattr("src.tools_bootstrap.subprocess.run", lambda *a, **kw: called.append(a) or _ok())

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

        monkeypatch.setattr("src.tools_bootstrap.subprocess.run", fake_run)

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

        monkeypatch.setattr("src.tools_bootstrap.subprocess.run", fake_run)

        result = ensure_tools_installed(agent_root=tmp_path)

        assert result == (tmp_path / "tools").resolve()
        assert any("clone" in c and TOOLS_REPO_URL in c for c in run_calls)


    def test_raises_when_submodule_update_fails(self, tmp_path, monkeypatch):
        """If submodule update returns non-zero, raise RuntimeError with stderr."""
        from src.tools_bootstrap import ensure_tools_installed

        (tmp_path / "tools").mkdir()
        (tmp_path / ".gitmodules").write_text("[submodule \"tools\"]\n")

        def fake_run(cmd, **kw):
            import subprocess
            return subprocess.CompletedProcess(
                args=cmd, returncode=1, stdout="", stderr="fatal: no SSH key",
            )

        monkeypatch.setattr("src.tools_bootstrap.subprocess.run", fake_run)

        with pytest.raises(RuntimeError) as exc_info:
            ensure_tools_installed(agent_root=tmp_path)

        assert "submodule" in str(exc_info.value).lower()
        assert "fatal: no SSH key" in str(exc_info.value)


def _ok():
    """Helper: minimal CompletedProcess stand-in."""
    import subprocess
    return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
