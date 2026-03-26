# CAP Development Tools - Installation Guide

Professional development tools for Connect-A-PIC-Pro that work with any Claude Code instance.

## Features

### 🔍 Semantic Code Search
- AI-powered code search using OpenAI embeddings
- Find code by intent, not just keywords
- 30-50% faster than grep/find
- Natural language queries

### 🧪 Smart Test Runner
- Filtered dotnet test output
- 98.5% output reduction (1193 → 17 lines)
- Shows only summary on success
- Full details on failures

## Quick Install

```bash
curl -sSL https://raw.githubusercontent.com/aignermax/autonomous-issue-agent/main/install.sh | bash
```

This installs tools to `~/.cap-tools/` and provides slash command templates.

## Manual Install

### 1. Download Tools

```bash
mkdir -p ~/.cap-tools
cd ~/.cap-tools

# Download semantic search
curl -sSL https://raw.githubusercontent.com/aignermax/autonomous-issue-agent/main/tools/semantic_search.py -o semantic_search.py
chmod +x semantic_search.py

# Download smart test
curl -sSL https://raw.githubusercontent.com/aignermax/autonomous-issue-agent/main/tools/smart_test.py -o smart_test.py
chmod +x smart_test.py
```

### 2. Install Dependencies

In your project's virtual environment:

```bash
cd your-project
source venv/bin/activate  # or activate your venv
pip install python-dotenv openai
```

### 3. Setup Slash Commands (Optional)

```bash
cd your-project
mkdir -p .claude/commands

# Download command templates
curl -sSL https://raw.githubusercontent.com/aignermax/autonomous-issue-agent/main/examples/commands/search-code.md -o .claude/commands/search-code.md
curl -sSL https://raw.githubusercontent.com/aignermax/autonomous-issue-agent/main/examples/commands/test.md -o .claude/commands/test.md
```

### 4. Configure Environment

Create `.env` in your project root:

```bash
OPENAI_API_KEY=sk-your-key-here
GITHUB_TOKEN=ghp-your-token  # Optional, for GitHub MCP
```

## Usage

### Semantic Search

**Direct call:**
```bash
python3 ~/.cap-tools/semantic_search.py "ViewModel for analysis"
```

**In Claude Code (VSCode Extension or CLI):**
```
/search-code ViewModel for analysis features
```

**Output:**
```
## Relevant Files:
- ParameterSweepViewModel.cs (score: 0.699)
- MainViewModel.cs (score: 0.684)
```

### Smart Test

**Direct call:**
```bash
python3 ~/.cap-tools/smart_test.py ParameterSweeper
```

**In Claude Code:**
```
/test ParameterSweeper
```

**Output:**
```
✅ TESTS PASSED

## Summary
- Total:   7 tests
- Passed:  7 ✅
- Duration: 254 ms
```

## First Time Setup

### Build Semantic Search Index

The first time you use semantic search, it will build an index (~2-3 minutes):

```bash
cd your-project
python3 ~/.cap-tools/semantic_search.py --rebuild "test query"
```

This costs ~$0.05 one-time (OpenAI embeddings). Subsequent searches are instant and free.

## Updating

### Check Version

```bash
cat ~/.cap-tools/VERSION 2>/dev/null || echo "Not installed"
```

### Update to Latest

Re-run the installer:

```bash
curl -sSL https://raw.githubusercontent.com/aignermax/autonomous-issue-agent/main/install.sh | bash
```

Or manually download new versions from:
https://github.com/aignermax/autonomous-issue-agent/releases

## Versioning

Tools follow semantic versioning:
- **1.0.0** - Initial release
- **1.1.0** - New features (backward compatible)
- **2.0.0** - Breaking changes

Check changelog: https://github.com/aignermax/autonomous-issue-agent/releases

## Troubleshooting

### "OPENAI_API_KEY not set"

Create `.env` in your project root with:
```
OPENAI_API_KEY=sk-...
```

### "Module 'openai' not found"

Install in your project venv:
```bash
source venv/bin/activate
pip install openai python-dotenv
```

### Search returns no results

Rebuild the index:
```bash
python3 ~/.cap-tools/semantic_search.py --rebuild "test"
```

### Tests not found

Make sure you're in the project root where the solution file is.

## Uninstall

```bash
rm -rf ~/.cap-tools
rm your-project/.claude/commands/search-code.md
rm your-project/.claude/commands/test.md
```

## Architecture

### Why Not MCP?

These tools intentionally **don't use MCP** because:
- ❌ MCP requires user permissions (not headless-friendly)
- ❌ MCP has subprocess incompatibility
- ✅ Direct Python tools work everywhere
- ✅ No permission prompts
- ✅ Works in automation

### Tool Design

Both tools are:
- **Standalone** - No dependencies on agent code
- **Portable** - Work in any environment
- **Versionable** - Clear version tracking
- **Installable** - One-command install
- **Project-agnostic** - Work in any codebase

## Contributing

Found a bug or want a feature?

1. Open issue: https://github.com/aignermax/autonomous-issue-agent/issues
2. Or submit PR: https://github.com/aignermax/autonomous-issue-agent/pulls

## License

MIT License - See repository for details.

## Support

- Documentation: [Main README](https://github.com/aignermax/autonomous-issue-agent)
- Issues: [GitHub Issues](https://github.com/aignermax/autonomous-issue-agent/issues)
- Discussions: [GitHub Discussions](https://github.com/aignermax/autonomous-issue-agent/discussions)
