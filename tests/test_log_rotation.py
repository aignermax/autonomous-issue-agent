"""Shared log rotation: several writers, one file, bounded size."""
import logging

from src import log_rotation
from src.log_rotation import SharedRotatingFileHandler


def _logger(name, handler):
    lg = logging.getLogger(name)
    lg.handlers = [handler]
    lg.propagate = False
    lg.setLevel(logging.INFO)
    return lg


def _write(lg, n, text="x" * 200):
    for _ in range(n):
        lg.info(text)


def test_rotates_and_keeps_backup_count(tmp_path, monkeypatch):
    monkeypatch.setattr(log_rotation, "_CHECK_EVERY", 1)
    path = tmp_path / "agent.log"
    h = SharedRotatingFileHandler(str(path), max_bytes=4_000, backup_count=2)
    lg = _logger("rot-a", h)
    _write(lg, 200)
    h.close()
    names = sorted(p.name for p in tmp_path.iterdir() if p.name.startswith("agent.log") and not p.name.endswith(".lock"))
    assert names == ["agent.log", "agent.log.1", "agent.log.2"]
    assert path.stat().st_size < 4_000 + 400


def test_two_writers_share_the_file_after_rotation(tmp_path, monkeypatch):
    """The second process must follow the rename, not keep writing into agent.log.1."""
    monkeypatch.setattr(log_rotation, "_CHECK_EVERY", 1)
    path = tmp_path / "agent.log"
    a = _logger("rot-b1", SharedRotatingFileHandler(str(path), max_bytes=3_000, backup_count=3))
    b = _logger("rot-b2", SharedRotatingFileHandler(str(path), max_bytes=3_000, backup_count=3))
    _write(a, 30)            # a rotates
    b.info("from-b-after-rotation")
    for lg in (a, b):
        for h in lg.handlers:
            h.close()
    assert "from-b-after-rotation" in path.read_text(encoding="utf-8")


def test_huge_legacy_file_is_rotated_on_first_record(tmp_path):
    path = tmp_path / "agent.log"
    path.write_text("old\n" * 5_000, encoding="utf-8")
    h = SharedRotatingFileHandler(str(path), max_bytes=1_000, backup_count=3)
    lg = _logger("rot-c", h)
    lg.info("first line after upgrade")
    h.close()
    assert (tmp_path / "agent.log.1").exists()
    assert path.read_text(encoding="utf-8").strip().endswith("first line after upgrade")


def test_garbage_settings_fall_back_to_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_LOG_MAX_MB", "50MB")
    monkeypatch.setenv("AGENT_LOG_BACKUPS", "3.0")
    h = log_rotation.from_env(str(tmp_path / "agent.log"))
    assert h.max_bytes == 50 * 1024 * 1024 and h.backup_count == 3
    h.close()


def test_dashboard_tail_reads_across_rotation(tmp_path):
    from src.dashboard import tail_lines_rotated
    (tmp_path / "agent.log.1").write_text("Found issue #7\nlater\n", encoding="utf-8")
    (tmp_path / "agent.log").write_text("after rotation\n", encoding="utf-8")
    lines = [l.strip() for l in tail_lines_rotated(tmp_path / "agent.log", 100, max_bytes=10_000)]
    assert lines == ["Found issue #7", "later", "after rotation"]


def test_zero_disables_rotation(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_LOG_MAX_MB", "0")
    h = log_rotation.from_env(str(tmp_path / "agent.log"))
    lg = _logger("rot-d", h)
    _write(lg, 50)
    h.close()
    assert not (tmp_path / "agent.log.1").exists()
