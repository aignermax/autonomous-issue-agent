"""
PR visual walkthrough.

Collects UI-flow screenshots the coder produced, commits them onto the PR
branch, and builds a step-by-step markdown walkthrough for the PR body so a
reviewer can see the feature without checking it out.

Screenshots are expected under `artifacts/ui-screenshots/issue-<N>/` in the
worktree (issue-scoped ONLY — a generic fallback dir would risk embedding
stale screenshots committed by an earlier, unrelated issue), with an optional
`manifest.json` describing step order + captions:

    [{"file": "01-open.png", "caption": "User opens the panel"}, ...]

(A plain {"01-open.png": "caption", ...} object is also accepted.)

Images are moved to `docs/pr-media/issue-<N>/` (the transient artifacts/
copies are removed from tree AND index in the same commit — the coder's
blanket `git add .` commit earlier in the pipeline has usually committed
them already), committed, and pushed. They are embedded via the only URL
form that renders inline in a PRIVATE repo:
`https://github.com/OWNER/REPO/blob/<REF>/PATH?raw=true`
(raw.githubusercontent.com 404s for private repos). REF is the media
commit's SHA, not the branch name — branch URLs die when the branch is
deleted on merge; commit URLs survive.

The walkthrough block is wrapped in HTML markers so later rounds (review
retries, PR-feedback rounds) can refresh it in place via
`merge_walkthrough_into_body`.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
from pathlib import Path
from typing import List, Optional, Tuple

log = logging.getLogger("agent")

SCREENSHOT_SUBDIR = Path("artifacts") / "ui-screenshots"
MANIFEST_NAME = "manifest.json"
SECTION_START = "<!-- pr-walkthrough:start -->"
SECTION_END = "<!-- pr-walkthrough:end -->"
_SECTION_RE = re.compile(
    re.escape(SECTION_START) + r".*?" + re.escape(SECTION_END), re.DOTALL
)


def build_walkthrough_markdown(
    owner: str, repo: str, ref: str, issue_number: int,
    steps: List[Tuple[str, str]],
) -> str:
    """Pure: render the walkthrough markdown block. `steps` = [(filename, caption)].

    `ref` should be a commit SHA (survives branch deletion after merge).
    Returns "" when there are no steps. Uses the private-repo-safe
    blob?raw=true URL form.
    """
    if not steps:
        return ""
    rel_dir = f"docs/pr-media/issue-{issue_number}"
    out = [
        f"\n{SECTION_START}\n",
        "\n## 📸 Visual walkthrough\n",
        "_Step-by-step of the user flow, rendered headlessly. "
        "Review here — no checkout needed._\n",
    ]
    for i, (fname, caption) in enumerate(steps, 1):
        url = f"https://github.com/{owner}/{repo}/blob/{ref}/{rel_dir}/{fname}?raw=true"
        label = caption.strip() if caption and caption.strip() else fname
        out.append(f"\n**Step {i} — {label}**\n")
        out.append(f"\n![step {i}]({url})\n")
    out.append(f"\n{SECTION_END}\n")
    return "".join(out)


def merge_walkthrough_into_body(body: Optional[str], walkthrough: str) -> str:
    """Pure: insert or refresh the marked walkthrough section in a PR body.

    - empty walkthrough → body unchanged (never wipe an existing section
      just because one round produced no screenshots)
    - existing marked section → replaced in place
    - otherwise → appended
    """
    body = body or ""
    if not walkthrough:
        return body
    if _SECTION_RE.search(body):
        return _SECTION_RE.sub(walkthrough.strip("\n"), body)
    return body.rstrip("\n") + "\n" + walkthrough


def _load_steps(media_dir: Path, png_names: List[str]) -> List[Tuple[str, str]]:
    """Order + caption the PNGs using manifest.json if present, else sort by name.

    Manifest entries pointing at missing files are skipped; PNGs not mentioned
    in the manifest are appended (sorted) with no caption so nothing is lost.
    """
    present = set(png_names)
    manifest_path = media_dir / MANIFEST_NAME
    if not manifest_path.exists():
        return [(n, "") for n in sorted(present)]

    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning(f"[pr-media] manifest.json unreadable ({e}); falling back to name sort")
        return [(n, "") for n in sorted(present)]

    steps: List[Tuple[str, str]] = []
    used = set()
    if isinstance(data, list):
        for entry in data:
            if not isinstance(entry, dict):
                continue
            fname = str(entry.get("file", "")).strip()
            if fname in present and fname not in used:
                steps.append((fname, str(entry.get("caption", ""))))
                used.add(fname)
    elif isinstance(data, dict):
        for fname in sorted(data):
            if fname in present and fname not in used:
                steps.append((fname, str(data[fname])))
                used.add(fname)

    # Any screenshots the manifest didn't mention — keep them, don't drop.
    for n in sorted(present - used):
        steps.append((n, ""))
    return steps


def _find_source_dir(worktree: Path, issue_number: int) -> Optional[Path]:
    """Issue-scoped screenshot dir only — no generic fallback (stale risk)."""
    scoped = worktree / SCREENSHOT_SUBDIR / f"issue-{issue_number}"
    if scoped.is_dir() and any(scoped.glob("*.png")):
        return scoped
    return None


def publish_walkthrough(git, repo_name: str, branch: str, issue_number: int) -> str:
    """Move screenshots into docs/, commit+push to `branch`, return markdown.

    Non-fatal by contract: on any problem (no screenshots, push failure)
    returns "" so the PR is still created — just without a walkthrough.
    Never raises.
    """
    try:
        worktree = Path(git.path)
        src = _find_source_dir(worktree, issue_number)
        if src is None:
            log.info("[pr-media] no UI screenshots found — skipping walkthrough")
            return ""

        if not repo_name or "/" not in repo_name:
            log.warning(f"[pr-media] unexpected repo_name '{repo_name}' — skipping")
            return ""
        owner, repo = repo_name.split("/", 1)

        rel_dir = Path("docs") / "pr-media" / f"issue-{issue_number}"
        dest = worktree / rel_dir
        dest.mkdir(parents=True, exist_ok=True)

        png_names: List[str] = []
        for png in sorted(src.glob("*.png")):
            shutil.copy2(png, dest / png.name)
            png_names.append(png.name)
        manifest = src / MANIFEST_NAME
        if manifest.exists():
            shutil.copy2(manifest, dest / MANIFEST_NAME)

        if not png_names:
            return ""

        steps = _load_steps(dest, png_names)

        rel_posix = rel_dir.as_posix()
        artifacts_posix = SCREENSHOT_SUBDIR.as_posix()

        # Stage the media, and de-duplicate: the coder's earlier `git add .`
        # commit usually included the raw artifacts/ copies — remove them
        # from index AND worktree in the same commit so the final tree only
        # carries docs/pr-media.
        add = git.run("add", "--", rel_posix)
        if add.returncode != 0:
            log.warning(f"[pr-media] git add failed: {add.stderr.strip()}")
            return ""
        git.run("rm", "-r", "-f", "--ignore-unmatch", "--", artifacts_posix)
        # git rm leaves untracked leftovers on disk — clear them too.
        shutil.rmtree(worktree / SCREENSHOT_SUBDIR, ignore_errors=True)

        # Locale-independent no-op detection: porcelain output is stable,
        # unlike "nothing to commit" which localizes.
        status = git.run("status", "--porcelain")
        if status.stdout.strip():
            commit = git.run(
                "commit", "-a", "-m",
                f"docs(pr-media): visual walkthrough for #{issue_number}",
            )
            if commit.returncode != 0:
                log.warning(f"[pr-media] git commit failed: {commit.stderr.strip()}")
                return ""
            push = git.run("push", "origin", branch)
            if push.returncode != 0:
                log.warning(f"[pr-media] git push failed — omitting walkthrough: {push.stderr.strip()}")
                return ""

        # Pin image URLs to the commit SHA — branch URLs 404 once the PR
        # branch is deleted on merge.
        head = git.run("rev-parse", "HEAD")
        ref = head.stdout.strip() if head.returncode == 0 and head.stdout.strip() else branch

        log.info(f"[pr-media] published {len(steps)} screenshot(s) for #{issue_number} @ {ref[:12]}")
        return build_walkthrough_markdown(owner, repo, ref, issue_number, steps)
    except Exception as e:
        log.warning(f"[pr-media] walkthrough failed (non-fatal): {e}")
        return ""
