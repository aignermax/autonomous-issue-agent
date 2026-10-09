"""Control-Center contract: per-role pause (control.json) and status heartbeat (status-<role>.json)."""
import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

from src import control


def _write_control(tmp_path, paused):
    (tmp_path / control.CONTROL_FILE).write_text(json.dumps({"paused": paused}), encoding="utf-8")


def _iso(delta_hours):
    return (datetime.now().astimezone() + timedelta(hours=delta_hours)).isoformat()


class TestPause:
    def test_no_file_means_not_paused(self, tmp_path):
        assert control.pause_reason(tmp_path, "coder") is None

    def test_indefinite_pause_for_one_role_only(self, tmp_path):
        _write_control(tmp_path, {"qa": {"until": None, "reason": "debugging"}})
        assert control.pause_reason(tmp_path, "qa") == "debugging"
        assert control.pause_reason(tmp_path, "coder") is None

    def test_elapsed_pause_is_over(self, tmp_path):
        _write_control(tmp_path, {"coder": {"until": _iso(-1), "reason": "x"}})
        assert control.pause_reason(tmp_path, "coder") is None

    def test_future_pause_holds_with_default_reason(self, tmp_path):
        _write_control(tmp_path, {"coder": {"until": _iso(+2)}})
        assert control.pause_reason(tmp_path, "coder") == "pausiert"

    def test_garbage_file_never_blocks(self, tmp_path):
        (tmp_path / control.CONTROL_FILE).write_text("{nope", encoding="utf-8")
        assert control.pause_reason(tmp_path, "coder") is None

    def test_naive_until_is_local_time_not_a_crash(self, tmp_path):
        naive = (datetime.now() + timedelta(hours=1)).replace(microsecond=0).isoformat()
        _write_control(tmp_path, {"coder": {"until": naive, "reason": "r"}})
        assert control.pause_reason(tmp_path, "coder") == "r"

    def test_malformed_shapes_never_raise(self, tmp_path):
        for payload in ([], {"paused": ["coder"]}, {"paused": {"coder": {"until": 12345}}}):
            (tmp_path / control.CONTROL_FILE).write_text(json.dumps(payload), encoding="utf-8")
            control.pause_reason(tmp_path, "coder")  # must not raise

    def test_is_paused_uses_init_role(self, tmp_path):
        _write_control(tmp_path, {"pr-feedback": {"until": None, "reason": "r"}})
        control.init(tmp_path, "pr-feedback")
        assert control.is_paused() == "r"


class TestStatusReport:
    def test_report_writes_status_and_keeps_since_while_unchanged(self, tmp_path):
        control.init(tmp_path, "coder")
        control.report("working", repo="o/r", issue=7)
        first = json.loads((tmp_path / "status-coder.json").read_text(encoding="utf-8"))
        control.report("working", repo="o/r", issue=7)
        second = json.loads((tmp_path / "status-coder.json").read_text(encoding="utf-8"))
        assert first["state"] == "working" and first["detail"] == {"repo": "o/r", "issue": 7}
        assert second["since"] == first["since"]
        control.report("idle")
        third = json.loads((tmp_path / "status-coder.json").read_text(encoding="utf-8"))
        assert third["state"] == "idle"

    def test_touch_refreshes_current_state(self, tmp_path):
        control.init(tmp_path, "qa")
        control.report("working", pr=5)
        control.touch()
        status = json.loads((tmp_path / "status-qa.json").read_text(encoding="utf-8"))
        assert status["state"] == "working" and status["detail"] == {"pr": 5}

    def test_report_without_init_is_a_noop(self, tmp_path):
        control._session_dir = None
        control.report("idle")  # must not raise


class TestSkipLabels:
    def test_find_next_issue_skips_claimed_and_escalated(self):
        from src.github_client import GitHubClient
        client = GitHubClient.__new__(GitHubClient)

        def issue(number, *labels):
            return SimpleNamespace(number=number, pull_request=None, assignees=[],
                                   labels=[SimpleNamespace(name=n) for n in labels])

        client.repo = Mock()
        client.repo.get_issues.return_value = [
            issue(1, "agent-task", "agent-running"),
            issue(2, "agent-task", "Needs-Human"),
            issue(3, "agent-task"),
        ]
        picked = client.find_next_issue("agent-task", skip_labels=["agent-running", "needs-human"])
        assert picked.number == 3
