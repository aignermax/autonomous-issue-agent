# Script Overview

Quick reference for all scripts in this repository.

## 🚀 Main Entry Points

### `setup.sh`
**Smart installation script** - Run this first!

```bash
./setup.sh
```

Automatically:
- Detects environment (WSL, Linux, Mac)
- Checks what's already installed
- Analyzes target repositories
- Installs only missing dependencies
- Configures Python venv
- Creates .env from template

### `start.bat` (Windows)
**Windows launcher** — double-click to start agent + dashboard.

Thin wrapper that opens WSL (prefers Windows Terminal) and runs `run.sh`.

### `start-agent-autostart.bat` (Windows)
**Wrapper for shell:startup / Task Scheduler.** Just calls `start.bat`, so the launch logic stays in one place.

### `run.sh` (Linux/Mac, WSL)
**Single source of truth.** Sets up the PATH (dotnet, codegraph, cargo), starts the agent in the background, and runs the interactive dashboard in the foreground.

```bash
./run.sh
```

Features:
- Real-time agent status
- Repository monitoring
- Start/stop controls
- Token usage tracking
- CPU and session info
- Uses `gnome-session-inhibit` when available to prevent system sleep

## 📦 Tools (in `tools/` directory)

### `tools/install.sh`
**Install development tools** to `~/.cap-tools/`

```bash
curl -sSL https://raw.githubusercontent.com/aignermax/autonomous-issue-agent/main/tools/install.sh | bash
```

Installs:
- `semantic_search.py` - AI-powered code search
- `smart_test.py` - Filtered test output

### `tools/semantic_search.py`
AI-powered semantic code search using embeddings.

```bash
python3 tools/semantic_search.py "routing algorithms"
```

### `tools/smart_test.py`
Smart test runner that filters overwhelming output.

```bash
python3 tools/smart_test.py          # Run all tests
python3 tools/smart_test.py MyTest   # Filter specific tests
```

## 🗑️ Removed Scripts (Cleanup)

The following scripts were removed to reduce confusion:

- ❌ `start_agent_wsl.sh` - Obsolete, replaced by `run.sh`
- ❌ `TOOLS_INSTALL.md` - Moved to GitHub releases
- ❌ Root-level `install.sh` - Moved to `tools/install.sh`
- ❌ Root-level `VERSION` - Moved to `tools/VERSION`

## 📋 Decision Tree

**Setting up for the first time?**
→ Run `./setup.sh`

**On Windows?**
→ Double-click `start.bat`

**On Linux/Mac / inside WSL?**
→ Run `./run.sh`

**Want to install tools for Claude Code?**
→ Use `tools/install.sh`

**Want unattended startup after Windows reboots?**
→ See `AUTOSTART.md` — point Task Scheduler at `start-agent-autostart.bat`
