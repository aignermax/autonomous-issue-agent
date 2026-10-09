"""Operator control surface shared with the Control Center (lunima-agent-loop/control-center).

Two small JSON files in the session dir form the contract:

* ``control.json`` — written by the operator (Control Center), read here::

      {"paused": {"coder": {"until": "2026-10-10T08:00:00+02:00", "reason": "vacation"},
                  "qa": {"until": null, "reason": "debugging"}}}

  A role listed under ``paused`` skips its work cycles; ``until: null`` means
  indefinitely, an elapsed ``until`` means not paused.

* ``status-<role>.json`` — written here after every state change, read by the
  Control Center to show what each role is doing right now::

      {"role": "coder", "pid": 1234, "state": "working", "detail": {"repo": "...",
       "issue": 1480, "title": "..."}, "since": "<iso>", "updated": "<iso>"}

  ``state`` is one of ``idle``, ``working``, ``paused``.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger("agent")

CONTROL_FILE = "control.json"

_session_dir: Optional[Path] = None
_role: Optional[str] = None
_last: Optional[tuple] = None
_since: Optional[str] = None


def init(session_dir: Path, role: str) -> None:
    """Called once per process so the helpers below know where to read/write."""
    global _session_dir, _role, _last, _since
    _session_dir, _role, _last, _since = Path(session_dir), role, None, None


def _now() -> datetime:
    return datetime.now().astimezone()


def pause_reason(session_dir: Path, role: str) -> Optional[str]:
    """The pause reason if ``role`` is paused right now, else None. Never raises."""
    try:
        data = json.loads((Path(session_dir) / CONTROL_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    entry = (data.get("paused") or {}).get(role)
    if not isinstance(entry, dict):
        return None
    until = entry.get("until")
    if until:
        try:
            if datetime.fromisoformat(until) <= _now():
                return None
        except ValueError:
            pass  # unparseable end → treat as indefinite, the safe side
    return entry.get("reason") or "pausiert"


def is_paused() -> Optional[str]:
    """``pause_reason`` for the role this process runs as (after ``init``)."""
    if _session_dir is None or _role is None:
        return None
    return pause_reason(_session_dir, _role)


def report(state: str, **detail) -> None:
    """Writes ``status-<role>.json`` (atomically). Unchanged reports only bump ``updated``
    every call, so the Control Center can tell a live role from a dead one."""
    global _last, _since
    if _session_dir is None or _role is None:
        return
    key = (state, tuple(sorted((k, str(v)) for k, v in detail.items())))
    now = _now().isoformat(timespec="seconds")
    if key != _last:
        _last, _since = key, now
    payload = {"role": _role, "pid": os.getpid(), "state": state, "detail": detail, "since": _since, "updated": now}
    path = _session_dir / f"status-{_role}.json"
    tmp = path.with_suffix(".json.tmp")
    try:
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(tmp, path)
    except OSError as e:
        log.debug(f"status report failed: {e}")
