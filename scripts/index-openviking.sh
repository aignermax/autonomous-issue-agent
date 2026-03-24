#!/bin/bash
# Index Connect-A-PIC-Pro repository with OpenViking using --no-strict flag
# This allows indexing despite unsupported file types (.axaml, .csproj, .sln)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../repo" && pwd)"
RESOURCE_URI="viking://resources/connect-a-pic"

echo "🔍 Indexing Connect-A-PIC-Pro with OpenViking..."
echo "Repository: $REPO_DIR"
echo "Resource URI: $RESOURCE_URI"
echo ""

# Check if OpenViking server is running
if ! pgrep -f "openviking-server" > /dev/null; then
    echo "⚠️  OpenViking server is not running"
    echo "Starting server..."
    openviking-server &
    sleep 5
fi

# Remove existing resource if it exists
echo "🗑️  Removing existing resource (if any)..."
~/.local/bin/openviking rm "$RESOURCE_URI" 2>/dev/null || true

# Index the repository with --no-strict flag
echo "📦 Indexing repository (this may take a few minutes)..."
echo "⏳ Using --no-strict flag to allow .axaml, .csproj, .sln files"
echo ""

cd "$REPO_DIR"

# Use --no-strict to allow unsupported file types
# --wait to block until indexing is complete
time ~/.local/bin/openviking add-resource . \
    --to "$RESOURCE_URI" \
    --wait \
    --no-strict

echo ""
echo "✅ Indexing complete!"
echo ""
echo "📊 Resource statistics:"
~/.local/bin/openviking ls "$RESOURCE_URI/" -l 256 -n 10

echo ""
echo "🔍 Test search:"
~/.local/bin/openviking search "ParameterSweep" -u "$RESOURCE_URI/" -n 3

echo ""
echo "✅ OpenViking is ready for use with the autonomous agent!"
