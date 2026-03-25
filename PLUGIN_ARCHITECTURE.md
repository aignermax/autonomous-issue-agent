# Claude Code Plugin Architecture - Lösung für MCP Integration

## Das Problem

Der aktuelle Agent startet Claude Code als **Subprocess** und übergibt Prompts via Kommandozeile:
```bash
claude -p "Fix issue #123" --output-format json --mcp-config .mcp.json
```

**Problem:** MCP Server hängen sich auf, wenn Claude Code als Subprocess gestartet wird. MCP funktioniert nur in **interaktiven Claude Code Sessions**, nicht in Subprocess-Automation.

## Die Lösung: Claude Code Plugins

Anstatt Claude Code von außen zu steuern, können wir **innerhalb von Claude Code** arbeiten und ein Plugin erstellen, das die Agent-Logik implementiert.

### Wie Plugins funktionieren

Plugins werden **direkt in Claude Code** geladen und ausgeführt:
- Plugin MCP Server starten automatisch wenn das Plugin aktiviert wird
- MCP Server laufen im gleichen Kontext wie Claude Code (kein Subprocess-Problem!)
- Plugins können **Skills** und **Agents** definieren
- Plugins haben Zugriff auf GitHub MCP Server

### Plugin-Struktur für Issue Agent

```
autonomous-issue-agent-plugin/
├── .claude-plugin/
│   └── plugin.json          # Plugin Manifest
├── .mcp.json                # MCP Server Config (GitHub, OpenViking, etc.)
├── skills/
│   ├── check-issues.md      # Skill: Hole offene GitHub Issues
│   ├── analyze-issue.md     # Skill: Analysiere Issue und plane Lösung
│   └── create-pr.md         # Skill: Erstelle Pull Request
└── agents/
    └── issue-worker.json    # Agent Definition für autonome Issue-Bearbeitung
```

## Verfügbare MCP Server im Plugin

Das Plugin kann alle MCP Server bündeln, die wir brauchen:

### 1. GitHub MCP Server (offiziell)
```json
{
  "mcpServers": {
    "github": {
      "command": "github-mcp-server",
      "env": {
        "GITHUB_TOKEN": "${GITHUB_TOKEN}"
      }
    }
  }
}
```

**Capabilities:**
- Issues auflisten: `github_list_issues`
- Issue Details: `github_get_issue`
- PR erstellen: `github_create_pull_request`
- Code durchsuchen: `github_search_code`

### 2. OpenViking (Semantic Code Search)
```json
{
  "mcpServers": {
    "openviking": {
      "command": "openviking-server",
      "env": {
        "OPENAI_API_KEY": "${OPENAI_API_KEY}"
      }
    }
  }
}
```

**Vorteil:** 93% Token-Reduktion durch semantische Suche!

### 3. dotnet-test-mcp (für Connect-A-PIC Testing)
```json
{
  "mcpServers": {
    "dotnet-test": {
      "command": "dotnet-test-mcp"
    }
  }
}
```

## Plugin Implementation

### plugin.json

```json
{
  "name": "autonomous-issue-agent",
  "version": "1.0.0",
  "description": "Autonomous GitHub Issue Agent with MCP integration",
  "author": "Max Aigner",
  "main": ".claude-plugin/plugin.json",
  "skills": [
    {
      "name": "check-issues",
      "description": "Check for open GitHub issues",
      "file": "skills/check-issues.md"
    },
    {
      "name": "process-issue",
      "description": "Analyze and fix a GitHub issue",
      "file": "skills/process-issue.md"
    }
  ],
  "agents": [
    {
      "name": "issue-worker",
      "description": "Autonomous issue processing agent",
      "file": "agents/issue-worker.json"
    }
  ]
}
```

### skills/check-issues.md

```markdown
# Check Issues Skill

Use the GitHub MCP server to list open issues:

1. Call `github_list_issues` for the repository
2. Filter for issues without PR links
3. Filter out issues with "blocked" or "wontfix" labels
4. Sort by priority labels
5. Return the top issue to work on

If issues found, invoke the `process-issue` skill with the issue number.
```

### skills/process-issue.md

