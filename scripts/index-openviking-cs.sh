#!/bin/bash
# Selective OpenViking indexing - only C# files
# Workaround for OpenViking not supporting .axaml/.csproj

set -e

REPO_PATH="/home/aigner/connect-a-pic-agent/repo"
TEMP_INDEX_DIR="/tmp/openviking-cs-index"
OPENVIKING="${HOME}/.local/bin/openviking"

echo "📚 Selective OpenViking indexing (C# files only)"
echo ""

# Create temp directory structure with only .cs files
rm -rf "$TEMP_INDEX_DIR"
mkdir -p "$TEMP_INDEX_DIR"

echo "📁 Copying C# files to temp directory..."
cd "$REPO_PATH"

# Copy all .cs files preserving directory structure
find . -name "*.cs" -not -path "*/bin/*" -not -path "*/obj/*" -not -path "*/.vs/*" | while read file; do
    dir=$(dirname "$file")
    mkdir -p "$TEMP_INDEX_DIR/$dir"
    cp "$file" "$TEMP_INDEX_DIR/$file"
done

CS_COUNT=$(find "$TEMP_INDEX_DIR" -name "*.cs" | wc -l)
echo "✅ Copied $CS_COUNT C# files"
echo ""

echo "🔍 Indexing with OpenViking..."
cd "$TEMP_INDEX_DIR"
$OPENVIKING add-resource . --to viking://resources/connect-a-pic-cs --wait

echo ""
echo "✅ Indexing complete!"
echo "   Resource: viking://resources/connect-a-pic-cs"
echo "   Files: $CS_COUNT C# files"
echo ""
echo "ℹ️  Note: AXAML files are NOT indexed (OpenViking limitation)"
echo "   Agent will use normal Read/Grep tools for AXAML files"
echo ""
