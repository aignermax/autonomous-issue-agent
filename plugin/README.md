# Autonomous Issue Agent - Claude Code Plugin

This plugin provides autonomous GitHub issue processing capabilities for Claude Code with full MCP integration.

## Features

- ✅ **GitHub MCP Integration** - Direct GitHub API access for issues and PRs
- ✅ **OpenViking MCP Integration** - Semantic code search (93% token reduction)
- ✅ **Autonomous Loop** - Continuously monitors and processes issues
- ✅ **CLAUDE.md Compliance** - Follows repository architecture rules
- ✅ **Vertical Slice Enforcement** - Every feature includes Core + ViewModel + View + Tests

## How It Works

The plugin runs autonomously in Claude Code and:

1. **Checks for Issues** - Monitors repository for issues with `agent-task` label
2. **Analyzes Issue** - Uses GitHub MCP to fetch details, OpenViking to search code
3. **Plans Solution** - Creates implementation plan following CLAUDE.md rules
4. **Implements** - Creates complete vertical slice (Core + ViewModel + View + Tests)
5. **Tests** - Runs `dotnet build` and `dotnet test`
6. **Creates PR** - Uses GitHub MCP to create PR and link to issue
7. **Loops** - Waits 15 seconds and repeats

## Installation

### 1. Prerequisites

Ensure you have:
- Claude Code installed
- GitHub Personal Access Token with `repo` scope
- OpenAI API Key (for OpenViking semantic search)

### 2. Set Environment Variables

```bash
export GITHUB_TOKEN="ghp_your_token_here"
export OPENAI_API_KEY="sk-your_key_here"
```

Or create a `.env` file in your project root.

### 3. Install the Plugin

In Claude Code:

```bash
# Navigate to your project
cd /path/to/Connect-A-PIC-Pro

# Install the plugin from this repository
/plugin install /path/to/autonomous-issue-agent/plugin
```

### 4. Verify MCP Servers

The plugin bundles two MCP servers:
- **github** - GitHub API integration
- **openviking** - Semantic code search

Check they're running:
```bash
/mcp status
```

## Usage

### Start the Autonomous Agent

The plugin doesn't need manual invocation. Once installed, you can:

**Option 1: Use Skills Directly**
```bash
# Check for issues
/autonomous-issue-agent:check-issues

# Process a specific issue
/autonomous-issue-agent:process-issue
```

**Option 2: Let Claude Code Auto-Invoke**
The skills are marked as "model-invoked", meaning Claude Code will automatically use them when appropriate based on context.

### Monitor Progress

Watch the agent work:
```bash
# In Claude Code, you'll see:
# - Issue discovery
# - Code analysis with OpenViking
# - Implementation progress
# - Build/test results
# - PR creation
```

### Stop the Agent

Simply close Claude Code or use:
```bash
/plugin disable autonomous-issue-agent
```

## Skills Reference

### check-issues
Scans the repository for open issues labeled `agent-task` and returns the highest priority issue to work on.

**Filters:**
- Must have `agent-task` label
- Excludes issues with existing PR links
- Excludes `blocked`, `wontfix`, `duplicate` labels
- Prioritizes by `priority:high/medium/low` labels

### process-issue
Complete workflow from issue analysis to PR creation:
1. Fetch issue details (GitHub MCP)
2. Read CLAUDE.md architecture rules
3. Search relevant code (OpenViking MCP)
4. Plan vertical slice implementation
5. Implement Core + ViewModel + View + Tests
6. Run build and tests
7. Create PR (GitHub MCP)

## Configuration

### Polling Interval

By default, the agent checks for new issues every 15 seconds. This is configured in the Python agent version. In the plugin version, Claude Code manages the timing automatically.

### Issue Label

The agent looks for issues with the `agent-task` label. To change this, modify the skill instructions in `skills/check-issues.md`.

### Repository Rules

The agent reads `CLAUDE.md` from your repository root to understand:
- Architecture patterns (MVVM, SOLID principles)
- File size limits (250 lines per new file)
- Vertical slice requirements
- Testing expectations
- Code style conventions

## MCP Servers

### GitHub MCP

Provides tools:
- `github_list_issues` - List issues with filters
- `github_get_issue` - Get issue details
- `github_create_pull_request` - Create PR
- `github_add_comment` - Add issue/PR comments

### OpenViking MCP

Provides semantic code search:
- Reduces token usage by ~93% (23k → 1.6k tokens per issue)
- Finds relevant code without reading entire codebase
- Uses embeddings for intelligent search

**Cost Comparison:**
- Without MCP: ~$0.069 per issue (23k tokens)
- With MCP: ~$0.005 per issue (1.6k tokens)
- Savings: **~$6.40 per 100 issues**

## Comparison with Python Agent

| Feature | Python Agent | Plugin Agent |
|---------|-------------|--------------|
| MCP Support | ❌ Hangs in subprocess | ✅ Native support |
| Token Usage | ~23k per issue | ~1.6k per issue (93% reduction) |
| GitHub Integration | REST API via subprocess | ✅ GitHub MCP (native) |
| Code Search | Full file reads | ✅ OpenViking (semantic) |
| Setup Complexity | Python deps + env setup | Plugin install |
| Maintenance | Custom Python code | Declarative skills |
| Extensibility | Code changes required | Add new skills (markdown) |

## Troubleshooting

### MCP Servers Not Starting

Check environment variables:
```bash
echo $GITHUB_TOKEN
echo $OPENAI_API_KEY
```

Restart Claude Code to reload environment.

### GitHub Rate Limits

The agent respects GitHub API rate limits. If you hit limits:
- Wait for rate limit reset (1 hour)
- Use GitHub Enterprise token (higher limits)
- Reduce polling frequency

### Build/Test Failures

The agent will:
1. Attempt to fix the error
2. Retry build/test
3. If still failing after 2 attempts, comment on the issue

You can then manually intervene and fix the issue.

## Development

### Modifying Skills

Skills are plain markdown files in `skills/`. To modify behavior:

1. Edit the skill markdown file
2. Save changes
3. Reload plugin: `/reload-plugins`

No code changes required!

### Adding New Skills

Create a new markdown file in `skills/`:

```markdown
# My New Skill

Instructions for Claude on what to do...
```

Add it to `plugin.json` if you want to expose it as a command.

## License

MIT - See main repository LICENSE file

## Support

- **Issues**: [GitHub Issues](https://github.com/aignermax/autonomous-issue-agent/issues)
- **Documentation**: [Main README](../README.md)
- **Plugin Architecture**: [PLUGIN_ARCHITECTURE.md](../PLUGIN_ARCHITECTURE.md)
