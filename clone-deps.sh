#!/bin/bash
# One-shot helper to clone NuGet-dependency repos into the akhetonics-workspace
# so the agent's semantic_search has a local source-code mirror to read.
# Idempotent: skips repos that already have a .git directory.
set -e

WORKSPACE="/mnt/c/Users/MaxAigner/akhetonics-workspace"
ENV_FILE="/mnt/c/Users/MaxAigner/autonomous-issue-agent/.env"
PY="/mnt/c/Users/MaxAigner/autonomous-issue-agent/wsl-venv/bin/python"

TOKEN=$("$PY" -c "from dotenv import dotenv_values; print(dotenv_values('$ENV_FILE')['GITHUB_TOKEN'])")
if [ -z "$TOKEN" ]; then
  echo "no token" >&2; exit 1
fi
echo "token length: ${#TOKEN}"

export GIT_TERMINAL_PROMPT=0
URL="https://x-access-token:${TOKEN}@github.com/Akhetonics"

clone_one() {
  local name="$1"
  local target="$WORKSPACE/$name"
  if [ -d "$target/.git" ]; then
    echo "skip $name (already cloned)"
    return 0
  fi
  echo "clone $name ..."
  git clone "${URL}/${name}.git" "$target" 2>&1 | tail -2
}

mkdir -p "$WORKSPACE"
echo "=== clone start $(date -Iseconds) ==="

clone_one SAPPHIRE-Compiler &
P1=$!
clone_one raycore-vulkan-icd &
P2=$!
clone_one raycore-vulkan-layer &
P3=$!
wait $P1 $P2 $P3

echo "=== clone done $(date -Iseconds) ==="
echo "workspace:"
ls -d "$WORKSPACE"/*/
