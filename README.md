# Autonomous Issue Agent (AIA)

An autonomous agent that implements GitHub Issues using Claude Code.

<img width="814" height="848" alt="image" src="https://github.com/user-attachments/assets/1bb290ec-c140-449c-8e43-0020d2b1dcf1" />

**Works with any GitHub repository** — not limited to a specific tech stack or project type.

## 🆕 Two Implementation Options

### Option 1: Claude Code Plugin (Recommended - MCP Support!)

**✅ Recommended for:** New users, MCP integration, token efficiency

The plugin runs directly inside Claude Code with full MCP integration:
- ✅ **GitHub MCP** - Native GitHub API access
- ✅ **OpenViking MCP** - Semantic search (93% token reduction: 23k → 1.6k)
- ✅ **Better integration** - Skills + Agent definitions instead of Python code
- ✅ **Token savings** - ~$6.40 per 100 issues

**→ [Get Started with Plugin](plugin/README.md)** | **[Installation Guide](plugin/INSTALL.md)**

### Option 2: Python Agent (Legacy - No MCP)

**✅ Good for:** Existing users, running agent as standalone service

The original Python-based implementation using subprocess:
- ❌ MCP not supported (hangs in subprocess)
- ✅ Fully automated polling loop
- ✅ Works without Claude Code session
- ℹ️ Higher token usage (~23k per issue)

**→ Continue reading below for Python agent setup**

---

## How it works

```
GitHub Issue (label: agent-task)
        │
        ▼
   Agent polls every 5 min
        │
        ▼
   Git: clone/pull + create new branch
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
```

## Why Claude Code over raw API?

| Raw API approach                    | Claude Code (this agent)            |
|-------------------------------------|-------------------------------------|
| No repository awareness             | Reads the entire codebase           |
| Regex-based file parsing            | Direct file editing with context    |
| No build/test awareness             | Runs builds/tests automatically     |
| Fixes without context               | Iterates with full context          |
| ~100 lines of glue code             | Claude does the heavy lifting       |

## Setup

### 1. Prerequisites

```bash
# Node.js (>= 18)
node --version

# Claude Code CLI installieren
npm install -g @anthropic-ai/claude-code

# Python deps
pip install -r requirements.txt
```

### 2. Environment Variables

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

Then edit `.env`:

```bash
# Required
GITHUB_TOKEN=ghp_...                              # GitHub Personal Access Token (repo scope)
ANTHROPIC_API_KEY=sk-ant-...                      # Anthropic API Key
AGENT_REPO=owner/your-repo                        # Target repository

# Optional
AGENT_POLL_INTERVAL=15                            # Polling interval in seconds (default: 15)
AGENT_ISSUE_LABEL=agent-task                      # Issue label to watch (default: agent-task)
AGENT_MAX_TURNS=30                                # Max Claude Code turns (default: 30)
AGENT_REPO_PATH=./repo                            # Local clone path (default: ./repo)
```

