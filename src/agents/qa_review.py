"""
QA-side PR reviewer using Claude Code.

Mirrors the structure of `src/reviewer.Reviewer` but is PR-centric: it
does not require an Issue object, since QA may run on PRs whose linking
issue is stale, missing, or already closed.

The class is injected into `QAAgent` via a `claude_factory` callable so
tests can swap in a fake Claude implementation without spawning a real
CLI subprocess.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Optional

from ..reviewer import ReviewResult, parse_review_output

log = logging.getLogger("agent")


class QAReviewer:
    """Run a Claude-based PR review pass on behalf of the QA agent."""

    def __init__(self, config, claude_factory: Callable):
        """
        Args:
            config: Config instance — used for model selection and tools paths.
            claude_factory: Callable returning a ClaudeCode-like object.
                            Production wiring passes the `ClaudeCode` class
                            itself; tests pass a stub.
        """
        self.config = config
        self.claude_factory = claude_factory

    def review(self, pr, branch: str, base_branch: str,
               worktree_path: Path) -> ReviewResult:
        """Run a Claude review pass on `pr`'s diff.

        Returns a `ReviewResult`. The caller is responsible for posting
        the verdict — `QAReviewer` does not touch GitHub itself, which
        keeps the comment shape unified with the mechanical verdict.
        """
        from ..prompt_template import build_qa_review_prompt

        tools_dir = str(self.config.tools_dir) if self.config.tools_dir else "tools"
        tools_python = (
            str(self.config.tools_python)
            if self.config.tools_python else "python3"
        )
        prompt = build_qa_review_prompt(
            pr=pr, branch=branch, base_branch=base_branch,
            tools_dir=tools_dir, tools_python=tools_python,
        )

        model = self._select_model(pr)
        log.info(f"[qa-review] running on PR #{pr.number} with model={model}")

        claude = self.claude_factory(
            working_dir=worktree_path,
            max_turns=self.config.reviewer_max_turns,
            model=model,
        )
        try:
            output, _maxed, usage = claude.execute(prompt)
        except Exception as e:
            # A failed review must not be silently treated as PASS — fail-safe
            # to BLOCKING so the PR doesn't get qa-passed by mistake.
            log.exception(f"[qa-review] Claude execution failed for PR #{pr.number}")
            return ReviewResult(
                verdict="BLOCKING",
                summary=f"QA review could not run: {e}",
                raw_output="",
            )

        result = parse_review_output(output)
        cost = getattr(usage, "estimated_cost_usd", 0.0)
        log.info(
            f"[qa-review] PR #{pr.number} verdict={result.verdict} "
            f"({len(result.findings)} findings, ~${cost:.3f})"
        )
        return result

    def _select_model(self, pr) -> Optional[str]:
        """Pick model: critical-tag uses upgraded model, else default."""
        labels = {(getattr(label, "name", "") or "").lower()
                  for label in (getattr(pr, "labels", []) or [])}
        if self.config.critical_label.lower() in labels:
            return self.config.reviewer_model_critical
        return self.config.reviewer_model_default
