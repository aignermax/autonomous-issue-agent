"""Test for Agent._count_tool_usage regex matching."""

import sys
import types
from unittest.mock import MagicMock


def _agent():
    """Alias used by newer tests."""
    return _make_agent()


def _make_agent():
    """Build a minimal Agent without invoking __init__ and without real deps."""
    # Stub out the github and other heavy deps before importing src.agent
    for mod_name in ("github", "github.Auth"):
        if mod_name not in sys.modules:
            sys.modules[mod_name] = types.ModuleType(mod_name)

    # Provide minimal stubs so src.agent imports cleanly
    github_mod = sys.modules["github"]
    if not hasattr(github_mod, "Github"):
        github_mod.Github = MagicMock()
    if not hasattr(github_mod, "Auth"):
        auth_mod = sys.modules.get("github.Auth") or types.ModuleType("github.Auth")
        auth_mod.Token = MagicMock()
        sys.modules["github.Auth"] = auth_mod
        github_mod.Auth = auth_mod

    from src.agent import Agent  # noqa: PLC0415
    return Agent.__new__(Agent)


class TestCountToolUsage:
    """Verify _count_tool_usage regex matches the new prompt format."""

    def test_counts_semantic_search_in_new_prompt_format(self):
        agent = _make_agent()
        output = (
            "Some text...\n"
            "python3 /home/max/Projects/autonomous-issue-agent/tools/semantic_search.py 'query'\n"
            "more text\n"
            "python3 /opt/aia/tools/semantic_search.py 'another'\n"
        )
        result = agent._count_tool_usage(output)
        assert result.get("semantic_search") == 2

    def test_counts_smart_test_in_new_prompt_format(self):
        agent = _make_agent()
        output = "python3 /any/path/tools/smart_test.py\npython3 /other/tools/smart_test.py"
        result = agent._count_tool_usage(output)
        assert result.get("smart_test") == 2

    def test_returns_empty_when_no_matches(self):
        agent = _make_agent()
        result = agent._count_tool_usage("nothing relevant here")
        assert result == {}

    def test_counts_relative_tools_path(self):
        """Regex must also match the fallback `python3 tools/...` (no leading slash)."""
        agent = _make_agent()
        output = (
            "python3 tools/semantic_search.py 'q1'\n"
            "python3 tools/smart_test.py\n"
        )
        result = agent._count_tool_usage(output)
        assert result.get("semantic_search") == 1
        assert result.get("smart_test") == 1

    def test_counts_new_install_format(self):
        """Regex must match ~/.cap-tools/venv/bin/python3 ~/.cap-tools/<tool>.py."""
        agent = _agent()
        output = (
            "/home/max/.cap-tools/venv/bin/python3 /home/max/.cap-tools/semantic_search.py 'q'\n"
            "/home/max/.cap-tools/venv/bin/python3 /home/max/.cap-tools/smart_test.py\n"
        )
        result = agent._count_tool_usage(output)
        assert result.get("semantic_search") == 1
        assert result.get("smart_test") == 1
