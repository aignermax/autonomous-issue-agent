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
