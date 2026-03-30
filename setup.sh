#!/bin/bash
#
# Smart Setup Script for Autonomous Issue Agent
# Automatically detects environment and installs only required dependencies
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Banner
echo -e "${BLUE}╔════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   Autonomous Issue Agent - Smart Setup        ║${NC}"
echo -e "${BLUE}╔════════════════════════════════════════════════╗${NC}"
echo ""

# Detect environment
echo -e "${BLUE}[1/6] Detecting environment...${NC}"

IS_WSL=false
if grep -qi microsoft /proc/version 2>/dev/null; then
    IS_WSL=true
    echo -e "${GREEN}✓${NC} Running in WSL (Windows Subsystem for Linux)"
else
    echo -e "${GREEN}✓${NC} Running on Linux"
fi

# Check what's already installed
echo ""
echo -e "${BLUE}[2/6] Checking installed tools...${NC}"

HAS_GIT=false
HAS_NODE=false
HAS_DOTNET=false
HAS_RUST=false
HAS_PYTHON=false

if command -v git &> /dev/null; then
    HAS_GIT=true
    GIT_VERSION=$(git --version | cut -d' ' -f3)
    echo -e "${GREEN}✓${NC} git $GIT_VERSION"
else
    echo -e "${YELLOW}✗${NC} git not found"
fi

if command -v node &> /dev/null; then
    HAS_NODE=true
    NODE_VERSION=$(node --version)
    echo -e "${GREEN}✓${NC} Node.js $NODE_VERSION"
else
    echo -e "${YELLOW}✗${NC} Node.js not found"
fi

if command -v dotnet &> /dev/null; then
    HAS_DOTNET=true
    DOTNET_VERSION=$(dotnet --version)
    echo -e "${GREEN}✓${NC} dotnet SDK $DOTNET_VERSION"
else
    echo -e "${YELLOW}✗${NC} dotnet not found"
fi

if command -v rustc &> /dev/null; then
    HAS_RUST=true
    RUST_VERSION=$(rustc --version | cut -d' ' -f2)
    echo -e "${GREEN}✓${NC} rust $RUST_VERSION"
else
    echo -e "${YELLOW}✗${NC} rust not found"
fi

if command -v python3 &> /dev/null; then
    HAS_PYTHON=true
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
    echo -e "${GREEN}✓${NC} Python $PYTHON_VERSION"
else
    echo -e "${YELLOW}✗${NC} Python3 not found"
fi

# Analyze target repositories to detect what's needed
echo ""
echo -e "${BLUE}[3/6] Analyzing target repositories...${NC}"

NEEDS_DOTNET=false
NEEDS_RUST=false
NEEDS_NODE=false

# Check if .env exists and has repo configuration
if [ -f .env ]; then
    source .env

    # Parse AGENT_REPOS or AGENT_REPO
    if [ ! -z "$AGENT_REPOS" ]; then
        REPOS=$AGENT_REPOS
    elif [ ! -z "$AGENT_REPO" ]; then
        REPOS=$AGENT_REPO
    else
        REPOS=""
    fi

    if [ ! -z "$REPOS" ]; then
        echo -e "   Configured repositories: ${YELLOW}$REPOS${NC}"

        # Check if any repo mentions .NET, C#, rust, cargo, node, npm in name
        if echo "$REPOS" | grep -qi "dotnet\|csharp\|sharp\|-pro"; then
            NEEDS_DOTNET=true
        fi
        if echo "$REPOS" | grep -qi "rust\|cargo"; then
            NEEDS_RUST=true
        fi
        if echo "$REPOS" | grep -qi "node\|npm\|typescript\|react"; then
            NEEDS_NODE=true
        fi
    else
        echo -e "${YELLOW}   No repositories configured yet (.env missing or empty)${NC}"
        echo -e "${YELLOW}   Will install core dependencies only${NC}"
    fi
else
    echo -e "${YELLOW}   .env not found - will install core dependencies only${NC}"
fi

