"""Tests for the PR visual-walkthrough builder (src/pr_media.py)."""
import json
from types import SimpleNamespace

from src.pr_media import (
    SECTION_END,
    SECTION_START,
    _find_source_dir,
    _load_steps,
    build_walkthrough_markdown,
    merge_walkthrough_into_body,
)
from src.prompt_template import build_prompt


# --- build_walkthrough_markdown ---------------------------------------------

def test_markdown_empty_steps_returns_blank():
    assert build_walkthrough_markdown("o", "r", "b", 1, []) == ""


def test_markdown_uses_private_safe_blob_url_and_steps():
    md = build_walkthrough_markdown(
        "Akhetonics", "akhetonics-desktop", "agent/issue-5-x", 5,
        [("01-open.png", "User opens panel"), ("02-done.png", "Result shown")],
    )
    # private-repo-safe form, NOT raw.githubusercontent
    assert "raw.githubusercontent.com" not in md
    assert ("https://github.com/Akhetonics/akhetonics-desktop/blob/agent/issue-5-x/"
            "docs/pr-media/issue-5/01-open.png?raw=true") in md
    assert "Step 1 — User opens panel" in md
    assert "Step 2 — Result shown" in md


def test_markdown_blank_caption_falls_back_to_filename():
    md = build_walkthrough_markdown("o", "r", "b", 1, [("01.png", "  ")])
    assert "Step 1 — 01.png" in md


def test_markdown_is_wrapped_in_section_markers():
    md = build_walkthrough_markdown("o", "r", "abc123", 1, [("01.png", "x")])
    assert SECTION_START in md and SECTION_END in md
    # ref (commit sha) is used in the URL, not a branch name
    assert "/blob/abc123/" in md


# --- merge_walkthrough_into_body ---------------------------------------------

def test_merge_appends_when_no_existing_section():
    body = "Automated implementation for #5\n"
    wt = build_walkthrough_markdown("o", "r", "sha1", 5, [("01.png", "a")])
    merged = merge_walkthrough_into_body(body, wt)
    assert merged.startswith("Automated implementation for #5")
    assert SECTION_START in merged


def test_merge_replaces_existing_section_in_place():
    old = build_walkthrough_markdown("o", "r", "OLDSHA", 5, [("01.png", "old")])
    new = build_walkthrough_markdown("o", "r", "NEWSHA", 5, [("01.png", "new")])
    body = "intro\n" + old + "\n---\nfooter"
    merged = merge_walkthrough_into_body(body, new)
    assert "OLDSHA" not in merged
    assert "NEWSHA" in merged
    assert merged.count(SECTION_START) == 1
    # content around the section survives
    assert merged.startswith("intro") and merged.rstrip().endswith("footer")


def test_merge_empty_walkthrough_keeps_body_untouched():
    old = build_walkthrough_markdown("o", "r", "OLDSHA", 5, [("01.png", "old")])
    body = "intro\n" + old
    assert merge_walkthrough_into_body(body, "") == body
    assert merge_walkthrough_into_body(None, "") == ""


# --- _find_source_dir ----------------------------------------------------------

def test_find_source_dir_issue_scoped_only(tmp_path):
    generic = tmp_path / "artifacts" / "ui-screenshots"
    generic.mkdir(parents=True)
    (generic / "stale.png").write_bytes(b"x")
    # generic dir must NOT be picked up (stale-screenshot contamination)
    assert _find_source_dir(tmp_path, 7) is None

    scoped = generic / "issue-7"
    scoped.mkdir()
    (scoped / "01.png").write_bytes(b"x")
    assert _find_source_dir(tmp_path, 7) == scoped


# --- _load_steps -------------------------------------------------------------

def test_load_steps_no_manifest_sorts_by_name(tmp_path):
    steps = _load_steps(tmp_path, ["02-b.png", "01-a.png"])
    assert steps == [("01-a.png", ""), ("02-b.png", "")]


def test_load_steps_list_manifest_orders_and_captions(tmp_path):
    (tmp_path / "manifest.json").write_text(json.dumps([
        {"file": "02-b.png", "caption": "second"},
        {"file": "01-a.png", "caption": "first"},
    ]), encoding="utf-8")
    steps = _load_steps(tmp_path, ["01-a.png", "02-b.png"])
    assert steps == [("02-b.png", "second"), ("01-a.png", "first")]


def test_load_steps_skips_missing_and_appends_unmentioned(tmp_path):
    (tmp_path / "manifest.json").write_text(json.dumps([
        {"file": "01-a.png", "caption": "first"},
        {"file": "99-gone.png", "caption": "missing file"},
    ]), encoding="utf-8")
    steps = _load_steps(tmp_path, ["01-a.png", "03-extra.png"])
    assert steps == [("01-a.png", "first"), ("03-extra.png", "")]


def test_load_steps_dict_manifest(tmp_path):
    (tmp_path / "manifest.json").write_text(
        json.dumps({"01-a.png": "first", "02-b.png": "second"}), encoding="utf-8")
    steps = _load_steps(tmp_path, ["01-a.png", "02-b.png"])
    assert steps == [("01-a.png", "first"), ("02-b.png", "second")]


def test_load_steps_bad_manifest_falls_back(tmp_path):
    (tmp_path / "manifest.json").write_text("{not json", encoding="utf-8")
    steps = _load_steps(tmp_path, ["01-a.png"])
    assert steps == [("01-a.png", "")]


# --- prompt instruction wiring ----------------------------------------------

def test_complex_prompt_includes_issue_scoped_screenshot_path():
    issue = SimpleNamespace(number=42, title="t", body="b")
    cpx = build_prompt(issue, complexity="COMPLEX")
    assert "artifacts/ui-screenshots/issue-42/" in cpx
    assert "manifest.json" in cpx
    # regular issues stay lean — no walkthrough instruction
    assert "artifacts/ui-screenshots" not in build_prompt(issue, complexity="REGULAR")


# --- dense PR summary ----------------------------------------------------------

def test_every_prompt_demands_pr_summary_block():
    from src.prompt_template import PR_SUMMARY_INSTRUCTION
    issue = SimpleNamespace(number=1, title="t", body="b")
    st = SimpleNamespace(session_count=2, branch_name="agent/issue-1-x",
                         notes=[], total_turns_used=5)
    for prompt in (
        build_prompt(issue, complexity="REGULAR"),
        build_prompt(issue, complexity="COMPLEX"),
        build_prompt(issue, state=st, complexity="REGULAR"),
    ):
        assert "=== PR SUMMARY ===" in prompt
    assert "DENSE" in PR_SUMMARY_INSTRUCTION


def test_extract_pr_summary_block():
    from src.prompt_template import extract_pr_summary
    out = "long chatter...\n=== PR SUMMARY ===\n- added X\n- tested Y\n=== END ===\ntrailer"
    assert extract_pr_summary(out) == "- added X\n- tested Y"


def test_extract_pr_summary_fallback_is_bounded():
    from src.prompt_template import extract_pr_summary
    out = "x" * 5000
    res = extract_pr_summary(out)
    assert res.startswith("...")
    assert len(res) <= 1210
    assert extract_pr_summary("") == ""
