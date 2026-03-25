# Installation Guide - Autonomous Issue Agent Plugin

Quick start guide for installing and running the autonomous issue agent as a Claude Code plugin.

## Prerequisites

1. **Claude Code CLI** installed
   ```bash
   which claude
   # Should output: /usr/local/bin/claude (or similar)
   ```

2. **GitHub Personal Access Token** with `repo` scope
   - Create at: https://github.com/settings/tokens
   - Required scopes: `repo` (full control of private repositories)

3. **OpenAI API Key** (for OpenViking semantic search)
   - Get from: https://platform.openai.com/api-keys

4. **Target Repository** cloned locally
   ```bash
   git clone https://github.com/aignermax/Connect-A-PIC-Pro.git
   cd Connect-A-PIC-Pro
   ```

## Step 1: Set Environment Variables

### Linux/Mac

Add to `~/.bashrc` or `~/.zshrc`:

```bash
export GITHUB_TOKEN="ghp_your_token_here"
export OPENAI_API_KEY="sk-your_key_here"
```

Then reload:
```bash
source ~/.bashrc  # or source ~/.zshrc
```

### Verify

```bash
echo $GITHUB_TOKEN
echo $OPENAI_API_KEY
```

Both should output your tokens.

## Step 2: Install OpenViking MCP Server

OpenViking provides semantic code search with 93% token reduction.

```bash
npm install -g openviking-server
```

Verify installation:
```bash
which openviking-server
# Should output: /usr/local/bin/openviking-server (or similar)
```

## Step 3: Install GitHub MCP Server

The GitHub MCP server is installed via npx (will be downloaded automatically when plugin starts).

No manual installation needed!

## Step 4: Install the Plugin

Navigate to your project and start Claude Code:

```bash
cd /path/to/Connect-A-PIC-Pro
claude
```

In Claude Code, install the plugin:

```bash
/plugin install /path/to/autonomous-issue-agent/plugin
```

Example:
```bash
/plugin install /home/aigner/autonomous-issue-agent/plugin
```

## Step 5: Verify Installation

Check that the plugin is installed:

```bash
/plugin list
```

You should see:
```
autonomous-issue-agent (v1.0.0) - Installed
```

## Step 6: Verify MCP Servers

Check that MCP servers are running:

```bash
/mcp status
```

You should see:
```
✅ github - Running
✅ openviking - Running
```

If servers are not running, try:
```bash
/reload-plugins
```

## Step 7: Test the Plugin

### Test Issue Discovery

```bash
List all open issues with the agent-task label
```

Claude Code should use the GitHub MCP to fetch issues.

### Test Semantic Search

```bash
Search the codebase for ViewModel implementations
```

Claude Code should use OpenViking MCP for semantic search.

### Test Full Workflow

If you have an open issue with `agent-task` label:

```bash
Process issue #123 following the CLAUDE.md rules
```

This should trigger the full workflow:
1. Fetch issue details
2. Search relevant code
3. Plan implementation
4. Create vertical slice
5. Run tests
6. Create PR

## Continuous Operation

Once the plugin is installed, you can let it run continuously:

```bash
# In Claude Code:
Every 15 seconds, check for new agent-task issues and process them automatically
```

Claude Code will loop and process issues as they appear.

## Stopping the Agent

To stop the autonomous loop:

```bash
# Disable the plugin
/plugin disable autonomous-issue-agent

# Or just close Claude Code
exit
```

## Troubleshooting

### Problem: MCP Servers Not Starting

**Check environment variables:**
```bash
echo $GITHUB_TOKEN
echo $OPENAI_API_KEY
```

If empty, re-export them and restart Claude Code.

**Check OpenViking installation:**
```bash
openviking-server --version
```

If not found, reinstall:
```bash
npm install -g openviking-server
```

### Problem: GitHub API Rate Limits

**Symptom:** Agent slows down or reports rate limit errors

**Solution:**
- Wait 1 hour for rate limit reset
- Use GitHub Enterprise token (higher limits)
- Reduce polling frequency

### Problem: Build/Test Failures

**Symptom:** Agent creates PRs but tests fail

**Solution:**
- Check `CLAUDE.md` rules are up to date
- Manually review the PR and provide feedback
- Agent will learn from feedback in future iterations

### Problem: Plugin Not Found

**Symptom:** `/plugin install` says plugin not found

**Solution:**
- Use absolute path: `/home/user/autonomous-issue-agent/plugin`
- Verify directory structure:
  ```bash
  ls plugin/.claude-plugin/plugin.json
  # Should exist
  ```

## Updating the Plugin

To update the plugin after making changes:

```bash
# Reload plugins
/reload-plugins
```

No need to uninstall/reinstall!

## Uninstalling

To remove the plugin:

```bash
/plugin uninstall autonomous-issue-agent
```

## Next Steps

- Read [Plugin README](README.md) for detailed usage
- Review [PLUGIN_ARCHITECTURE.md](../PLUGIN_ARCHITECTURE.md) for technical details
- Customize skills in `skills/` directory for your workflow

## Support

Having issues? Open an issue on GitHub:
https://github.com/aignermax/autonomous-issue-agent/issues
