"""Reviewer role: inspects a PR via Claude Code and posts findings."""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List

log = logging.getLogger("agent")


@dataclass
class Finding:
    severity: str  # "BLOCKING" or "NIT"
    text: str


@dataclass
class ReviewResult:
    verdict: str  # "OK" or "BLOCKING"
    summary: str
    findings: List[Finding] = field(default_factory=list)
    raw_output: str = ""

    @property
    def has_blocking(self) -> bool:
        return self.verdict == "BLOCKING"


_RESULT_BLOCK = re.compile(
    r"=== REVIEW RESULT ===\s*\n"
    r"VERDICT:\s*(\S+)\s*\n"
    r"SUMMARY:\s*([^\n]+)\n"
    r"=== FINDINGS ===\s*\n"
    r"(.*?)"
    r"=== END ===",
    re.DOTALL,
)
_FINDING_LINE = re.compile(r"^-\s*\[(\w+)\]\s*(.+)$", re.MULTILINE)


def parse_review_output(output: str) -> ReviewResult:
    """Parse the structured trailing block from a reviewer's output.

    Treats unparseable output as BLOCKING (fail-safe — better to escalate
    to a human than silently pass a broken review).
    """
    m = _RESULT_BLOCK.search(output)
    if not m:
        return ReviewResult(
            verdict="BLOCKING",
            summary="Could not parse reviewer output — treating as BLOCKING.",
            raw_output=output,
        )
    verdict = m.group(1).strip().upper()
    summary = m.group(2).strip()
    findings_block = m.group(3)
    findings = [
        Finding(severity=fm.group(1).strip().upper(), text=fm.group(2).strip())
        for fm in _FINDING_LINE.finditer(findings_block)
    ]
    return ReviewResult(verdict=verdict, summary=summary, findings=findings,
                        raw_output=output)


class Reviewer:
    """Runs Claude Code in review mode against a PR diff."""

    def __init__(self, config, github, claude_factory: Callable):
        """
        Args:
            config: Config instance (for model/label settings).
            github: GitHubClient (for PR comments).
            claude_factory: Callable that returns a ClaudeCode-like object;
                            in production this is the ClaudeCode class itself.
        """
        self.config = config
        self.github = github
        self.claude_factory = claude_factory

    def _select_model(self, issue) -> str:
        labels = {(getattr(label, "name", "") or "").lower() for label in (issue.labels or [])}
        if self.config.critical_label.lower() in labels:
            return self.config.reviewer_model_critical
        return self.config.reviewer_model_default

    def review(self, issue, pr, branch: str, base_branch: str,
               worktree_path: Path) -> ReviewResult:
        """Run a review pass on `pr` and post findings as a PR comment."""
        from .prompt_template import build_reviewer_prompt

        tools_dir = str(self.config.tools_dir) if self.config.tools_dir else "tools"
        tools_python = (
            str(self.config.tools_python) if self.config.tools_python else "python3"
        )
        prompt = build_reviewer_prompt(
            issue=issue, pr=pr, branch=branch, base_branch=base_branch,
            tools_dir=tools_dir, tools_python=tools_python,
        )

        model = self._select_model(issue)
        log.info(f"Reviewer running on PR #{pr.number} with model={model}")

        claude = self.claude_factory(
            working_dir=worktree_path,
            max_turns=self.config.reviewer_max_turns,
            model=model,
        )
        output, _maxed, usage = claude.execute(prompt)
        result = parse_review_output(output)

        comment = self._format_comment(result, model)
        try:
            pr.create_issue_comment(comment)
        except Exception as e:
            log.warning(f"Failed to post reviewer comment on PR #{pr.number}: {e}")

        log.info(
            f"Review verdict: {result.verdict} ({len(result.findings)} findings, "
            f"~${usage.estimated_cost_usd:.3f})"
        )
        return result

    @staticmethod
    def _format_comment(result: ReviewResult, model: str) -> str:
        lines = [
            f"## Automated Review — verdict: **{result.verdict}**",
            f"_Model: `{model}`_",
            "",
            result.summary,
        ]
        if result.findings:
            lines.append("")
            lines.append("### Findings")
            for f in result.findings:
                lines.append(f"- **[{f.severity}]** {f.text}")
        return "\n".join(lines)
