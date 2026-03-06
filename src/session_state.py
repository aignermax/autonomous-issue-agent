"""
Multi-session persistence for complex, long-running tasks.

Inspired by Anthropic's autonomous coding quickstart.
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, asdict

log = logging.getLogger("agent")


@dataclass
class SessionState:
    """
    State tracking for multi-session issue implementation.

    Enables agent to resume work across multiple Claude Code sessions,
    allowing it to tackle complex tasks that exceed single-session turn limits.
    """

    issue_number: int
    branch_name: str
    started_at: str
    last_session_at: str
    total_turns_used: int
    session_count: int
    completed: bool
    pr_url: Optional[str] = None
    last_output: str = ""
    notes: list[str] = None
    total_tokens: int = 0
    total_cost_usd: float = 0.0

    def __post_init__(self):
        if self.notes is None:
            self.notes = []

    def add_note(self, note: str) -> None:
        """Add a progress note to the session."""
        timestamp = datetime.now().isoformat()
        self.notes.append(f"[{timestamp}] {note}")

    def increment_session(self, turns_used: int, tokens: int = 0, cost: float = 0.0) -> None:
        """
        Record completion of a session.

        Args:
            turns_used: Number of turns consumed
            tokens: Total tokens used
            cost: Cost in USD
        """
        self.session_count += 1
        self.total_turns_used += turns_used
        self.total_tokens += tokens
        self.total_cost_usd += cost
        self.last_session_at = datetime.now().isoformat()


class SessionManager:
    """Manages persistent session state across multiple Claude Code runs."""

    def __init__(self, session_dir: Path):
        """
        Initialize session manager.

        Args:
            session_dir: Directory to store session state files
        """
        self.session_dir = session_dir
        self.session_dir.mkdir(parents=True, exist_ok=True)

    def _get_state_file(self, issue_number: int) -> Path:
        """Get the state file path for an issue."""
        return self.session_dir / f"issue-{issue_number}.json"

    def load_state(self, issue_number: int) -> Optional[SessionState]:
        """
        Load existing session state for an issue.

        Args:
            issue_number: GitHub issue number

        Returns:
            SessionState if exists, None otherwise
        """
        state_file = self._get_state_file(issue_number)
        if not state_file.exists():
            return None

        try:
            with open(state_file, "r") as f:
                data = json.load(f)
                return SessionState(**data)
        except Exception as e:
            log.warning(f"Failed to load session state: {e}")
            return None

    def save_state(self, state: SessionState) -> None:
        """
        Save session state to disk.

        Args:
            state: SessionState to persist
        """
        state_file = self._get_state_file(state.issue_number)
        try:
            with open(state_file, "w") as f:
                json.dump(asdict(state), f, indent=2)
            log.info(f"Session state saved: {state_file}")
        except Exception as e:
            log.error(f"Failed to save session state: {e}")

    def create_state(self, issue_number: int, branch_name: str) -> SessionState:
        """
        Create new session state for an issue.

        Args:
            issue_number: GitHub issue number
            branch_name: Git branch name

        Returns:
            New SessionState
        """
        now = datetime.now().isoformat()
        state = SessionState(
            issue_number=issue_number,
            branch_name=branch_name,
            started_at=now,
            last_session_at=now,
            total_turns_used=0,
            session_count=0,
            completed=False,
        )
        state.add_note("Session created")
        return state

    def delete_state(self, issue_number: int) -> None:
        """
        Delete session state (cleanup after completion).

        Args:
            issue_number: GitHub issue number
        """
        state_file = self._get_state_file(issue_number)
        if state_file.exists():
            state_file.unlink()
            log.info(f"Session state deleted: {state_file}")

    def has_active_session(self, issue_number: int) -> bool:
        """
        Check if there's an active (incomplete) session for an issue.

        Args:
            issue_number: GitHub issue number

        Returns:
            True if active session exists
        """
        state = self.load_state(issue_number)
        return state is not None and not state.completed
