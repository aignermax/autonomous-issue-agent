# Autonomous Issue Agent (AIA)

An autonomous agent that implements GitHub Issues using Claude Code in headless mode.

**Works with any GitHub repository** — not limited to a specific tech stack or project type.

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
AGENT_POLL_INTERVAL=300                           # Polling interval in seconds (default: 300)
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

### 4. Start the agent

```bash
# Run continuously (polls every 5 minutes)
python main.py

# Run once for testing
python main.py --once

# Or use the provided script
./run_agent.sh
```

### 5. Create issues for the agent

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

## Future improvements

- [ ] Docker container for isolated execution
- [ ] Webhooks instead of polling (GitHub → Agent)
- [ ] Token budget tracking per issue
- [ ] Multi-issue queue with prioritization
- [ ] Slack/Discord notifications on PR creation

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

Contributions welcome! Feel free to open issues or submit PRs.
