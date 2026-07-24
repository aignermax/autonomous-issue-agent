"""Tests for persistent issue history (src/history.py + dashboard read)."""
from datetime import datetime, timedelta

from src.history import append_issue_history, read_issue_history, HISTORY_FILENAME


def test_roundtrip_newest_first(tmp_path):
    for n in (1, 2, 3):
        append_issue_history(
            tmp_path, number=n, title=f"t{n}", repository="o/repo",
            completed=True, pr_url=f"https://github.com/o/repo/pull/{n}",
            total_tokens=100 * n, total_cost_usd=0.5 * n, session_count=1,
        )
    recs = read_issue_history(tmp_path, limit=2)
    assert [r["number"] for r in recs] == [3, 2]
    assert recs[0]["repository"] == "o/repo"
    assert recs[0]["completed"] is True


def test_duration_from_started_at(tmp_path):
    started = (datetime.now() - timedelta(minutes=10)).isoformat()
    append_issue_history(
        tmp_path, number=7, title="t", repository="o/r",
        completed=True, started_at=started,
    )
    rec = read_issue_history(tmp_path, limit=1)[0]
    assert 590 <= rec["duration_sec"] <= 660


def test_bad_started_at_and_missing_file(tmp_path):
    assert read_issue_history(tmp_path) == []
    append_issue_history(
        tmp_path, number=8, title="t", repository="o/r",
        completed=False, started_at="not-a-date",
    )
    rec = read_issue_history(tmp_path, limit=1)[0]
    assert rec["duration_sec"] is None
    assert rec["completed"] is False


def test_corrupt_lines_are_skipped(tmp_path):
    append_issue_history(tmp_path, number=1, title="ok", repository="o/r", completed=True)
    with (tmp_path / HISTORY_FILENAME).open("a", encoding="utf-8") as fh:
        fh.write("{corrupt json\n")
    append_issue_history(tmp_path, number=2, title="ok2", repository="o/r", completed=True)
    recs = read_issue_history(tmp_path)
    assert [r["number"] for r in recs] == [2, 1]


def test_dashboard_reads_persisted_history(tmp_path):
    """Dashboard history must come from the JSONL, not from log archaeology."""
    import sys
    sys.path.insert(0, "src")
    from src.dashboard import DashboardMonitor

    sessions = tmp_path / ".sessions"
    append_issue_history(
        sessions, number=582, title="FDTD fix", repository="aignermax/Lunima",
        completed=True, pr_url="https://github.com/aignermax/Lunima/pull/743",
        total_tokens=57996, total_cost_usd=0.03, session_count=1,
        started_at=(datetime.now() - timedelta(minutes=30)).isoformat(),
    )
    monitor = DashboardMonitor(tmp_path)  # no agent.log in tmp_path
    hist = monitor.get_issue_history()
    assert len(hist) == 1
    h = hist[0]
    assert h.number == 582
    assert h.pr_url.endswith("/pull/743")
    assert h.completed is True
    assert h.repository  # formatted repo name present
    assert h.duration is not None and h.duration.total_seconds() > 0
    assert h.timestamp is not None
