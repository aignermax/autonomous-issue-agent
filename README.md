# Autonomous Issue Agent (AIA)

An autonomous agent that implements GitHub Issues using Claude Code.

<img width="814" height="848" alt="image" src="https://github.com/user-attachments/assets/1bb290ec-c140-449c-8e43-0020d2b1dcf1" />

**Works with any GitHub repository** — not limited to a specific tech stack or project type.

## Implementation: Python Agent

**Recommended Implementation:** Standalone Python agent (headless subprocess)

The Python-based autonomous agent runs as a background service:
- ✅ **Fully automated polling loop** - Monitors multiple repositories 24/7
- ✅ **Headless operation** - Runs without interactive Claude Code session
- ✅ **Multi-repository support** - Process issues across different repos
- ✅ **Session management** - Resumes work across restarts
- ✅ **Built-in tools** - Semantic search and smart test runner
- ⚠️ **No MCP support** - MCP causes hangs in subprocess headless mode
- ℹ️ **Token usage** - ~15-25k tokens per issue

> **Note:** An experimental plugin implementation exists in `plugin/` but has stability issues with MCP in headless mode and is not actively maintained. The Python agent is the stable, production-ready implementation.

---

## 🛠️ AI-Powered Development Tools

Looking for standalone AI development tools? Check out [**python-dev-tools**](https://github.com/aignermax/python-dev-tools):
- **Semantic Search** - Natural language code search using AI embeddings
- **Smart Test Runner** - Automatically finds and runs only relevant tests

These tools can be used independently or integrated with this agent for enhanced capabilities.

---

## How it works

```
GitHub Issues (label: agent-task) across multiple repos
        │
        ▼
   Agent polls every 15s (configurable)
        │
        ▼
   For each repository:
     - Check for agent-task issues
     - Clone/pull latest changes
     - Create feature branch
        │
        ▼
   Claude Code (headless):
   - Reads the entire repository
   - Understands the architecture
   - Implements the issue
   - Builds & tests
   - Fixes errors autonomously
        │
        ▼
   Git: commit + push
        │
        ▼
   GitHub: Create PR + close issue
        │
        ▼
   Move to next repository
```

**Multi-Repository Support:** The agent can monitor multiple repositories simultaneously. Configure with `AGENT_REPOS=owner/repo1,owner/repo2` in `.env`. The agent processes issues in order across all configured repositories.

## Why Claude Code over raw API?

| Raw API approach                    | Claude Code (this agent)            |
|-------------------------------------|-------------------------------------|
| No repository awareness             | Reads the entire codebase           |
| Regex-based file parsing            | Direct file editing with context    |
| No build/test awareness             | Runs builds/tests automatically     |
| Fixes without context               | Iterates with full context          |
| ~100 lines of glue code             | Claude does the heavy lifting       |

## Setup

### Quick Setup (Recommended)

**One-command installation** that automatically detects your environment and installs only what you need:

```bash
# Clone the repository with submodules (includes python-dev-tools)
git clone --recurse-submodules https://github.com/aignermax/autonomous-issue-agent.git
cd autonomous-issue-agent

# Run smart setup script
./setup.sh
```

**Note:** The `--recurse-submodules` flag automatically clones the [python-dev-tools](https://github.com/aignermax/python-dev-tools) submodule which contains semantic search and smart test runner tools.

If you already cloned without `--recurse-submodules`, initialize the submodules:
```bash
git submodule update --init --recursive
```

The setup script will:
- ✅ Detect your environment (WSL, Linux, Mac)
- ✅ Check what tools are already installed
- ✅ Analyze your target repositories (.NET, Rust, Node.js, etc.)
- ✅ Install only missing dependencies
- ✅ Configure Python virtual environment
- ✅ Create .env file from template

**For Windows users:** First install WSL, then run the setup script inside WSL:
```bash
# In Windows PowerShell (run as Administrator)
wsl --install Ubuntu

# Open Ubuntu terminal, then:
cd ~
git clone https://github.com/aignermax/autonomous-issue-agent.git
cd autonomous-issue-agent
./setup.sh
```

### Manual Setup (Alternative)

<details>
<summary>Click to expand manual installation steps</summary>

**For Windows Users:**
This agent requires WSL (Windows Subsystem for Linux) because it uses Unix-specific modules (`pty`, `termios`).

```bash
# Install WSL with Ubuntu (if not already installed)
wsl --install Ubuntu

# Open WSL terminal and install Node.js
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs

# Install Claude Code CLI in WSL
npm install -g @anthropic-ai/claude-code

# Clone the repository in WSL
cd ~
git clone https://github.com/aignermax/autonomous-issue-agent.git
cd autonomous-issue-agent

# Install Python dependencies
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

**For Linux/Mac Users:**

```bash
# Node.js (>= 18)
node --version

# Claude Code CLI
npm install -g @anthropic-ai/claude-code

# Python deps
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

</details>

### Configure Environment Variables

The setup script creates `.env` from `.env.example` automatically. Edit it to add your credentials:

```bash
nano .env  # or use your preferred editor
```

Then edit `.env`:

```bash
# Required
GITHUB_TOKEN=ghp_...                              # GitHub Personal Access Token (repo scope)
ANTHROPIC_API_KEY=sk-ant-...                      # Anthropic API Key (required for CLI automation)

# Target Repositories (choose one mode)
# Multi-repo mode (recommended): Watch multiple repositories
AGENT_REPOS=owner/repo1,owner/repo2,owner/repo3   # Comma-separated list
# Single-repo mode: Watch a single repository
# AGENT_REPO=owner/your-repo                      # Ignored if AGENT_REPOS is set

# Optional
AGENT_POLL_INTERVAL=15                            # Agent polling interval in seconds (default: 15)
DASHBOARD_REFRESH_INTERVAL=5                      # Dashboard refresh interval in seconds (default: 5)
AGENT_ISSUE_LABEL=agent-task                      # Issue label to watch (default: agent-task)
AGENT_MAX_TURNS=500                               # Max Claude Code turns (default: 300)
AGENT_REPO_PATH=./repo                            # Local clone path (default: ./repo)

# Optional: Semantic Search (requires OpenAI for embeddings)
# OPENAI_API_KEY=sk-...                           # Only needed for semantic_search.py tool
```

**How to get API keys:**

| API Key | Required? | Cost | How to get |
|---------|-----------|------|------------|
| **GITHUB_TOKEN** | ✅ **YES** | Free | [Create Personal Access Token](https://github.com/settings/tokens) with `repo` scope |
| **ANTHROPIC_API_KEY** | ✅ **YES** | **Pay-per-use** (~$0.20-$2 per issue) | [Anthropic Console](https://console.anthropic.com/) |
| **OPENAI_API_KEY** | ⚠️ Optional | Pay-per-use | Only needed for semantic_search.py tool |

**Important: Why ANTHROPIC_API_KEY is required**

This agent uses **Claude Code CLI in headless mode** for automation. Unlike the interactive Claude Desktop app which uses OAuth login with Claude Pro/Teams subscriptions, the CLI requires an **API key** for automated/headless operation.

- ❌ **Claude Pro/Teams subscription**: Works for Desktop app, NOT for CLI automation
- ✅ **Anthropic API Key**: Required for CLI headless mode (separate from subscription)
- 💰 **Costs**: ~$3/1M input tokens, ~$15/1M output tokens (Claude Sonnet 4)
- 📊 **Typical usage**: 15-50K tokens per issue = $0.20-$2 per issue

**Cost optimization tips:**
- Use prompt caching (enabled by default) - saves ~70% on repeated context
- Set reasonable `AGENT_MAX_TURNS` limits (default: 500)
- Monitor usage in [Anthropic Console](https://console.anthropic.com/)

**Accurate cost tracking:**
The agent now uses `--debug api` mode to capture **all** API calls made by Claude Code during execution (build, test, fix iterations, etc.), not just the final response. This provides accurate cost tracking that matches your Anthropic Console billing. Previous versions would underreport costs by 2-14x depending on task complexity.

### 4. Add CLAUDE.md to your target repository

The agent reads `CLAUDE.md` from your repository root to understand your project's architecture and coding standards.

**Example provided:** The included `CLAUDE.md` is configured for **Connect-A-PIC-Pro** (C# / Avalonia / MVVM project). You should:
- Copy it to your target repository: `cp CLAUDE.md /path/to/your/repo/CLAUDE.md`
- Adapt it to your project's needs (tech stack, testing framework, architecture patterns)

**Key sections to customize:**
- File size limits (e.g., 250 lines for C#)
- Architecture patterns (MVVM, Clean Architecture, etc.)
- Testing requirements (xUnit, Jest, pytest, etc.)
- Build commands (`dotnet build`, `npm test`, `cargo build`, etc.)
- **Vertical Slice requirement** — ensure PRs include UI + backend + tests

### 5. MCP Servers (Not Supported in Python Agent)

**Note:** MCP (Model Context Protocol) is **not compatible** with the Python headless agent's subprocess approach.

**Why:** MCP servers require interactive Claude Code sessions and cannot communicate through subprocess automation. They hang when used in headless mode.

**Solution:** Use the **[Plugin architecture](plugin/README.md)** instead for full MCP support:
- ✅ OpenViking: 93% token reduction for code exploration
- ✅ NetContextServer: .NET-specific tooling
- ✅ dotnet-test-mcp: Structured test output

**Current Python agent:** Runs reliably without MCP using standard headless mode (~23k tokens per issue). This is still very effective for most tasks.

### 6. Start the agent

**For Windows Users:**

Simply double-click `start.bat` in the repository root (Windows). This will:
- Open the interactive dashboard in WSL
- Show agent status and monitored repositories
- Allow you to start/stop the agent with keyboard commands

**For Linux/Mac Users:**

```bash
# Run with dashboard (recommended)
./dashboard_interactive.sh
```

### 7. Interactive Dashboard

The interactive dashboard provides full agent control with a clean interface:

**Windows:** Double-click **[start.bat](start.bat)** in the repository root

**Linux/Mac:** Run `./dashboard_interactive.sh`

**Dashboard Commands:**
- `[g]` Start Agent - Launch agent in continuous mode
- `[s]` Stop Agent - Stop running agent
- `[r]` Refresh - Update dashboard display
- `[q]` Quit - Exit dashboard

**Dashboard displays:**
- Real-time agent status (polling, working, idle)
- Current issue being processed
- Monitored repositories (e.g., Akhetonics/akhetonics-desktop, Akhetonics/raycore-sdk)
- Recent issue history with token usage and costs
- CPU usage and session time

**Alternative (manual start):**
```bash
# Linux/Mac
source venv/bin/activate
python3 main.py

# Windows (in WSL)
wsl bash -c "cd ~/autonomous-issue-agent && venv/bin/python3 main.py"
```

### 8. Create issues for the agent

Create an issue on GitHub with the label `agent-task` (or your custom label from `.env`):

**Example for Connect-A-PIC-Pro:**

**Title:** `Add loss budget analyzer for optical paths`

**Body:**
```
Implement a loss budget analysis feature that calculates total optical loss along signal paths.

Requirements:
- Core analyzer class in Connect-A-Pic-Core/Analysis/
- ViewModel with ObservableProperty and RelayCommand
- AXAML panel in MainWindow.axaml (right side properties area)
- Unit tests for core logic
- Integration test for Core → ViewModel flow
- Must follow vertical slice architecture (Core + ViewModel + View + Tests)
```

The agent will automatically:
1. Pull latest changes from `main`
2. Create a new branch `agent/issue-{number}-{timestamp}`
3. Implement the full vertical slice
4. Run builds and tests until they pass
5. Create a PR and close the issue

## Logs

All agent activity is logged to `agent.log` and printed to stdout simultaneously.

## Security considerations

- **`--dangerously-skip-permissions`** is required for headless mode.
  This allows Claude Code to read/write files and execute commands autonomously.
- **Only run on trusted machines** — your dev machine or isolated environments.
- The agent **never commits directly to `main`** — always creates feature branches.
- The `repo/` directory is local only and not tracked in Git.

## Running on multiple machines

To run the agent on another machine (e.g., work computer):

1. Clone this repository: `git clone https://github.com/aignermax/autonomous-issue-agent.git`
2. Install dependencies (see Setup section above)
3. Configure `.env` with your tokens
4. Run `python main.py`

The `repo/` directory will be automatically cloned on first run.

## Example: Lunima (formerly Connect-A-PIC-Pro)

This agent was originally developed for [Lunima](https://github.com/aignermax/Connect-A-PIC-Pro) (formerly Connect-A-PIC-Pro), a photonic circuit design tool built with C# / Avalonia.

The included `CLAUDE.md` demonstrates:
- **Vertical Slice Architecture** (Core + ViewModel + View + Tests)
- **File size limits** (max 250 lines per new file)
- **MVVM patterns** with CommunityToolkit.Mvvm
- **Testing strategy** (xUnit + Shouldly + Moq)

Adapt these patterns to your own project's needs.

## MCP (Model Context Protocol) Integration

The agent supports **MCP servers** to enhance Claude Code's capabilities. Currently integrated:

### OpenViking (Semantic Code Search) ❌ NOT COMPATIBLE WITH HEADLESS MODE

**Status:** OpenViking is **not compatible** with the Python headless agent due to subprocess limitations.

**Why it doesn't work:**
- OpenViking MCP server requires interactive mode
- The subprocess-based headless approach cannot communicate with MCP servers
- Hangs when Claude Code attempts to use MCP tools in subprocess

**Alternative:** Use the [Plugin architecture](plugin/README.md) instead, which has full MCP support including OpenViking.

**For Plugin users:**
- ✅ OpenViking works perfectly in the plugin (runs inside Claude Code session)
- ✅ 93% token reduction for code exploration
- ✅ Semantic search across entire codebase

---

### NetContextServer (for .NET/C# projects) ❌ NOT COMPATIBLE WITH HEADLESS MODE

**Status:** NetContextServer is **not compatible** with the Python headless agent.

**Why it doesn't work:**
- Same subprocess/MCP limitations as OpenViking
- MCP servers cannot be used in headless subprocess mode

**Alternative:** Use the [Plugin architecture](plugin/README.md) for MCP support.

---

### dotnet-test-mcp (for .NET projects) ❌ NOT COMPATIBLE WITH HEADLESS MODE

**Status:** dotnet-test-mcp is **not compatible** with the Python headless agent.

**Why it doesn't work:**
- MCP servers require interactive Claude Code sessions
- Not accessible in subprocess-based headless mode

**Alternative:** Use the [Plugin architecture](plugin/README.md) for full MCP support including dotnet-test-mcp.

## Troubleshooting

### Agent hangs at "Invoking Claude Code..."

**Problem:** The agent tries to start a nested Claude Code session when run inside an existing Claude Code session (e.g., VSCode extension).

**Solution:** Run the agent in a **separate terminal** outside any Claude Code session:

```bash
# Exit any VSCode/Claude Code session first
# Then run in a plain terminal:
./run_agent.sh
```

**Why:** Claude Code doesn't support nested sessions. The warning message is correct:
```
WARNING: Running inside a Claude Code session!
This may cause nested session conflicts.
Recommended: Run in a separate terminal window.
```

### NetContextServer not found

If you see "NetContextServer not found" errors, rebuild the MCP server:

```bash
cd mcp-servers/netcontext
dotnet build
```

NetContextServer starts automatically when the agent invokes Claude Code CLI - no manual server startup needed.

## Future improvements

- [ ] Docker container for isolated execution
- [ ] Webhooks instead of polling (GitHub → Agent)
- [ ] Multi-issue queue with prioritization
- [ ] Slack/Discord notifications on PR creation
- [x] ~~Token budget tracking per issue~~ (✅ Implemented)
- [x] ~~MCP server integration~~ (✅ dotnet-test-mcp, NetContextServer)

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

Contributions welcome! Feel free to open issues or submit PRs.

## Optional Dependencies

### Nazca Design (for Photonic IC Design)

If your repository uses Nazca Design for photonic integrated circuit design, install it manually:

```bash
# Download nazca-0.6.1.tar.gz from the official source
# Then install in the agent's venv:
source venv/bin/activate
pip install /path/to/nazca-0.6.1.tar.gz
```

Nazca provides photonic IC design capabilities and is used by some test suites.
