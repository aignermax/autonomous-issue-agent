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
        monkeypatch.setattr(agent_mod, "search_repos_with_agent_prs",
                            lambda gh, org: set())
        monkeypatch.setattr(agent_mod, "search_repos_with_qa_failed",
                            lambda gh, org: set())
        monkeypatch.setattr(agent_mod, "search_manual_repos_with_label",
                            lambda gh, repos, label: set())
        monkeypatch.setenv("GITHUB_TOKEN", "t")

        agent._maybe_discover_repos()
        agent._maybe_discover_repos()  # within interval → no second search
        assert len(calls) == 1
        # hints were written by the sweep
        from src.repo_discovery import HINTS_FILENAME
        assert (tmp_path / HINTS_FILENAME).exists()

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


class TestWorkHints:
    def test_roundtrip_and_staleness(self, tmp_path):
        from src.repo_discovery import save_work_hints, load_work_hints
        save_work_hints(tmp_path, {"o/a"}, {"o/b"})
        assert load_work_hints(tmp_path, max_age_sec=999) == {"o/a", "o/b"}
        # stale hints are ignored (degrade to plain rotation)
        assert load_work_hints(tmp_path, max_age_sec=0) == set()

    def test_missing_file_is_empty(self, tmp_path):
        from src.repo_discovery import load_work_hints
        assert load_work_hints(tmp_path, max_age_sec=999) == set()


class TestSearchVariants:
    def _gh(self, names):
        from types import SimpleNamespace
        gh = MagicMock()
        gh.search_issues.return_value = [
            SimpleNamespace(repository=SimpleNamespace(full_name=n)) for n in names]
        return gh

    def test_agent_pr_query(self):
        from src.repo_discovery import search_repos_with_agent_prs
        gh = self._gh(["o/x"])
        assert search_repos_with_agent_prs(gh, "Akhetonics") == {"o/x"}
        q = gh.search_issues.call_args[0][0]
        assert "is:pr" in q and "is:open" in q and "Agent:" in q

    def test_qa_failed_query(self):
        from src.repo_discovery import search_repos_with_qa_failed
        gh = self._gh([])
        search_repos_with_qa_failed(gh, "Akhetonics")
        assert "label:qa-failed" in gh.search_issues.call_args[0][0]

    def test_manual_repo_query_and_empty_shortcut(self):
        from src.repo_discovery import search_manual_repos_with_label
        gh = self._gh(["a/l"])
        assert search_manual_repos_with_label(gh, ["a/l", "b/m"], "agent-task") == {"a/l"}
        q = gh.search_issues.call_args[0][0]
        assert "repo:a/l" in q and "repo:b/m" in q
        gh2 = MagicMock()
        assert search_manual_repos_with_label(gh2, [], "agent-task") == set()
        gh2.search_issues.assert_not_called()


class TestOrgReadAccessNote:
    def test_note_present_when_org_set(self):
        from types import SimpleNamespace
        from src.prompt_template import build_prompt
        issue = SimpleNamespace(number=1, title="t", body="b")
        p = build_prompt(issue, org_read_access="Akhetonics")
        assert "Cross-repo reference access" in p
        assert "git clone --depth 1" in p
        assert "github.com/Akhetonics/" in p
        assert "${GITHUB_TOKEN}" in p
        assert "Cross-repo" not in build_prompt(issue)