```markdown
# Process Issue Skill

Given an issue number:

1. **Understand Issue**
   - Call `github_get_issue` to get full details
   - Use OpenViking MCP to search relevant code semantically
   - Read CLAUDE.md for architecture rules

2. **Plan Solution**
   - Follow vertical slice requirement from CLAUDE.md
   - Plan Core + ViewModel + View + Tests
   - Verify compliance with 250-line rule

3. **Implement**
   - Use standard Read/Edit/Write tools
   - Run `dotnet build` via Bash
   - Run `dotnet test` via Bash
   - Fix any errors

4. **Create PR**
   - Stage changes with `git add`
   - Commit with structured message
   - Call `github_create_pull_request`
   - Link PR to issue

5. **Log Progress**
   - Append to `agent.log`
   - Update issue with PR link comment
```

### agents/issue-worker.json

```json
{
  "name": "Issue Worker",
  "description": "Autonomous agent that continuously processes GitHub issues",
  "system_prompt": "You are an autonomous GitHub issue agent. Your job is to:\n1. Check for open issues every 30 minutes\n2. Select the highest priority issue\n3. Analyze, implement, test, and create a PR\n4. Move to the next issue\n\nFollow the CLAUDE.md architecture rules strictly.\nEvery feature must be a complete vertical slice with UI.\n\nUse the check-issues and process-issue skills to work autonomously.",
  "tool_permissions": {
    "github": "allow",
    "openviking": "allow",
    "dotnet-test": "allow",
    "bash": "allow",
    "read": "allow",
    "edit": "allow",
    "write": "allow"
  },
  "loop": {
    "enabled": true,
    "interval_minutes": 30,
    "max_iterations": null
  }
}
```

## Workflow im Plugin-Modus

### Statt Python-Agent mit Subprocess:
```
Python Agent → subprocess.run(['claude', '-p', prompt]) → Hangs with MCP
```

### Mit Plugin:
```
Claude Code läuft interaktiv
  ↓
Plugin wird geladen
  ↓
MCP Server starten automatisch (kein Subprocess!)
  ↓
Agent läuft in Claude Code Session
  ↓
Nutzt Skills + MCP Tools
  ↓
Arbeitet Issues ab
```

## Vorteile

1. **MCP funktioniert** - Kein Subprocess-Problem mehr
2. **OpenViking nutzbar** - 93% Token-Reduktion möglich
3. **Bessere Integration** - GitHub MCP hat native API-Integration
4. **Offiziell supported** - Claude Code Plugin System ist die offizielle Lösung
5. **Erweiterbar** - Weitere Skills/MCP Server einfach hinzufügbar

## Beispiel Plugins zur Inspiration

- **Feature Dev** (131k installs) - Feature development workflow mit agents
- **Ralph Loop** (110k installs) - Iterative development mit loop
- **Code Review** (169k installs) - PR review automation
- **GitHub** (141k installs) - Offizielle GitHub Integration

## Nächste Schritte

1. **Plugin erstellen**
   ```bash
   mkdir autonomous-issue-agent-plugin
   cd autonomous-issue-agent-plugin
   mkdir -p .claude-plugin skills agents
   ```

2. **MCP Config migrieren**
   - `.mcp.json` vom Repo ins Plugin kopieren
   - `${CLAUDE_PLUGIN_ROOT}` für Pfade nutzen

3. **Skills definieren**
   - `check-issues.md` - Issue discovery
   - `process-issue.md` - Issue processing

4. **Agent konfigurieren**
   - `issue-worker.json` mit Loop-Modus
   - System Prompt mit CLAUDE.md Regeln

5. **Plugin installieren**
   ```bash
   /plugin install /path/to/autonomous-issue-agent-plugin
   ```

6. **Agent starten**
   ```
   /agent issue-worker
   ```

## Migration vom aktuellen Setup

Der aktuelle Python-Code (`main.py`, `claude_code.py`, etc.) wird **nicht mehr benötigt**.

Stattdessen:
- Agent-Logik → Skills (Markdown)
- Orchestrierung → Agent Definition (JSON)
- MCP Config → Plugin `.mcp.json`

Das Dashboard (`dashboard_interactive.py`) könnte optional bleiben, um den Claude Code Agent zu monitoren, aber die Steuerung läuft direkt in Claude Code.

## Benchmark Erwartung

**Aktuell (ohne MCP):** ~23,000 Tokens pro Issue

**Mit Plugin + OpenViking MCP:** ~1,600 Tokens pro Issue (93% Reduktion)

**Token-Kosten:**
- Claude Sonnet 4.5: $3 / 1M input tokens
- Aktuell: $0.069 pro Issue
- Mit MCP: ~$0.005 pro Issue

Bei 100 Issues: **$6.90 → $0.50** (Ersparnis: $6.40)
