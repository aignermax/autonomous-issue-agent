"""OpenRouter provider routing (unit) + a gated live integration test."""
import json
import os
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from tests.test_team_branch import _agent  # reuses the github stub setup


# --- config helpers ---------------------------------------------------------

def test_read_secret_inline_and_file(tmp_path):
    from src.config import _read_secret, _as_repo_list
    assert _read_secret("sk-inline", None) == "sk-inline"
    kf = tmp_path / "key.txt"
    kf.write_text("  sk-from-file\n", encoding="utf-8")
    assert _read_secret(None, str(kf)) == "sk-from-file"
    assert _read_secret(None, str(tmp_path / "missing.txt")) is None
    assert _as_repo_list("a/b, c/d ,") == ["a/b", "c/d"]


# --- _worker_provider precedence -------------------------------------------

def _issue(number=5, labels=()):
    return SimpleNamespace(number=number,
                           labels=[SimpleNamespace(name=n) for n in labels])


def _cfg(**over):
    base = dict(
        eco_tag="eco", eco_model="kimi-k2-thinking",
        eco_base_url="https://api.moonshot.ai/anthropic", eco_api_key=None,
        coder_model="claude-fable-5", claudeapi_tag="claudeapi",
        complexity_tag="complex", complex_uses_claude=True,
        openrouter_repos=["aignermax/Lunima"], openrouter_model="qwen/qwen3-coder",
        openrouter_base_url="https://openrouter.ai/api", openrouter_api_key="sk-or",
    )
    base.update(over)
    return SimpleNamespace(**base)


def _mk(repo, **over):
    a = _agent()
    a.config = _cfg(**over)
    a.current_repo_name = repo
    return a


def test_openrouter_repo_routes_coder():
    model, env = _mk("aignermax/Lunima")._worker_provider(_issue())
    assert model == "qwen/qwen3-coder"
    assert env["ANTHROPIC_BASE_URL"] == "https://openrouter.ai/api"
    assert env["ANTHROPIC_AUTH_TOKEN"] == "sk-or"
    assert env["ANTHROPIC_SMALL_FAST_MODEL"] == "qwen/qwen3-coder"


def test_non_routed_repo_uses_default():
    model, env = _mk("Akhetonics/khepri")._worker_provider(_issue())
    assert model == "claude-fable-5"
    assert env == {}


def test_eco_label_wins_over_openrouter_repo():
    a = _mk("aignermax/Lunima", eco_api_key="sk-kimi")
    model, env = a._worker_provider(_issue(labels=["eco"]))
    assert model == "kimi-k2-thinking"
    assert "moonshot" in env["ANTHROPIC_BASE_URL"]


def test_missing_openrouter_key_demotes_to_default():
    model, env = _mk("aignermax/Lunima", openrouter_api_key=None)._worker_provider(_issue())
    assert model == "claude-fable-5"
    assert env == {}


def test_repo_match_is_case_insensitive():
    model, _ = _mk("AigNerMax/Lunima")._worker_provider(_issue())
    assert model == "qwen/qwen3-coder"


def test_claudeapi_label_forces_default_over_openrouter():
    model, env = _mk("aignermax/Lunima")._worker_provider(_issue(labels=["claudeapi"]))
    assert model == "claude-fable-5"
    assert env == {}


def test_claudeapi_label_wins_over_eco_too():
    a = _mk("aignermax/Lunima", eco_api_key="sk-kimi")
    model, env = a._worker_provider(_issue(labels=["eco", "claudeapi"]))
    assert model == "claude-fable-5"
    assert env == {}


def test_complex_auto_tiers_to_claude_over_openrouter():
    model, env = _mk("aignermax/Lunima")._worker_provider(_issue(labels=["complex"]))
    assert model == "claude-fable-5"
    assert env == {}


def test_eco_wins_over_complex_autotier():
    a = _mk("aignermax/Lunima", eco_api_key="sk-kimi")
    model, env = a._worker_provider(_issue(labels=["complex", "eco"]))
    assert model == "kimi-k2-thinking"  # explicit cheap beats complex→Claude


def test_complex_autotier_can_be_disabled():
    a = _mk("aignermax/Lunima", complex_uses_claude=False)
    model, _ = a._worker_provider(_issue(labels=["complex"]))
    assert model == "qwen/qwen3-coder"  # falls through to OpenRouter


# --- live integration test (gated) -----------------------------------------

def _openrouter_key():
    inline = os.environ.get("AGENT_OPENROUTER_API_KEY")
    if inline:
        return inline.strip()
    kf = os.environ.get("AGENT_OPENROUTER_KEY_FILE",
                        "/mnt/c/Users/MaxAigner/.ssh/openrouter.txt")
    p = Path(kf)
    return p.read_text(encoding="utf-8").strip() if p.exists() else None


@pytest.mark.integration
def test_openrouter_anthropic_endpoint_live():
    """Real call: the configured model answers via OpenRouter's Anthropic
    endpoint in Anthropic message format. Skipped without a key so CI stays
    green; runs on the operator's machine (RUN_LIVE=1 to force)."""
    key = _openrouter_key()
    if not key:
        pytest.skip("no OpenRouter key configured")
    if not os.environ.get("RUN_LIVE"):
        pytest.skip("live test disabled (set RUN_LIVE=1 to run)")

    model = os.environ.get("AGENT_OPENROUTER_MODEL", "qwen/qwen3-coder")
    base = os.environ.get("AGENT_OPENROUTER_BASE_URL", "https://openrouter.ai/api")
    body = json.dumps({
        "model": model, "max_tokens": 40,
        "messages": [{"role": "user", "content": "Reply with exactly: PONG"}],
    }).encode()
    req = urllib.request.Request(
        f"{base}/v1/messages", data=body, method="POST",
        headers={"Authorization": f"Bearer {key}", "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read())
    assert data.get("type") == "message"
    assert data.get("role") == "assistant"
    text = "".join(b.get("text", "") for b in data.get("content", []))
    assert "PONG" in text.upper()
