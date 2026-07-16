#!/bin/bash
# Bring every workspace repo to the most-recent state the agent should
# read from. Order of preference per repo:
#   1) clone if it doesn't exist locally
#   2) `dev` branch if it exists on origin
#   3) repo's default branch (origin/HEAD)
# Then fast-forward pull so we're at the tip.
#
# Idempotent + safe to re-run before every agent start.
set -e

WORKSPACE="/mnt/c/Users/MaxAigner/akhetonics-workspace"
ENV_FILE="/mnt/c/Users/MaxAigner/autonomous-issue-agent/.env"
PY="/mnt/c/Users/MaxAigner/autonomous-issue-agent/wsl-venv/bin/python"

# Repos to sync, in `owner/repo` form so each can live under a different
# GitHub owner.
REPOS=(
  "Akhetonics/SAPPHIRE-Compiler"
  "Akhetonics/raycore-vulkan-icd"
  "Akhetonics/raycore-vulkan-layer"
  "Akhetonics/raycore-isa"
  "Akhetonics/raycore-assembler"
  "Akhetonics/phridge-blades-simulator"
  "Akhetonics/Phridge-Dispatcher"
  "Akhetonics/akhetonics-desktop"
  "aignermax/Lunima"
  # raycore-sdk intentionally kept on disk for now but no longer in the
  # agent's prompt — remove this comment + entry below to drop it entirely.
  "Akhetonics/raycore-sdk"
)

# The local clone directory name may differ from the upstream repo name
# (the original workspace was set up with capitalised "raycore-ISA").
# This map gives the on-disk name we should use, when different.
local_dir_for() {
  case "$1" in
    raycore-isa)        echo "raycore-ISA" ;;
    raycore-assembler)  echo "raycore-Assembler" ;;
    *)                  echo "$1" ;;
  esac
}

TOKEN=$("$PY" -c "from dotenv import dotenv_values; print(dotenv_values('$ENV_FILE')['GITHUB_TOKEN'])")
if [ -z "$TOKEN" ]; then
  echo "no token" >&2; exit 1
fi
export GIT_TERMINAL_PROMPT=0

sync_one() {
  local slug="$1"           # e.g. Akhetonics/SAPPHIRE-Compiler
  local owner="${slug%%/*}"
  local repo="${slug##*/}"
  local dir
  dir=$(local_dir_for "$repo")
  local target="$WORKSPACE/$dir"
  local remote_url="https://x-access-token:${TOKEN}@github.com/${owner}/${repo}.git"

  if [ ! -d "$target/.git" ]; then
    echo "[$repo] clone from $owner..."
    git clone --quiet "$remote_url" "$target"
  fi

  # Refresh the remote URL so a stale token-less or wrong-owner clone still works.
  git -C "$target" remote set-url origin "$remote_url" 2>/dev/null || true

  # Fetch everything we need to decide where dev/HEAD live.
  if ! git -C "$target" fetch --quiet --prune origin; then
    echo "[$repo] WARN: fetch failed; leaving as-is"
    return 0
  fi

  # Pick the branch to track.
  local target_branch
  if git -C "$target" ls-remote --exit-code --heads origin dev >/dev/null 2>&1; then
    target_branch="dev"
  else
    # Resolve origin/HEAD → main/master/whatever the repo's default is.
    target_branch=$(git -C "$target" symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's|^origin/||' || true)
    if [ -z "$target_branch" ]; then
      # Some clones don't have origin/HEAD set; ask the server.
      target_branch=$(git -C "$target" remote show origin 2>/dev/null | awk '/HEAD branch/ {print $NF}')
    fi
  fi

  if [ -z "$target_branch" ]; then
    echo "[$repo] WARN: could not determine target branch; leaving as-is"
    return 0
  fi

  # Drop any local dirt before switching — agent only reads from these
  # workspaces, so we can be aggressive.
  git -C "$target" reset --hard HEAD --quiet 2>/dev/null || true
  git -C "$target" clean -fd --quiet 2>/dev/null || true

  # Checkout + align with remote tip.
  git -C "$target" checkout --quiet "$target_branch" 2>/dev/null \
    || git -C "$target" checkout --quiet -b "$target_branch" "origin/$target_branch"
  git -C "$target" reset --hard --quiet "origin/$target_branch"

  local head_short
  head_short=$(git -C "$target" rev-parse --short HEAD)
  echo "[$repo] -> $target_branch @ $head_short"
}

mkdir -p "$WORKSPACE"
echo "=== sync start $(date -Iseconds) ==="

# Run in parallel (max 8 concurrent — well within reasonable git concurrency).
pids=()
for r in "${REPOS[@]}"; do
  sync_one "$r" &
  pids+=($!)
done
for p in "${pids[@]}"; do
  wait "$p" || echo "WARN: a sync_one job exited non-zero"
done

echo "=== sync done $(date -Iseconds) ==="
