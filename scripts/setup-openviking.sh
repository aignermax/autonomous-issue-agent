#!/bin/bash
# OpenViking Setup for Autonomous Issue Agent
# Automatically sets up OpenViking for Claude Code integration

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
REPO_PATH="$PROJECT_ROOT/repo"

echo "🚀 OpenViking Setup for Autonomous Issue Agent"
echo ""

# Ask user which embedding provider to use
echo "Choose embedding provider:"
echo "  1) Ollama (local, free, slower indexing)"
echo "  2) OpenAI (paid, fast, requires API key)"
echo ""
read -p "Choice [1/2] (default: 1): " EMBEDDING_CHOICE
EMBEDDING_CHOICE=${EMBEDDING_CHOICE:-1}

if [ "$EMBEDDING_CHOICE" = "2" ]; then
    # OpenAI mode - check for API key
    if [ ! -f "$PROJECT_ROOT/.env" ]; then
        echo "❌ Error: .env file not found"
        echo "Please create .env with OPENAI_API_KEY"
        exit 1
    fi

    source "$PROJECT_ROOT/.env"

    if [ -z "$OPENAI_API_KEY" ]; then
        echo "❌ Error: OPENAI_API_KEY not set in .env"
        echo ""
        echo "Add to .env:"
        echo "  OPENAI_API_KEY=sk-proj-..."
        exit 1
    fi

    echo "✅ Using OpenAI embeddings (fast, paid)"
    EMBEDDING_PROVIDER="openai"
    EMBEDDING_API_KEY="$OPENAI_API_KEY"
    EMBEDDING_API_BASE="https://api.openai.com/v1"
else
    # Ollama mode - check if Ollama is running
    echo "✅ Using Ollama embeddings (free, local)"

    if ! command -v ollama &> /dev/null; then
        echo "❌ Error: Ollama not installed"
        echo ""
        echo "Install Ollama:"
        echo "  curl -fsSL https://ollama.com/install.sh | sh"
        echo ""
        exit 1
    fi

    # Check if Ollama is running
    if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        echo "🚀 Starting Ollama..."
        ollama serve &
        sleep 3
    fi

    # Pull nomic-embed-text model if not present
    if ! ollama list | grep -q "nomic-embed-text"; then
        echo "📦 Downloading nomic-embed-text model (~275 MB)..."
        ollama pull nomic-embed-text
    fi

    EMBEDDING_PROVIDER="ollama"
    EMBEDDING_API_KEY="dummy"  # Ollama doesn't need a key
    EMBEDDING_API_BASE="http://localhost:11434"
fi

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

# Create OpenViking config based on provider choice
if [ "$EMBEDDING_PROVIDER" = "ollama" ]; then
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
      "api_base": "http://localhost:11434",
      "provider": "ollama",
      "dimension": 768,
      "model": "nomic-embed-text"
    },
    "max_concurrent": 4
  }
}
EOF
else
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
      "api_base": "$EMBEDDING_API_BASE",
      "api_key": "$EMBEDDING_API_KEY",
      "provider": "openai",
      "dimension": 1536,
      "model": "text-embedding-3-small"
    },
    "max_concurrent": 10
  },
  "vlm": {
    "api_base": "$EMBEDDING_API_BASE",
    "api_key": "$EMBEDDING_API_KEY",
    "provider": "openai",
    "model": "gpt-4o-mini"
  }
}
EOF
fi

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
