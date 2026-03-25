# MCP Testing Guide

## The Nested Session Problem

When running the agent from within a Claude Code session (like when Claude is helping you), MCP **will hang** due to nested session conflicts.

### Why It Happens

```
Claude Code Session (you talking to me)
  └─> Agent spawns subprocess
      └─> Claude Code with MCP
          └─> ❌ HANGS due to nested MCP conflict
```

The agent logs show:
```
WARNING: Running inside a Claude Code session!
This may cause nested session conflicts.
Recommended: Run in a separate terminal window.
```

## Solution: Run Tests Outside Claude Code

### Quick Test

Open a **separate terminal** (not in Claude Code) and run:

```bash
cd /home/aigner/connect-a-pic-agent
./test_mcp_fix.sh
```

This will:
1. Test Claude with MCP using the new `--permission-mode bypassPermissions` flag
2. Run the full benchmark Phase 2 (WITH MCP)
3. Show token comparison results

### Manual Benchmark

To run the full benchmark from scratch:

```bash
cd /home/aigner/connect-a-pic-agent
source venv/bin/activate

# Full benchmark (both phases)
python3 benchmark_mcp.py --issue 251 --repo ./repo

# Or just Phase 2 if Phase 1 results exist
python3 benchmark_mcp.py --issue 251 --repo ./repo --mcp-only
```

## The Fix

**Before** (caused hangs with MCP):
```python
if not has_mcp:
    cmd.append("--dangerously-skip-permissions")
```

**After** (works with MCP):
```python
# Always use permission-mode bypassPermissions (works with MCP)
cmd.extend(["--permission-mode", "bypassPermissions"])
```

The key insight: `--dangerously-skip-permissions` is incompatible with MCP, but `--permission-mode bypassPermissions` works fine with MCP.

## Expected Results

**Phase 1 (WITHOUT MCP):**
- Tokens: ~23,429
- Cost: ~$0.31
- Duration: ~11 minutes

**Phase 2 (WITH MCP):**
- Should complete in similar time
- Should show token savings if MCP helps reduce context

## Monitoring

Use the interactive dashboard to monitor progress:

```bash
./dashboard_interactive.sh
```

Press `[b]` to start benchmark, `[l]` to view logs, `[a]` to toggle auto-refresh.
