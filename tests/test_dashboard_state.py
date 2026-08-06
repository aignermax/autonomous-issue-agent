"""Coder-state detection must survive shared-log pollution (agent.log is
written by all three roles)."""
from pathlib import Path
from unittest.mock import patch


def _monitor(tmp_path, log_text):
    (tmp_path / "agent.log").write_text(log_text, encoding="utf-8")
    import sys; sys.path.insert(0, "src")
    from dashboard import DashboardMonitor
    m = DashboardMonitor(tmp_path)
    # Pretend the coder process is up; skip real ps/psutil.
    m.get_all_agent_processes = lambda: [(123, __import__("datetime").datetime.now(), "coder")]
    return m


def test_working_survives_qa_prfeedback_flood(tmp_path):
    lines = ["2026-08-06 13:09:06,190 [INFO] Found issue #817 in aignermax/Lunima: X\n"]
    # 2000 heartbeat lines from the other two roles after the marker
    for i in range(2000):
        lines.append(f"2026-08-06 13:{i%60:02d}:00,000 [INFO] [qa] sleeping 15s ...\n")
        lines.append(f"2026-08-06 13:{i%60:02d}:01,000 [INFO] [pr-feedback] nothing to do\n")
    lines.append("2026-08-06 13:40:07,253 [INFO] Claude Code activity: files modified\n")
    m = _monitor(tmp_path, "".join(lines))
    s = m.get_agent_status()
    assert s.state == "working"
    assert s.current_issue == 817
    assert s.current_repo == "aignermax/Lunima"


def test_genuine_polling_when_coder_idle(tmp_path):
    lines = "".join(
        f"2026-08-06 13:{i%60:02d}:00,000 [INFO] [qa] sleeping 15s ...\n" for i in range(50))
    lines += "2026-08-06 13:59:00,000 [INFO] Sleeping 15s ...\n"
    m = _monitor(tmp_path, lines)
    s = m.get_agent_status()
    assert s.state == "polling"
