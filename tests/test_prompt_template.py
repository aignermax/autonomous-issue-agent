"""Tests for prompt template rendering."""

from unittest.mock import MagicMock

from src.prompt_template import build_prompt, INITIAL_TEMPLATE, CONTINUATION_TEMPLATE


def _make_issue(number=42, title="Test issue", body="Implement X"):
    issue = MagicMock()
    issue.number = number
    issue.title = title
    issue.body = body
    return issue


class TestPromptTemplate:
    def test_initial_prompt_substitutes_tools_dir_and_python(self):
        prompt = build_prompt(
            _make_issue(),
            tools_dir="/opt/aia/tools",
            tools_python="/opt/aia/venv/bin/python3",
        )
        assert "/opt/aia/venv/bin/python3 /opt/aia/tools/semantic_search.py" in prompt
        assert "/opt/aia/venv/bin/python3 /opt/aia/tools/smart_test.py" in prompt
        assert "{tools_dir}" not in prompt
        assert "{tools_python}" not in prompt
        assert "/home/aigner/connect-a-pic-agent" not in prompt

    def test_continuation_prompt_substitutes_both(self):
        state = MagicMock()
        state.session_count = 1
        state.total_turns_used = 50
        state.branch_name = "agent/issue-42"
        state.notes = ["did X"]
        prompt = build_prompt(
            _make_issue(), state=state,
            tools_dir="/x/tools", tools_python="/x/py3",
        )
        assert "/x/py3 /x/tools/smart_test.py" in prompt
        assert "{tools_python}" not in prompt

    def test_initial_template_has_both_placeholders(self):
        assert "{tools_dir}" in INITIAL_TEMPLATE
        assert "{tools_python}" in INITIAL_TEMPLATE
        assert "/home/aigner" not in INITIAL_TEMPLATE

    def test_continuation_template_has_both_placeholders(self):
        assert "{tools_dir}" in CONTINUATION_TEMPLATE
        assert "{tools_python}" in CONTINUATION_TEMPLATE
        assert "/home/aigner" not in CONTINUATION_TEMPLATE


class TestReviewerCommentHygiene:
    def test_reviewer_prompt_contains_comment_hygiene_backstop(self):
        from src.prompt_template import REVIEWER_TEMPLATE
        assert "Comment hygiene" in REVIEWER_TEMPLATE
        assert "WHAT-comments" in REVIEWER_TEMPLATE


class TestQAReviewVisualInspection:
    """Ported from PR #6, adapted: walkthrough PNGs live in docs/pr-media
    (pr_media removes the transient artifacts/ copies before commit)."""

    def _pr(self):
        pr = MagicMock()
        pr.number = 7
        pr.title = "Add feature X"
        return pr

    def test_visual_inspection_instructions_present(self):
        from src.prompt_template import build_qa_review_prompt
        prompt = build_qa_review_prompt(self._pr(), branch="feat/x", base_branch="main")
        assert "docs/pr-media" in prompt
        assert "NO_SCREENSHOTS" in prompt
        assert "Read each PNG" in prompt
        assert "[UI]" in prompt

    def test_custom_screenshots_dir_is_honored(self):
        from src.prompt_template import build_qa_review_prompt
        prompt = build_qa_review_prompt(
            self._pr(), branch="feat/x", base_branch="main",
            screenshots_dir="custom/shots")
        assert "custom/shots" in prompt
        assert "docs/pr-media" not in prompt

    def test_no_unresolved_placeholders(self):
        import re
        from src.prompt_template import build_qa_review_prompt
        prompt = build_qa_review_prompt(self._pr(), branch="feat/x", base_branch="main")
        unresolved = re.findall(r"(?<!\{)\{[a-zA-Z_][a-zA-Z0-9_]*\}(?!\})", prompt)
        assert unresolved == [], f"Unresolved placeholders: {unresolved}"