# Manual override if heuristic didn't detect
if [ "$NEEDS_DOTNET" = false ] && [ "$NEEDS_RUST" = false ] && [ "$NEEDS_NODE" = false ]; then
    echo ""
    echo -e "${YELLOW}   Could not auto-detect project types. You can install manually:${NC}"

    read -p "   Will you work with .NET/C# projects? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        NEEDS_DOTNET=true
    fi

    read -p "   Will you work with Rust projects? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        NEEDS_RUST=true
    fi

    read -p "   Will you work with Node.js/TypeScript projects? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        NEEDS_NODE=true
    fi
fi

# Summary of what will be installed
echo ""
echo -e "${BLUE}[4/6] Installation plan:${NC}"

INSTALL_LIST=()

if [ "$HAS_GIT" = false ]; then
    echo -e "${GREEN}→${NC} Install git"
    INSTALL_LIST+=("git")
fi

if [ "$HAS_PYTHON" = false ]; then
    echo -e "${GREEN}→${NC} Install Python 3"
    INSTALL_LIST+=("python3")
fi

if [ "$HAS_NODE" = false ]; then
    echo -e "${GREEN}→${NC} Install Node.js 18.x (required for Claude Code CLI)"
    INSTALL_LIST+=("node")
fi

if [ "$NEEDS_DOTNET" = true ] && [ "$HAS_DOTNET" = false ]; then
    echo -e "${GREEN}→${NC} Install .NET SDK 8.0 (for C# projects)"
    INSTALL_LIST+=("dotnet")
fi

if [ "$NEEDS_RUST" = true ] && [ "$HAS_RUST" = false ]; then
    echo -e "${GREEN}→${NC} Install Rust toolchain (for Rust projects)"
    INSTALL_LIST+=("rust")
fi

