"""Size-based rotation for a log file shared by several processes.

coder, qa and pr-feedback all append to the same ``agent.log``. The stdlib
``RotatingFileHandler`` assumes a single writer: after one process renames the file,
the others keep writing into the renamed one. This handler builds on
``WatchedFileHandler`` (which reopens the path when the file under it changes) and
rotates under an exclusive lock, re-checking the size inside the lock so only one
process rotates.
"""

import logging.handlers
import os
from pathlib import Path

try:  # POSIX only — the agent runs in WSL; on other systems rotation still works, unlocked
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None

_CHECK_EVERY = 100  # stat() the file every N records, not on every line


class SharedRotatingFileHandler(logging.handlers.WatchedFileHandler):
    def __init__(self, filename: str, max_bytes: int, backup_count: int, encoding: str = "utf-8"):
        super().__init__(filename, encoding=encoding, delay=False)
        self.max_bytes = max_bytes
        self.backup_count = max(1, backup_count)
        self._since_check = _CHECK_EVERY  # check on the first record (shrinks a huge legacy file)

    def emit(self, record):
        self._since_check += 1
        if self.max_bytes > 0 and self._since_check >= _CHECK_EVERY:
            self._since_check = 0
            try:
                self._maybe_rotate()
            except OSError:
                pass  # logging must never take the agent down
        super().emit(record)  # reopens the path if another process rotated it

    def _size(self) -> int:
        try:
            return os.stat(self.baseFilename).st_size
        except FileNotFoundError:
            return 0

    def _maybe_rotate(self) -> None:
        if self._size() < self.max_bytes:
            return
        lock_path = self.baseFilename + ".lock"
        with open(lock_path, "a") as lock:
            if fcntl:
                fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                if self._size() < self.max_bytes:  # another process was faster
                    return
                self._shift_backups()
            finally:
                if fcntl:
                    fcntl.flock(lock, fcntl.LOCK_UN)

    def _shift_backups(self) -> None:
        base = Path(self.baseFilename)
        oldest = base.with_name(f"{base.name}.{self.backup_count}")
        if oldest.exists():
            oldest.unlink()
        for i in range(self.backup_count - 1, 0, -1):
            src = base.with_name(f"{base.name}.{i}")
            if src.exists():
                src.rename(base.with_name(f"{base.name}.{i + 1}"))
        base.rename(base.with_name(f"{base.name}.1"))
        # our own stream now points at .1 — WatchedFileHandler.emit reopens the path


def from_env(filename: str = "agent.log") -> SharedRotatingFileHandler:
    """``AGENT_LOG_MAX_MB`` (default 50, 0 = never rotate) and ``AGENT_LOG_BACKUPS`` (default 3)."""
    max_mb = float(os.environ.get("AGENT_LOG_MAX_MB", "50"))
    backups = int(os.environ.get("AGENT_LOG_BACKUPS", "3"))
    return SharedRotatingFileHandler(filename, int(max_mb * 1024 * 1024), backups)
