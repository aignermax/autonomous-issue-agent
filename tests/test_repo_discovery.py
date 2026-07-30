"""Tests for org-wide repo auto-discovery (src/repo_discovery.py)."""
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

from src.repo_discovery import (
    RepoRegistry,
    effective_repo_names,
    search_repos_with_label,
)


class TestRepoRegistry:
    def test_update_adds_and_refreshes(self, tmp_path):
        reg = RepoRegistry(tmp_path)
        added = reg.update({"Akhetonics/a", "Akhetonics/b"})
        assert sorted(added) == ["Akhetonics/a", "Akhetonics/b"]
        # second sweep: nothing new, but last_seen refreshed
        assert reg.update({"Akhetonics/a"}) == []
        # persists across instances
        assert set(RepoRegistry(tmp_path).active_repos(8)) == {
            "Akhetonics/a", "Akhetonics/b"}

    def test_expiry_prunes_stale_repos(self, tmp_path):
        reg = RepoRegistry(tmp_path)
        old = datetime.now() - timedelta(days=9)
        reg.update({"Akhetonics/stale"}, now=old)
        reg.update({"Akhetonics/fresh"})
        assert reg.active_repos(8) == ["Akhetonics/fresh"]
        # pruned from the store, not just filtered
        assert "Akhetonics/stale" not in reg._data

    def test_remove(self, tmp_path):
        reg = RepoRegistry(tmp_path)
        reg.update({"Akhetonics/gone"})
        reg.remove("Akhetonics/gone")
        assert reg.active_repos(8) == []

    def test_corrupt_file_starts_fresh(self, tmp_path):
        (tmp_path / "discovered-repos.json").write_text("{broken", encoding="utf-8")
        assert RepoRegistry(tmp_path).active_repos(8) == []


class TestEffectiveRepoNames:
    def _config(self, tmp_path, org="Akhetonics"):
        return SimpleNamespace(
            repo_names=["Akhetonics/manual", "aignermax/Lunima"],
            discovery_org=org,
            discovery_expiry_days=8,
            session_dir=tmp_path,
        )

    def test_merges_manual_and_discovered(self, tmp_path):
        RepoRegistry(tmp_path).update({"Akhetonics/auto"})
        repos = effective_repo_names(self._config(tmp_path))
        assert repos == ["Akhetonics/manual", "aignermax/Lunima", "Akhetonics/auto"]

    def test_dedupes_case_insensitively(self, tmp_path):
        RepoRegistry(tmp_path).update({"akhetonics/MANUAL"})
        repos = effective_repo_names(self._config(tmp_path))
        assert repos == ["Akhetonics/manual", "aignermax/Lunima"]

    def test_disabled_org_returns_manual_only(self, tmp_path):
        RepoRegistry(tmp_path).update({"Akhetonics/auto"})
        repos = effective_repo_names(self._config(tmp_path, org=""))
        assert repos == ["Akhetonics/manual", "aignermax/Lunima"]


class TestSearch:
    def test_search_collects_unique_repos(self):
        gh = MagicMock()
        gh.search_issues.return_value = [
            SimpleNamespace(repository=SimpleNamespace(full_name="Akhetonics/x")),
            SimpleNamespace(repository=SimpleNamespace(full_name="Akhetonics/x")),
            SimpleNamespace(repository=SimpleNamespace(full_name="Akhetonics/y")),
        ]
        repos = search_repos_with_label(gh, "Akhetonics", "agent-task")
        assert repos == {"Akhetonics/x", "Akhetonics/y"}
        query = gh.search_issues.call_args[0][0]
        assert "org:Akhetonics" in query
        assert 'label:"agent-task"' in query
        assert "is:open" in query


class TestDiscoveryThrottle:
    def test_coder_discovery_respects_interval(self, tmp_path, monkeypatch):
        from tests.test_team_branch import _agent
        agent = _agent()
        agent.config = SimpleNamespace(
            discovery_org="Akhetonics", discovery_interval_sec=1800,
            discovery_expiry_days=8, issue_label="agent-task",
            repo_names=[], session_dir=tmp_path)
        agent._last_discovery = 0.0

        calls = []
        import src.agent as agent_mod
        monkeypatch.setattr(agent_mod, "search_repos_with_label",
                            lambda gh, org, label: calls.append(1) or set())
        monkeypatch.setenv("GITHUB_TOKEN", "t")

        agent._maybe_discover_repos()
        agent._maybe_discover_repos()  # within interval → no second search
        assert len(calls) == 1

    def test_discovery_errors_are_swallowed(self, tmp_path, monkeypatch):
        from tests.test_team_branch import _agent
        agent = _agent()
        agent.config = SimpleNamespace(
            discovery_org="Akhetonics", discovery_interval_sec=0,
            discovery_expiry_days=8, issue_label="agent-task",
            repo_names=[], session_dir=tmp_path)
        agent._last_discovery = 0.0
        import src.agent as agent_mod

        def boom(gh, org, label):
            raise RuntimeError("api down")
        monkeypatch.setattr(agent_mod, "search_repos_with_label", boom)
        monkeypatch.setenv("GITHUB_TOKEN", "t")
        agent._maybe_discover_repos()  # must not raise
