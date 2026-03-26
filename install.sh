#!/bin/bash
# CAP Development Tools Installer
# Installs semantic search and smart test tools for Claude Code

set -e

VERSION="1.0.0"
INSTALL_DIR="$HOME/.cap-tools"
REPO_URL="https://raw.githubusercontent.com/aignermax/autonomous-issue-agent"
BRANCH="main"

echo "🔧 CAP Development Tools Installer v$VERSION"
echo ""

# Create install directory
mkdir -p "$INSTALL_DIR"

echo "📦 Installing tools to $INSTALL_DIR..."

# Download tools
curl -sSL "$REPO_URL/$BRANCH/tools/semantic_search.py" -o "$INSTALL_DIR/semantic_search.py"
curl -sSL "$REPO_URL/$BRANCH/tools/smart_test.py" -o "$INSTALL_DIR/smart_test.py"
curl -sSL "$REPO_URL/$BRANCH/tools/README.md" -o "$INSTALL_DIR/README.md"

# Make executable
chmod +x "$INSTALL_DIR/semantic_search.py"
chmod +x "$INSTALL_DIR/smart_test.py"

echo "✅ Tools installed!"
echo ""

# Check for Python dependencies
echo "🐍 Checking Python dependencies..."

if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found! Please install Python 3.8+"
    exit 1
fi

# Check if in a venv or if python-dotenv is installed globally
if python3 -c "import dotenv" 2>/dev/null; then
    echo "✅ python-dotenv found"
else
    echo "⚠️  python-dotenv not found"
    echo "   Install in your project venv: pip install python-dotenv"
fi

if python3 -c "import openai" 2>/dev/null; then
    echo "✅ openai package found"
else
    echo "⚠️  openai package not found"
    echo "   Install in your project venv: pip install openai"
fi

echo ""
echo "📝 Setup slash commands in your project:"
echo ""
echo "   cd your-project"
echo "   mkdir -p .claude/commands"
echo "   cp $INSTALL_DIR/../examples/commands/*.md .claude/commands/"
echo ""
echo "📚 Documentation: $INSTALL_DIR/README.md"
echo ""
echo "🎉 Installation complete!"
echo ""
echo "Usage:"
echo "  Semantic search: python3 $INSTALL_DIR/semantic_search.py \"query\""
echo "  Smart test:      python3 $INSTALL_DIR/smart_test.py [filter]"
echo ""
echo "Or use slash commands in Claude Code:"
echo "  /search-code <query>"
echo "  /test [filter]"
