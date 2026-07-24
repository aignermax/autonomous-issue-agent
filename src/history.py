"""
Persistent issue history (.sessions/issue-history.jsonl).

The dashboard's "Recent Issues" panel used to be reconstructed by parsing
agent.log on every refresh. That broke twice: unbounded reads froze the UI
on multi-MB logs, and the bounded-tail fix silently dropped anything older
than the last ~512KB — a dashboard restart lost repo/PR/duration columns.

Instead the agent appends one compact JSON line per finished issue here;
the dashboard just reads the file (small, append-only, survives restarts).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

log = logging.getLogger("agent")

HISTORY_FILENAME = "issue-history.jsonl"


def append_issue_history(
    session_dir: Path,
    *,
    number: int,
    title: str,
    repository: str,
    completed: bool,
    pr_url: Optional[str] = None,
    total_tokens: int = 0,
    total_cost_usd: float = 0.0,
    session_count: int = 0,
    started_at: str = "",
) -> None:
    """Append one history record. Never raises — history must not break runs."""
    try:
        now = datetime.now()
        duration_sec = None
        if started_at:
            try:
                duration_sec = int(
                    (now - datetime.fromisoformat(started_at)).total_seconds())
            except (ValueError, TypeError):
                pass
        record = {
            "number": number,
            "title": title or "",
            "repository": repository or "",
            "completed": completed,
            "pr_url": pr_url,
            "total_tokens": total_tokens,
            "total_cost_usd": total_cost_usd,
            "session_count": session_count,
            "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
            "duration_sec": duration_sec,
        }
        session_dir.mkdir(parents=True, exist_ok=True)
        with (session_dir / HISTORY_FILENAME).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    except Exception as e:
        log.warning(f"Could not append issue history: {e}")


def read_issue_history(session_dir: Path, limit: int = 10) -> List[dict]:
    """Newest-first records. Tolerates a missing file and corrupt lines."""
    path = session_dir / HISTORY_FILENAME
    if not path.exists():
        return []
    records: List[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError as e:
        log.warning(f"Could not read issue history: {e}")
        return []
    return list(reversed(records))[:limit]
