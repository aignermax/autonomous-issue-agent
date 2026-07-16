"""Tests for the PR-feedback agent (src/agents/pr_feedback_agent.py)."""
from datetime import datetime
from types import SimpleNamespace

from src.agents.pr_feedback_agent import (
    REPLY_MARKER,
    FeedbackState,
    PRFeedbackAgent,
    extract_feedback_report,
    extract_issue_number,
    find_trigger_comments,
    is_trigger_comment,
)
from src.prompt_template import build_pr_feedback_prompt


# --- pure helpers -------------------------------------------------------

def test_extract_issue_number_from_pr_body():
    assert extract_issue_number("Automated implementation for #515\n...", 9) == 515
    assert extract_issue_number("", 9) == 9
    assert extract_issue_number(None, 9) == 9


def test_extract_feedback_report_block():
    out = "bla bla\n=== FEEDBACK REPORT ===\n- moved button\n- added dialog\n=== END ===\n"
    assert extract_feedback_report(out) == "- moved button\n- added dialog"


def test_extract_feedback_report_fallback_tail():
    out = "x" * 2000
    rep = extract_feedback_report(out)
    assert rep.startswith("...")
    assert len(rep) <= 810
    assert extract_feedback_report("") == "(worker produced no output)"


def test_is_trigger_comment_marker_and_reply_exclusion():
    assert is_trigger_comment("@agent please move the button", "@agent")
    assert not is_trigger_comment("just a note", "@agent")
    assert not is_trigger_comment(f"{REPLY_MARKER}\n@agent echoed", "@agent")
    assert not is_trigger_comment("", "@agent")


def _c(cid, body, ts):
    return SimpleNamespace(id=cid, body=body, created_at=datetime(2026, 7, ts))


def test_find_trigger_comments_filters_and_orders():
    comments = [
        _c(3, "@agent do C", 3),
        _c(1, "@agent do A", 1),
        _c(2, "unrelated", 2),
        _c(4, f"{REPLY_MARKER} done", 4),
        _c(5, "@agent do E", 5),
    ]
    hits = find_trigger_comments(comments, "@agent", processed_ids=[1])
    assert [c.id for c in hits] == [3, 5]


# --- FeedbackState -------------------------------------------------------

def test_state_roundtrip(tmp_path):
    p = tmp_path / "state.json"
    s = FeedbackState(p)
    key = "o/r#7"
    assert s.rounds(key) == 0
    s.mark_processed(key, 11)
    s.mark_processed(key, 12)
    s.mark_processed(key, 11)  # idempotent
    assert s.rounds(key) == 2

    # fresh instance reads the same file
    s2 = FeedbackState(p)
    assert s2.processed_ids(key) == [11, 12]
    assert not s2.cap_notified(key)
    s2.set_cap_notified(key)
    assert FeedbackState(p).cap_notified(key)


def test_state_attempts_cleared_on_processed(tmp_path):
    s = FeedbackState(tmp_path / "state.json")
    assert s.bump_attempts("k", 5) == 1
    assert s.bump_attempts("k", 5) == 2
    s.mark_processed("k", 5)
    # marking processed resets the attempt counter
    assert s.bump_attempts("k", 5) == 1


def test_state_corrupt_file_starts_fresh(tmp_path):
    p = tmp_path / "state.json"
    p.write_text("{corrupt", encoding="utf-8")
    s = FeedbackState(p)
    assert s.rounds("any") == 0


# --- reply / cap ---------------------------------------------------------

def _bare_agent(max_rounds=3):
    a = PRFeedbackAgent.__new__(PRFeedbackAgent)
    a.config = SimpleNamespace(pr_feedback_max_rounds=max_rounds)
    return a


class _StubPR:
    def __init__(self):
        self.number = 42
        self.comments = []

    def create_issue_comment(self, body):
        self.comments.append(body)


