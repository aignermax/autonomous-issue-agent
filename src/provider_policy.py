"""Coder provider policy — which model/endpoint a coder session may use.

Shared by the coder (new issues + QA fixes) and the PR-feedback worker so the
operator policy holds everywhere a coder session starts:

  0. claudeapi label → premium Claude model on the Claude API, in every repo
     (explicit escalation; overrides everything below)
  1. forced repo     → OpenRouter (AGENT_OPENROUTER_FORCE_REPOS); overrides
     eco/complex and never falls back to Claude
  2. eco label       → cheap endpoint (Moonshot/Kimi) — only in repos cleared
     for third-party providers; ignored (warning) everywhere else
  3. complex label   → premium Claude model (auto-tier), when
     AGENT_COMPLEX_USES_CLAUDE is on
  4. OpenRouter repo → OpenRouter's Anthropic endpoint (per-repo)
  5. default         → AGENT_CODER_MODEL / CLI default

"Cleared for third-party providers" means listed in AGENT_OPENROUTER_REPOS or
AGENT_OPENROUTER_FORCE_REPOS; that clearance covers OpenRouter *and* the eco
endpoint. Every other repo is internal and its code never leaves the Claude
API. Reviewer/QA always stay on the default provider as a quality net.
"""
import logging
from typing import Iterable, Optional

log = logging.getLogger("agent")


class ProviderUnavailable(RuntimeError):
    """A repo's mandatory provider can't be used (forced repo without a key)."""


def labels_of(*items) -> set:
    """Lower-cased label names of the given issues/PRs (None entries skipped)."""
    names = set()
    for item in items:
        for label in getattr(item, "labels", None) or []:
            names.add(label.name.lower())
    return names


def _listed(repo: str, repos: Iterable[str]) -> bool:
    return bool(repo) and repo.lower() in {r.lower() for r in repos}


def _has(labels: set, tag: Optional[str]) -> bool:
    return isinstance(tag, str) and bool(tag) and tag.lower() in labels


def anthropic_provider_env(base_url: str, api_key: str, model: str) -> dict:
    """Env overrides pointing Claude Code at an Anthropic-compatible endpoint."""
    return {
        "ANTHROPIC_BASE_URL": base_url,
        "ANTHROPIC_AUTH_TOKEN": api_key,
        "ANTHROPIC_API_KEY": api_key,
        # Claude Code's auxiliary calls use a small/fast model whose
        # Anthropic id doesn't exist on third-party endpoints.
        "ANTHROPIC_MODEL": model,
        "ANTHROPIC_SMALL_FAST_MODEL": model,
    }


def is_forced(config, repo: str) -> bool:
    """True if this repo must run its coder sessions on OpenRouter."""
    return _listed(repo, config.openrouter_force_repos)


def third_party_allowed(config, repo: str) -> bool:
    """True if this repo is cleared for third-party providers (OpenRouter/eco)."""
    return _listed(repo, list(config.openrouter_repos) + list(config.openrouter_force_repos))


def check_ready(config, repo: str) -> None:
    """Raise ProviderUnavailable when the repo's mandatory provider can't run.

    Called before claiming any work, so a misconfigured forced repo is skipped
    instead of stranding a claimed issue or looping on a qa-failed PR.
    """
    if is_forced(config, repo) and not config.openrouter_api_key:
        raise ProviderUnavailable(
            f"OpenRouter is mandatory for {repo} but no key is configured "
            "(AGENT_OPENROUTER_API_KEY / AGENT_OPENROUTER_KEY_FILE); no premium fallback")


def _openrouter(config) -> tuple:
    return config.openrouter_model, anthropic_provider_env(
        config.openrouter_base_url, config.openrouter_api_key, config.openrouter_model)


def select_coder_provider(config, repo: str, labels: set, num="?") -> tuple:
    """(model, env_overrides) for a coder session, per the module-level policy."""
    if _has(labels, config.claudeapi_tag):
        log.info(f"Issue #{num} '{config.claudeapi_tag}' tag → premium Claude "
                 f"({config.premium_coder_model})")
        return config.premium_coder_model, {}

    if is_forced(config, repo):
        check_ready(config, repo)
        log.info(f"Issue #{num} forced OpenRouter → {config.openrouter_model} (repo {repo})")
        return _openrouter(config)

    if _has(labels, config.eco_tag):
        if not third_party_allowed(config, repo):
            log.warning(f"Issue #{num} has '{config.eco_tag}' tag but repo {repo or '?'} is "
                        "internal (not cleared for third-party providers) — ignoring eco")
        elif config.eco_api_key:
            log.info(f"Issue #{num} eco mode → {config.eco_model} @ {config.eco_base_url}")
            return config.eco_model, anthropic_provider_env(
                config.eco_base_url, config.eco_api_key, config.eco_model)
        else:
            log.warning(f"Issue #{num} has '{config.eco_tag}' tag but "
                        "AGENT_ECO_API_KEY is not set — trying next provider")

    if config.complex_uses_claude and _has(labels, config.complexity_tag):
        log.info(f"Issue #{num} '{config.complexity_tag}' → premium Claude "
                 f"({config.premium_coder_model}, auto-tier)")
        return config.premium_coder_model, {}

    if _listed(repo, config.openrouter_repos):
        if config.openrouter_api_key:
            log.info(f"Issue #{num} OpenRouter → {config.openrouter_model} (repo {repo})")
            return _openrouter(config)
        log.warning(f"Repo {repo} is OpenRouter-routed but no OpenRouter key is "
                    "configured — using default provider")

    return config.coder_model, {}
