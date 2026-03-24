#!/bin/bash
# OpenViking Setup for Autonomous Issue Agent
# Automatically sets up OpenViking for Claude Code integration

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
REPO_PATH="$PROJECT_ROOT/repo"

echo "🚀 OpenViking Setup for Autonomous Issue Agent"
echo ""

# Check if .env exists and has OpenAI key
if [ ! -f "$PROJECT_ROOT/.env" ]; then
    echo "❌ Error: .env file not found"
    echo "Please create .env with OPENAI_API_KEY"
    exit 1
fi

# Source .env to get API key
source "$PROJECT_ROOT/.env"

if [ -z "$OPENAI_API_KEY" ]; then
    echo "❌ Error: OPENAI_API_KEY not set in .env"
    echo ""
    echo "Add to .env:"
    echo "  OPENAI_API_KEY=sk-proj-..."
    exit 1
fi

echo "✅ Found OpenAI API key in .env"
echo ""

# Check if OpenViking is already installed
if command -v openviking &> /dev/null; then
    echo "✅ OpenViking already installed"
else
    echo "📦 Installing OpenViking..."

    # Install pipx if needed
    if ! command -v pipx &> /dev/null; then
        echo "   Installing pipx first..."
        if [[ "$OSTYPE" == "linux-gnu"* ]]; then
            sudo apt update && sudo apt install -y pipx
        elif [[ "$OSTYPE" == "darwin"* ]]; then
            brew install pipx
        fi
        pipx ensurepath
    fi

    # Install OpenViking
    pipx install openviking --force
    echo "✅ OpenViking installed"
fi

echo ""
echo "⚙️  Configuring OpenViking..."

# Create config directory
mkdir -p ~/.openviking

# Create OpenViking config
cat > ~/.openviking/ov.conf <<EOF
{
  "storage": {
    "workspace": "$HOME/.openviking/workspace"
  },
  "log": {
    "level": "INFO",
    "output": "stdout"
  },
  "embedding": {
    "dense": {
      "api_base": "https://api.openai.com/v1",
      "api_key": "$OPENAI_API_KEY",
      "provider": "openai",
      "dimension": 1536,
      "model": "text-embedding-3-small"
    },
    "max_concurrent": 10
  },
  "vlm": {
    "api_base": "https://api.openai.com/v1",
    "api_key": "$OPENAI_API_KEY",
    "provider": "openai",
    "model": "gpt-4o-mini"
  }
}
EOF

# Create CLI config
cat > ~/.openviking/ovcli.conf <<EOF
{
  "url": "http://localhost:1933"
}
EOF

echo "✅ Config created"
echo ""

# Check if repo is already indexed
OPENVIKING_CMD="${HOME}/.local/bin/openviking"

if $OPENVIKING_CMD list-resources 2>/dev/null | grep -q "viking://resources/connect-a-pic"; then
    echo "✅ Repo already indexed"
else
    echo "📚 Indexing Connect-A-PIC-Pro codebase..."
    echo "   This will take ~30-60 seconds and cost ~€0.003..."

    cd "$REPO_PATH"
    $OPENVIKING_CMD add-resource . --to viking://resources/connect-a-pic --wait

    echo "✅ Codebase indexed"
fi

echo ""
echo "🔧 Creating MCP server files..."

# Copy MCP server files from Connect-A-PIC-Pro repo
MCP_DIR="$PROJECT_ROOT/mcp-servers/openviking"
mkdir -p "$MCP_DIR"

# Extract server.py from repo
cd "$REPO_PATH"
git show HEAD:mcp-servers/openviking/server.py > "$MCP_DIR/server.py"
git show HEAD:mcp-servers/openviking/requirements.txt > "$MCP_DIR/requirements.txt"

chmod +x "$MCP_DIR/server.py"

# Install MCP server dependencies
echo "📦 Installing MCP server dependencies..."
pip install -q -r "$MCP_DIR/requirements.txt"

echo "✅ MCP server files created"
echo ""

# Update .mcp.json
echo "⚙️  Updating .mcp.json..."

cat > "$PROJECT_ROOT/.mcp.json" <<EOF
{
  "mcpServers": {
    "openviking": {
      "command": "python3",
      "args": ["$MCP_DIR/server.py"],
      "env": {
        "PYTHONUNBUFFERED": "1"
      }
    }
  }
}
EOF

echo "✅ .mcp.json updated"
echo ""

echo "✅ OpenViking setup complete!"
echo ""
echo "📝 Summary:"
echo "   - OpenViking installed via pipx"
echo "   - Config created with your OpenAI API key"
echo "   - Connect-A-PIC-Pro codebase indexed"
echo "   - MCP server configured for Claude Code"
echo ""
echo "🚀 Next steps:"
echo "   1. Start OpenViking server: $OPENVIKING_CMD-server"
echo "   2. Restart the agent: ./run_agent.sh"
echo ""
echo "   The agent will now use OpenViking for semantic code search!"
echo "   Token usage: ~15k instead of ~200k (93% reduction)"
echo ""
