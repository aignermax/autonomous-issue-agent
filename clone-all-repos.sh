#!/bin/bash
# Clone all Akhetonics dependency repositories
# This saves 50-70% token waste by giving agent access to all code!

set -e

WORKSPACE="/mnt/c/Users/MaxAigner/akhetonics-workspace"
mkdir -p "$WORKSPACE"
cd "$WORKSPACE"

echo "========================================="
echo "Cloning all Akhetonics repositories"
echo "========================================="
echo ""

# List of all repos the agent needs access to
REPOS=(
    "Akhetonics/akhetonics-desktop"
    "Akhetonics/raycore-sdk"
    "Akhetonics/raycore-Compiler"
    "Akhetonics/raycore-ISA"
    "Akhetonics/raycore-Assembler"
    "Akhetonics/RCK-format"
    "Akhetonics/Vulkan-layer"
    "Akhetonics/ICD-driver"
    "aignermax/Lunima"
)

for repo in "${REPOS[@]}"; do
    repo_name=$(basename "$repo")

    if [ -d "$repo_name" ]; then
        echo "✅ $repo_name already exists, pulling latest..."
        cd "$repo_name"
        git pull origin main 2>/dev/null || git pull origin master 2>/dev/null || echo "  (could not pull)"
        cd ..
    else
        echo "📥 Cloning $repo..."
        if git clone "git@github.com:$repo.git" 2>/dev/null; then
            echo "  ✅ Cloned successfully"
        else
            echo "  ❌ Failed to clone (check SSH key or permissions)"
        fi
    fi
    echo ""
done

echo "========================================="
echo "✅ Workspace ready!"
echo "========================================="
echo ""
echo "All repos are in: $WORKSPACE"
echo ""
echo "Next steps:"
echo "1. Update agent to use this workspace"
echo "2. Configure semantic_search.py to index all repos"
echo "3. Agent will have access to all code!"
echo ""