**How to get tokens:**
- **GITHUB_TOKEN**: [Create a Personal Access Token](https://github.com/settings/tokens) with `repo` scope
- **ANTHROPIC_API_KEY**: Get your API key from [Anthropic Console](https://console.anthropic.com/)

### 3. Add CLAUDE.md to your target repository

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

### 4. MCP Servers (Currently Not Supported)

**Note:** MCP (Model Context Protocol) is currently **not compatible** with the agent's subprocess automation approach. MCP works great in interactive Claude Code sessions but hangs when used in automated subprocess calls.

**Future:** A Claude Code plugin architecture is being explored that would allow direct MCP access without subprocess limitations. See [MCP_TESTING.md](MCP_TESTING.md) for details.

**Current status:** Agent runs reliably without MCP using standard headless mode (~23k tokens per issue).

**Summary of benefits:**
- OpenViking: 93% token reduction for code exploration (all languages)
- NetContextServer: .NET-specific tooling (C# projects only)
- dotnet-test-mcp: Structured test output (C# projects only)

If you skip this step, the agent will still work but won't use MCP optimizations.

### 5. Start the agent

```bash
# Run with dashboard (recommended - opens in new terminal window)
./run_agent.sh

# Run without dashboard
./run_agent.sh --no-dashboard

# Run once for testing
./run_agent.sh --once

# Or run directly with Python
python main.py
```

### 6. Interactive Dashboard (Recommended)

The interactive dashboard provides full agent control:

```bash
./dashboard_interactive.sh
```

**Commands:**
- `[g]` Start Agent - Launch agent in continuous mode
- `[k]` Kill Agent - Stop running agent
- `[b]` Benchmark - Test with/without MCP (experimental)
- `[s]` Stream Logs - Watch real-time agent output
- `[l]` Show Logs - View recent log entries
- `[r]` Refresh - Update dashboard display
- `[a]` Auto-refresh - Toggle automatic updates
- `[q]` Quit - Exit dashboard

**Dashboard features:**
- 🟢 Real-time agent status (polling, working, error)
- 🔄 Current issue being processed
- 📈 Recent issue history with token usage and costs
- 📊 Benchmark results and comparisons

**Alternative (manual start):**
```bash
# Start agent manually
source venv/bin/activate
python3 main.py
```

### 6. Create issues for the agent

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

## Example: Connect-A-PIC-Pro

This agent was originally developed for [Connect-A-PIC-Pro](https://github.com/aignermax/Connect-A-PIC-Pro), a photonic circuit design tool built with C# / Avalonia.

The included `CLAUDE.md` demonstrates:
- **Vertical Slice Architecture** (Core + ViewModel + View + Tests)
- **File size limits** (max 250 lines per new file)
- **MVVM patterns** with CommunityToolkit.Mvvm
- **Testing strategy** (xUnit + Shouldly + Moq)

Adapt these patterns to your own project's needs.

## MCP (Model Context Protocol) Integration

The agent supports **MCP servers** to enhance Claude Code's capabilities. Currently integrated:

### OpenViking (Semantic Code Search) ⭐ RECOMMENDED FOR ALL PROJECTS

**What it does:** Universal semantic code search with massive token reduction (93% in real-world usage).

**Benefits:**
- **93% token reduction** - from 200k tokens to 15k tokens for codebase exploration
- **Language-agnostic** - works with Python, JavaScript, TypeScript, Rust, Go, C++, and more
- **Semantic search** - find code by natural language description, not just text matching
- **Directory overviews** - AI-generated summaries of folder contents
- **Local embeddings** - uses Ollama (free) or OpenAI for vectorization

**Installation:**

```bash
# Install OpenViking
pip install openviking

# Start OpenViking server in background
openviking-server &

# Index your codebase (for C# projects with unsupported file types)
cd /path/to/autonomous-issue-agent
./scripts/index-openviking.sh
```

**For C# projects (with .axaml/.csproj/.sln files):**

The indexing script uses `--no-strict` flag to allow indexing despite file types that OpenViking doesn't normally support. This allows full C# codebase indexing including Avalonia projects.

**Configuration:**

OpenViking is already configured in `.mcp.json`. Set your OpenAI API key in `.env`:

```bash
OPENAI_API_KEY=sk-...
```

Or use Ollama for free local embeddings (see [OpenViking docs](https://github.com/openviking-ai/openviking)).

**What Claude Code gets:**
- Semantic search across entire codebase
- File and directory navigation with AI summaries
- Context-aware code retrieval
- Massive reduction in token usage for exploration tasks

---

### NetContextServer (for .NET/C# projects) - Additional .NET Features

**What it does:** Provides semantic code search and .NET-specific analysis for C# codebases.

**Benefits:**
- **Semantic code search** - find code by natural language description
- **Project analysis** - understands .csproj files and dependencies
- **Coverage analysis** - multi-format support (Coverlet, LCOV, Cobertura)
- **Package recommendations** - dependency updates and visualization
- **C# native** - built specifically for .NET ecosystem

**Installation:**

NetContextServer is included as a git submodule. Build it once:

```bash
cd mcp-servers/netcontext
dotnet build
```

After building, NetContextServer is configured in `.mcp.json` and will start automatically when the agent runs.

**Features available to Claude Code:**
- List all .NET source files in the project ✅ (works without API key)
- Analyze .csproj dependencies ✅ (works without API key)
- Read file contents with context ✅ (works without API key)
- Search C# code semantically ⚠️ (requires Azure OpenAI - optional)

**Semantic Search (Optional):**

To enable semantic code search, add to your `.env`:

```bash
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-azure-openai-key
```

**Note:** NetContextServer works without Azure OpenAI keys, but semantic search will be disabled.

---

### dotnet-test-mcp (for .NET projects)

Provides structured test execution and output parsing, saving tokens and improving test result analysis.

**Prerequisites:**
- .NET 10 SDK (only on the agent machine, not in target project!)
- xUnit v3 with MTP v2 (Microsoft Testing Platform) in target project

**Installation:**

```bash
# Install .NET 10 SDK
wget https://dot.net/v1/dotnet-install.sh -O /tmp/dotnet-install.sh
chmod +x /tmp/dotnet-install.sh
/tmp/dotnet-install.sh --channel 10.0 --install-dir ~/.dotnet-10

# Clone and build dotnet-test-mcp
git clone https://github.com/j-d-ha/dotnet-test-mcp.git /tmp/dotnet-test-mcp
~/.dotnet-10/dotnet build /tmp/dotnet-test-mcp/src/DotnetTest.Mcp/DotnetTest.Mcp.csproj -c Release
~/.dotnet-10/dotnet pack /tmp/dotnet-test-mcp/src/DotnetTest.Mcp/DotnetTest.Mcp.csproj -c Release -o /tmp/dotnet-test-mcp-package
~/.dotnet-10/dotnet tool install --global DotnetTest.Mcp --version 0.0.1-beta.4 --add-source /tmp/dotnet-test-mcp-package
```

**Configuration:**

The `.mcp.json` file is already configured in this repository. Claude Code CLI loads it automatically.

**Target project requirements:**

Your .NET project needs MTP v2 enabled in `global.json`:

```json
{
  "sdk": {
    "version": "8.0.100",
    "rollForward": "latestMajor"
  },
  "test": {
    "runner": "Microsoft.Testing.Platform"
  }
}
```

**What it does:**
- `ListTestProjects` - Enumerate test projects
- `ListTestsSummary` - Get test counts and names
- `RunSingleTest` - Execute specific test
- `RunAllTests` - Run entire test suite
- Returns structured JSON instead of thousands of lines of raw output

**Token savings:** ~70-90% reduction in test output tokens!

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