def test_reply_contains_marker_report_and_walkthrough():
    a = _bare_agent()
    pr = _StubPR()
    comment = SimpleNamespace(id=99)
    a._reply(pr, comment, "- did the thing", "## 📸 Visual walkthrough\n![x](u)", True)
    body = pr.comments[0]
    assert REPLY_MARKER in body
    assert "- did the thing" in body
    assert "Visual walkthrough" in body
    # reply must never re-trigger
    assert not is_trigger_comment(body, "@agent") or "@agent" not in body


def test_reply_notes_missing_push_and_screenshots():
    a = _bare_agent()
    pr = _StubPR()
    a._reply(pr, SimpleNamespace(id=1), "report", "", False)
    body = pr.comments[0]
    assert "no new commits were pushed" in body
    assert "No UI screenshots" in body


def test_notify_cap_only_once(tmp_path):
    a = _bare_agent(max_rounds=2)
    a.state = FeedbackState(tmp_path / "s.json")
    pr = _StubPR()
    a._notify_cap(pr, "k")
    a._notify_cap(pr, "k")
    assert len(pr.comments) == 1
    assert REPLY_MARKER in pr.comments[0]


# --- prompt --------------------------------------------------------------

def test_build_pr_feedback_prompt_contents():
    pr = SimpleNamespace(number=7, title="Agent: add export")
    p = build_pr_feedback_prompt(
        pr, branch="agent/issue-5-x", comment_body="@agent make the button blue",
        issue_number=5)
    assert "PR #7" in p
    assert "agent/issue-5-x" in p
    assert "@agent make the button blue" in p
    assert "artifacts/ui-screenshots/issue-5/" in p
    assert "FEEDBACK REPORT" in p


# --- repo policy + fork handling ------------------------------------------

def test_load_project_config_from_text():
    from src.agents.agent_config import load_project_config_from_text
    cfg = load_project_config_from_text(
        "build_cmd = \"dotnet build\"\nagents_enabled = [\"coder\", \"pr-feedback\"]\n")
    assert cfg.is_agent_enabled("pr-feedback")
    assert not load_project_config_from_text("").is_agent_enabled("pr-feedback")
    # broken TOML falls back to defaults instead of raising
    assert not load_project_config_from_text("{nonsense").is_agent_enabled("pr-feedback")


def _fb_agent_for_handling(tmp_path):
    from unittest.mock import MagicMock
    a = PRFeedbackAgent.__new__(PRFeedbackAgent)
    a.config = SimpleNamespace(pr_feedback_max_rounds=3, pr_feedback_max_turns=10,
                               pr_feedback_marker="@agent", tools_dir=None,
                               tools_python=None, coder_model=None)
    a.current_repo_name = "o/r"
    a.state = FeedbackState(tmp_path / "s.json")
    a.git = MagicMock()
    a.github = MagicMock()
    a.claude_factory = MagicMock()
    return a


def test_fork_pr_is_declined_with_reply(tmp_path):
    a = _fb_agent_for_handling(tmp_path)
    pr = _StubPR()
    pr.head = SimpleNamespace(ref="feat-x", repo=SimpleNamespace(full_name="someone/fork"))
    pr.body = ""
    comment = SimpleNamespace(id=5, body="@agent do it")
    a._handle_feedback(pr, "o/r#42", comment)
    assert any("fork" in c for c in pr.comments)
    assert a.state.processed_ids("o/r#42") == [5]
    a.claude_factory.assert_not_called()


def test_disabled_policy_replies_instead_of_silent_swallow(tmp_path):
    a = _fb_agent_for_handling(tmp_path)
    pr = _StubPR()
    pr.head = SimpleNamespace(ref="feat-x", repo=SimpleNamespace(full_name="o/r"))
    pr.body = ""
    # policy read yields config without pr-feedback
    a._load_repo_policy = lambda: __import__("src.agents.agent_config", fromlist=["ProjectConfig"]).ProjectConfig()
    comment = SimpleNamespace(id=6, body="@agent do it")
    a._handle_feedback(pr, "o/r#43", comment)
    assert any("not" in c and "enabled" in c for c in pr.comments)
    assert a.state.processed_ids("o/r#43") == [6]
    a.claude_factory.assert_not_called()
