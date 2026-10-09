"""Prompt files: built-ins in src/prompts, overrides in prompts/ (edited by the Control Center)."""
import importlib
import subprocess
from types import SimpleNamespace

import pytest

from src import prompt_template as pt


@pytest.fixture
def overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_PROMPTS_DIR", str(tmp_path))
    return tmp_path


def _issue():
    return SimpleNamespace(number=7, title="Fix it", body="Body", labels=[])


def _pr():
    return SimpleNamespace(number=12, title="Agent: Fix it", body="Closes #7", head=SimpleNamespace(ref="agent/issue-7"))


def test_every_builtin_prompt_file_exists_and_formats():
    assert set(pt._BUILTIN) == set(pt.PROMPT_NAMES)
    for name, text in pt._BUILTIN.items():
        assert text.strip(), name
        assert "\r" not in text, f"{name}: line endings must be normalised"


def test_builtins_match_the_previous_inline_templates():
    """Moving the templates into files must not change a single character."""
    try:
        old_src = subprocess.run(["git", "show", "0018f9b:src/prompt_template.py"], capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git history not available")
    ns = {}
    exec(compile(old_src, "old_prompt_template", "exec"), ns)
    pairs = {"coder-initial": "INITIAL_TEMPLATE", "coder-continuation": "CONTINUATION_TEMPLATE", "reviewer": "REVIEWER_TEMPLATE",
             "coder-retry": "WORKER_RETRY_TEMPLATE", "qa-review": "QA_REVIEW_TEMPLATE", "qa-fix": "QA_FIX_TEMPLATE", "pr-feedback": "PR_FEEDBACK_TEMPLATE"}
    for name, const in pairs.items():
        assert pt._BUILTIN[name] == ns[const], name


def test_override_wins(overrides):
    (overrides / "pr-feedback.md").write_text("Custom feedback rules for PR #{pr_number}", encoding="utf-8")
    out = pt.build_pr_feedback_prompt(_pr(), "agent/issue-7", "please rename", 7)
    assert out.startswith("Custom feedback rules for PR #12")


def test_broken_override_falls_back_to_builtin(overrides, caplog):
    (overrides / "pr-feedback.md").write_text("Broken {no_such_placeholder} and {unbalanced", encoding="utf-8")
    out = pt.build_pr_feedback_prompt(_pr(), "agent/issue-7", "please rename", 7)
    assert "no_such_placeholder" not in out
    assert "unusable" in caplog.text


@pytest.mark.parametrize("text", ["{pr_number.x}", "{pr_number[0]}", "{0}"])
def test_attribute_and_index_placeholders_fall_back(overrides, text):
    (overrides / "pr-feedback.md").write_text(text, encoding="utf-8")
    assert "#12" in pt.build_pr_feedback_prompt(_pr(), "agent/issue-7", "x", 7)


def test_override_that_is_a_directory_falls_back(overrides):
    (overrides / "pr-feedback.md").mkdir()
    assert "#12" in pt.build_pr_feedback_prompt(_pr(), "agent/issue-7", "x", 7)


def test_no_override_dir_uses_builtin(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_PROMPTS_DIR", str(tmp_path / "missing"))
    importlib.reload(pt)
    out = pt.build_pr_feedback_prompt(_pr(), "agent/issue-7", "please rename", 7)
    assert "#12" in out
