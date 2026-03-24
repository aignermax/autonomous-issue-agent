#!/bin/bash
set -e

# Change to script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Autonomous Issue Agent (AIA) ===${NC}\n"

# Check if .env file exists
if [ ! -f .env ]; then
    echo -e "${RED}ERROR: .env file not found!${NC}\n"
    echo "Please create a .env file with your credentials:"
    echo ""
    echo "  cp .env.example .env"
    echo ""
    echo "Then edit .env and add your tokens:"
    echo ""
    echo "  GITHUB_TOKEN=ghp_your_github_token_here"
    echo "  ANTHROPIC_API_KEY=sk-ant-your_anthropic_key_here"
    echo "  AGENT_REPO=owner/repo-name"
    echo ""
    echo "Get your tokens from:"
    echo "  - GitHub: https://github.com/settings/tokens (need 'repo' scope)"
    echo "  - Anthropic: https://console.anthropic.com/"
    echo ""
    exit 1
fi

# Load environment variables from .env
echo -e "${GREEN}Loading environment variables from .env...${NC}"
export $(grep -v '^#' .env | xargs)

# Check for required environment variables
MISSING_VARS=()

if [ -z "$GITHUB_TOKEN" ]; then
    MISSING_VARS+=("GITHUB_TOKEN")
fi

if [ -z "$ANTHROPIC_API_KEY" ]; then
    MISSING_VARS+=("ANTHROPIC_API_KEY")
fi

if [ -z "$AGENT_REPO" ]; then
    MISSING_VARS+=("AGENT_REPO")
fi

if [ ${#MISSING_VARS[@]} -ne 0 ]; then
    echo -e "${RED}ERROR: Missing required environment variables in .env:${NC}"
    for var in "${MISSING_VARS[@]}"; do
        echo -e "  ${RED}✗${NC} $var"
    done
    echo ""
    echo "Please edit your .env file and add the missing variables:"
    echo ""
    echo "  nano .env"
    echo ""
    echo "Required format:"
    echo "  GITHUB_TOKEN=ghp_..."
    echo "  ANTHROPIC_API_KEY=sk-ant-..."
    echo "  AGENT_REPO=owner/repo-name"
    echo ""
    exit 1
fi

echo -e "${GREEN}✓ All required tokens found${NC}\n"

# Check if venv exists
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}Virtual environment not found. Creating...${NC}"
    python3 -m venv venv
    echo -e "${GREEN}✓ Virtual environment created${NC}\n"
fi

# Activate virtual environment
echo -e "${GREEN}Activating virtual environment...${NC}"
source venv/bin/activate

# Check if dependencies are installed
if ! python -c "import github" 2>/dev/null; then
    echo -e "${YELLOW}Installing dependencies...${NC}"
    pip install -r requirements.txt
    echo -e "${GREEN}✓ Dependencies installed${NC}\n"
fi

# Check if Claude Code CLI is installed
if ! command -v claude &> /dev/null; then
    echo -e "${YELLOW}WARNING: Claude Code CLI not found!${NC}"
    echo "Install with: npm install -g @anthropic-ai/claude-code"
    echo ""
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    echo -e "${GREEN}✓ Claude Code CLI found${NC}"
fi

# Start OpenViking server if configured
if [ -f scripts/start-openviking.sh ]; then
    ./scripts/start-openviking.sh
fi

echo -e "\n${GREEN}Starting agent...${NC}"
echo -e "Repository: ${YELLOW}$AGENT_REPO${NC}"
echo -e "Polling interval: ${YELLOW}${AGENT_POLL_INTERVAL:-300}s${NC}"
echo -e "Issue label: ${YELLOW}${AGENT_ISSUE_LABEL:-agent-task}${NC}\n"

# Run the agent
python main.py "$@"
