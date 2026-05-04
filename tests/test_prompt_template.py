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
    """Test prompt rendering with tools_dir."""

    def test_initial_prompt_substitutes_tools_dir(self):
        """tools_dir placeholder is replaced with actual path."""
        prompt = build_prompt(_make_issue(), tools_dir="/opt/aia/tools")

        assert "/opt/aia/tools/semantic_search.py" in prompt
        assert "/opt/aia/tools/smart_test.py" in prompt
        assert "/opt/aia/tools/build_errors.py" in prompt
        assert "{tools_dir}" not in prompt
        assert "/home/aigner/connect-a-pic-agent" not in prompt

    def test_continuation_prompt_substitutes_tools_dir(self):
        """tools_dir placeholder is replaced in continuation template."""
        state = MagicMock()
        state.session_count = 1
        state.total_turns_used = 50
        state.branch_name = "agent/issue-42"
        state.notes = ["did X", "did Y"]

        prompt = build_prompt(_make_issue(), state=state, tools_dir="/x/tools")

        assert "/x/tools/smart_test.py" in prompt
        assert "{tools_dir}" not in prompt

    def test_initial_template_has_tools_dir_placeholder(self):
        """Source template contains placeholder, not absolute path."""
        assert "{tools_dir}" in INITIAL_TEMPLATE
        assert "/home/aigner" not in INITIAL_TEMPLATE

    def test_continuation_template_has_tools_dir_placeholder(self):
        """Continuation template contains placeholder."""
        assert "{tools_dir}" in CONTINUATION_TEMPLATE
        assert "/home/aigner" not in CONTINUATION_TEMPLATE