if [ ${#INSTALL_LIST[@]} -eq 0 ]; then
    echo -e "${GREEN}✓${NC} All required tools already installed!"
else
    echo ""
    read -p "Continue with installation? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Installation cancelled."
        exit 0
    fi
fi

# Install missing dependencies
echo ""
echo -e "${BLUE}[5/6] Installing dependencies...${NC}"

# Update package list if we need to install anything via apt
if [[ " ${INSTALL_LIST[@]} " =~ " git " ]] || [[ " ${INSTALL_LIST[@]} " =~ " python3 " ]]; then
    echo -e "${YELLOW}→${NC} Updating package list..."
    sudo apt-get update -qq
fi

# Install git
if [[ " ${INSTALL_LIST[@]} " =~ " git " ]]; then
    echo -e "${YELLOW}→${NC} Installing git..."
    sudo apt-get install -y git
    echo -e "${GREEN}✓${NC} git installed"
fi

# Install Python
if [[ " ${INSTALL_LIST[@]} " =~ " python3 " ]]; then
    echo -e "${YELLOW}→${NC} Installing Python 3 and venv..."
    sudo apt-get install -y python3 python3-pip python3-venv
    echo -e "${GREEN}✓${NC} Python 3 installed"
fi

# Install Node.js (required for Claude Code CLI)
if [[ " ${INSTALL_LIST[@]} " =~ " node " ]]; then
    echo -e "${YELLOW}→${NC} Installing Node.js 18.x..."
    curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
    sudo apt-get install -y nodejs
    echo -e "${GREEN}✓${NC} Node.js installed"
fi

# Install .NET SDK
if [[ " ${INSTALL_LIST[@]} " =~ " dotnet " ]]; then
    echo -e "${YELLOW}→${NC} Installing .NET SDK 8.0..."

    # Microsoft package repository
    wget https://packages.microsoft.com/config/ubuntu/22.04/packages-microsoft-prod.deb -O packages-microsoft-prod.deb
    sudo dpkg -i packages-microsoft-prod.deb
    rm packages-microsoft-prod.deb

    sudo apt-get update -qq
    sudo apt-get install -y dotnet-sdk-8.0
    echo -e "${GREEN}✓${NC} .NET SDK installed"
fi

# Install Rust
if [[ " ${INSTALL_LIST[@]} " =~ " rust " ]]; then
    echo -e "${YELLOW}→${NC} Installing Rust toolchain..."
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
    source "$HOME/.cargo/env"
    echo -e "${GREEN}✓${NC} Rust installed"
fi

# Install Claude Code CLI
echo ""
echo -e "${YELLOW}→${NC} Installing Claude Code CLI..."
if command -v claude &> /dev/null; then
    echo -e "${GREEN}✓${NC} Claude Code CLI already installed"
else
    sudo npm install -g @anthropic-ai/claude-code
    echo -e "${GREEN}✓${NC} Claude Code CLI installed"
fi

# Initialize git submodules (python-dev-tools)
echo ""
echo -e "${BLUE}[5/7] Initializing submodules...${NC}"
if [ -d ".git" ]; then
    if [ ! -f "tools/semantic_search.py" ]; then
        echo -e "${YELLOW}→${NC} Initializing git submodules (python-dev-tools)..."
        git submodule update --init --recursive
        echo -e "${GREEN}✓${NC} Submodules initialized"
    else
        echo -e "${GREEN}✓${NC} Submodules already initialized"
    fi
else
    echo -e "${YELLOW}⚠${NC} Not a git repository - submodules skipped"
    echo -e "   ${YELLOW}Note:${NC} Clone with: git clone --recurse-submodules <repo-url>"
fi

# Setup Python virtual environment
echo ""
echo -e "${BLUE}[6/7] Setting up Python virtual environment...${NC}"
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo -e "${GREEN}✓${NC} Virtual environment created"
else
    echo -e "${GREEN}✓${NC} Virtual environment already exists"
fi

echo -e "${YELLOW}→${NC} Installing Python dependencies..."
source venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt
echo -e "${GREEN}✓${NC} Python dependencies installed"

# Configure environment
echo ""
echo -e "${BLUE}[7/7] Final configuration...${NC}"

# Check if .env exists
if [ ! -f .env ]; then
    echo -e "${YELLOW}→${NC} Creating .env file from example..."
    cp .env.example .env
    echo -e "${GREEN}✓${NC} .env created"
    echo ""
    echo -e "${RED}⚠ IMPORTANT:${NC} Please edit .env and add your API keys:"
    echo -e "   - GITHUB_TOKEN=<your-github-token>"
    echo -e "   - ANTHROPIC_API_KEY=<your-anthropic-key>"
    echo -e "   - AGENT_REPOS=owner/repo1,owner/repo2"
    echo ""
else
    echo -e "${GREEN}✓${NC} .env already configured"
fi

# WSL-specific git configuration hint
if [ "$IS_WSL" = true ]; then
    if ! git config --global credential.helper &> /dev/null; then
        echo ""
        echo -e "${YELLOW}→${NC} WSL detected - git credential helper recommended:"
        echo -e "   Run: git config --global credential.helper store"
        echo -e "   Then: echo 'https://YOUR_GITHUB_TOKEN:@github.com' > ~/.git-credentials"
        echo -e "   Finally: chmod 600 ~/.git-credentials"
        echo ""
    fi
fi

# Success!
echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║          Setup completed successfully! ✓       ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BLUE}Next steps:${NC}"
echo -e "  1. Edit .env with your API keys (if not done yet)"
echo -e "  2. Run: ${YELLOW}./dashboard_interactive.sh${NC} (recommended)"
echo -e "     Or: ${YELLOW}source venv/bin/activate && python3 main.py${NC}"
echo ""
echo -e "${BLUE}Tools installed:${NC}"
if [ "$HAS_GIT" = true ] || [[ " ${INSTALL_LIST[@]} " =~ " git " ]]; then
    echo -e "  ${GREEN}✓${NC} git"
fi
if [ "$HAS_NODE" = true ] || [[ " ${INSTALL_LIST[@]} " =~ " node " ]]; then
    echo -e "  ${GREEN}✓${NC} Node.js + Claude Code CLI"
fi
if [ "$HAS_PYTHON" = true ] || [[ " ${INSTALL_LIST[@]} " =~ " python3 " ]]; then
    echo -e "  ${GREEN}✓${NC} Python 3 + dependencies"
fi
if [ "$HAS_DOTNET" = true ] || [[ " ${INSTALL_LIST[@]} " =~ " dotnet " ]]; then
    echo -e "  ${GREEN}✓${NC} .NET SDK 8.0"
fi
if [ "$HAS_RUST" = true ] || [[ " ${INSTALL_LIST[@]} " =~ " rust " ]]; then
    echo -e "  ${GREEN}✓${NC} Rust toolchain"
fi
echo ""
echo -e "Happy automating! 🤖"
echo ""
