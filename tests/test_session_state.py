"""
Unit tests for session state management.
"""

import json
import tempfile
from pathlib import Path
from datetime import datetime

import pytest

from src.session_state import SessionState, SessionManager


class TestSessionState:
    """Test SessionState dataclass."""

    def test_create_session_state(self):
        """Test creating a new session state."""
        state = SessionState(
            issue_number=42,
            branch_name="agent/issue-42-123",
            started_at="2026-03-05T20:00:00",
            last_session_at="2026-03-05T20:00:00",
            total_turns_used=0,
            session_count=0,
            completed=False,
        )

        assert state.issue_number == 42
        assert state.branch_name == "agent/issue-42-123"
        assert state.session_count == 0
        assert state.completed is False
        assert state.notes == []

    def test_add_note(self):
        """Test adding notes to session."""
        state = SessionState(
            issue_number=42,
            branch_name="test",
            started_at="2026-03-05T20:00:00",
            last_session_at="2026-03-05T20:00:00",
            total_turns_used=0,
            session_count=0,
            completed=False,
        )

        state.add_note("First note")
        state.add_note("Second note")

        assert len(state.notes) == 2
        assert "First note" in state.notes[0]
        assert "Second note" in state.notes[1]

    def test_increment_session(self):
        """Test incrementing session count."""
        state = SessionState(
            issue_number=42,
            branch_name="test",
            started_at="2026-03-05T20:00:00",
            last_session_at="2026-03-05T20:00:00",
            total_turns_used=0,
            session_count=0,
            completed=False,
        )

        state.increment_session(300)

        assert state.session_count == 1
        assert state.total_turns_used == 300

        state.increment_session(150)

        assert state.session_count == 2
        assert state.total_turns_used == 450


class TestSessionManager:
    """Test SessionManager."""

    @pytest.fixture
    def temp_session_dir(self):
        """Create temporary session directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_create_and_save_state(self, temp_session_dir):
        """Test creating and saving session state."""
        manager = SessionManager(temp_session_dir)
        state = manager.create_state(42, "agent/issue-42-123")

        assert state.issue_number == 42
        assert state.session_count == 0

        manager.save_state(state)

        # Verify file was created
        state_file = temp_session_dir / "issue-42.json"
        assert state_file.exists()

        # Verify content
        with open(state_file) as f:
            data = json.load(f)
            assert data["issue_number"] == 42
            assert data["branch_name"] == "agent/issue-42-123"

    def test_load_state(self, temp_session_dir):
        """Test loading existing state."""
        manager = SessionManager(temp_session_dir)

        # Create and save
        state = manager.create_state(42, "agent/issue-42-123")
        state.add_note("Test note")
        state.increment_session(300)
        manager.save_state(state)

        # Load
        loaded = manager.load_state(42)

        assert loaded is not None
        assert loaded.issue_number == 42
        assert loaded.session_count == 1
        assert loaded.total_turns_used == 300
        assert len(loaded.notes) > 0

    def test_load_nonexistent_state(self, temp_session_dir):
        """Test loading state that doesn't exist."""
        manager = SessionManager(temp_session_dir)
        state = manager.load_state(999)

        assert state is None

    def test_delete_state(self, temp_session_dir):
        """Test deleting state."""
        manager = SessionManager(temp_session_dir)

        # Create and save
        state = manager.create_state(42, "test")
        manager.save_state(state)

        state_file = temp_session_dir / "issue-42.json"
        assert state_file.exists()

        # Delete
        manager.delete_state(42)
        assert not state_file.exists()

    def test_has_active_session(self, temp_session_dir):
        """Test checking for active session."""
        manager = SessionManager(temp_session_dir)

        # No session
        assert not manager.has_active_session(42)

        # Create active session
        state = manager.create_state(42, "test")
        manager.save_state(state)

        assert manager.has_active_session(42)

        # Complete session
        state.completed = True
        manager.save_state(state)

        assert not manager.has_active_session(42)
