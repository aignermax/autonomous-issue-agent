# MCP Benchmark Tool

Measure the impact of MCP (Model Context Protocol) servers on agent token usage and performance.

## What It Does

The benchmark tool runs the agent on the same issue **twice**:
1. **Without MCP** - `.mcp.json` disabled
2. **With MCP** - OpenViking, NetContextServer, etc. enabled

Then compares:
- 🪙 **Token usage** (how many tokens were consumed)
- 💵 **Cost** (in USD)
- ⏱️ **Duration** (how long it took)

## Quick Start

```bash
# Benchmark a specific issue
python benchmark_mcp.py --issue 252 --repo ../Connect-A-PIC-Pro

# The script will:
# 1. Reset the repo to before the fix
# 2. Run agent WITHOUT MCP on the issue
# 3. Reset the repo again
# 4. Run agent WITH MCP on the same issue
# 5. Show comparison and save results
```

## Requirements

- Agent must support `--once <issue>` flag (already implemented)
- Issue should be already solved (so we can reset to before the fix)
- GitHub CLI (`gh`) installed for querying issue metadata
- Write access to the target repository

## How It Works

### Phase 1: Without MCP
```
1. Backup .mcp.json
2. Disable MCP (rename .mcp.json)
3. Reset repo to commit before fix
4. Run: python main.py --once 252
5. Collect tokens, cost, duration
```

### Phase 2: With MCP
```
1. Re-enable MCP (restore .mcp.json)
2. Reset repo to same commit
3. Run: python main.py --once 252
4. Collect tokens, cost, duration
```

### Phase 3: Compare
```
Print comparison table:
- Token savings (%)
- Cost savings ($)
- Duration difference

Save results to benchmark_issue_252.json
```

## Example Output

```
============================================================
BENCHMARK RESULTS - Issue #252
============================================================

Metric                         Without MCP          With MCP             Savings
-------------------------------------------------------------------------------------
Tokens                              26,580            18,234             31.4%
Cost (USD)                          $0.3977           $0.2735            31.2%
Duration (minutes)                     18m               12m              6.0m

============================================================
✅ MCP SAVED 31.4% tokens ($0.1242 USD)
============================================================

📊 Results saved to benchmark_issue_252.json
```

## Best Practices

### Choosing Issues to Benchmark

**Good candidates:**
- Already solved issues with PRs
- Issues requiring code exploration (MCP helps here)
- Medium complexity (not too trivial, not too complex)

**Avoid:**
- Trivial issues (no exploration needed)
- Issues with non-deterministic solutions
- Issues that depend on external state

### Multiple Runs

For statistical significance, run benchmarks multiple times:

```bash
# Run 3 times and average results
for i in {1..3}; do
    python benchmark_mcp.py --issue 252 --repo ../Connect-A-PIC-Pro
    sleep 60  # Cool down between runs
done
```

### Interpreting Results

**Expected MCP benefits:**
- **10-40% token savings** for issues requiring code search
- **Minimal savings** for trivial issues
- **Duration may increase slightly** (MCP server latency)

**When MCP helps most:**
- Finding specific functions/classes
- Understanding codebase structure
- Locating related code across multiple files

**When MCP helps less:**
- Simple bug fixes in known locations
- Adding new isolated features
- Refactoring single files

## Limitations

1. **Not perfectly reproducible** - Claude may take slightly different approaches
2. **Repo state matters** - Ensure clean state before benchmarking
3. **MCP server warmup** - First run may be slower (caching effects)
4. **Network latency** - Can affect MCP server response times

## Troubleshooting

### "Could not find issue"
```bash
# Check issue exists and is accessible
gh issue view 252 --repo aignermax/Connect-A-PIC-Pro
```

### "Repository not found"
```bash
# Verify repo path is correct
ls -la ../Connect-A-PIC-Pro/.git
```

### "Agent failed to process issue"
```bash
# Check agent.log for details
tail -100 agent.log
```

## Advanced: Batch Benchmarking

Benchmark multiple issues at once:

```bash
#!/bin/bash
# benchmark_batch.sh

ISSUES=(242 243 244 248)
REPO="../Connect-A-PIC-Pro"

for issue in "${ISSUES[@]}"; do
    echo "Benchmarking issue #$issue..."
    python benchmark_mcp.py --issue $issue --repo $REPO
    sleep 120  # 2 minute cooldown
done

# Aggregate results
python analyze_benchmarks.py
```

## Future Enhancements

- [ ] Support for multiple MCP configurations (OpenViking only, NetContextServer only, both)
- [ ] Automatic detection of base commit
- [ ] Parallel benchmark runs for faster results
- [ ] Web dashboard for viewing benchmark history
- [ ] Integration with CI/CD to track MCP improvements over time

## Contributing

Found ways to improve the benchmark tool? Please submit a PR!

## See Also

- [MCP Documentation](../README.md#mcp-integration)
- [Dashboard Tool](../src/dashboard.py)
- [Agent Architecture](../docs/architecture.md)
