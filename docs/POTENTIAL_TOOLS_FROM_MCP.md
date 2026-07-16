# Potential Python Tools from MCP Features

Analysis of which MCP server features could be implemented as standalone Python tools for the autonomous agent.

---

## ✅ Already Implemented

### 1. **Semantic Search** (`tools/semantic_search.py`)
- **MCP equivalent**: NetContextServer semantic search
- **Status**: ✅ Already implemented
- **What it does**: AI-powered code search using embeddings
- **Value**: HIGH - Used frequently by agent

### 2. **Smart Test** (`tools/smart_test.py`)
- **MCP equivalent**: dotnet-test-mcp filtered output
- **Status**: ✅ Already implemented
- **What it does**: Filtered `dotnet test` output (summary only)
- **Value**: HIGH - Saves tokens on every test run

---

## 🎯 High-Value Candidates for Implementation

### 3. **Dependency Analyzer** (`tools/dotnet_deps.py`)
**Source**: NetContextServer package analysis
**What it would do**:
- List all NuGet packages in solution
- Show outdated packages
- Identify security vulnerabilities
- Check for duplicate dependencies

**Commands**:
```python
# List all packages
dotnet_deps.py list

# Check for updates
dotnet_deps.py outdated

# Show dependency tree for a package
dotnet_deps.py tree CommunityToolkit.Mvvm
```

**Use case**:
- Agent investigating package conflicts
- Security audits
- Upgrade planning

**Estimated tokens saved**: 500-1000 per use (vs. manually parsing .csproj files)

**Implementation complexity**: MEDIUM (use `dotnet list package`)

---

### 4. **Test Coverage Analyzer** (`tools/coverage_report.py`)
**Source**: NetContextServer test coverage analysis
**What it would do**:
- Parse coverage.xml files (Coverlet/Cobertura)
- Show coverage % per file
- List uncovered lines
- Identify files with low coverage

**Commands**:
```python
# Generate coverage and show report
coverage_report.py

# Show coverage for specific file
coverage_report.py --file DesignCanvasViewModel.cs

# Find files with <80% coverage
coverage_report.py --threshold 80
```

**Use case**:
- Agent adding tests after feature implementation
- Identifying gaps in test coverage
- PR quality checks

**Estimated tokens saved**: 1000-2000 per use (vs. reading verbose coverage XML)

**Implementation complexity**: MEDIUM (XML parsing)

---

### 5. **Symbol Navigator** (`tools/find_symbol.py`)
**Source**: NetContextServer intelligent navigation
**What it would do**:
- Find definition of class/method/property
- Find all usages of a symbol
- Show inheritance hierarchy
- List implementations of interface

**Commands**:
```python
# Find where DesignCanvasViewModel is defined
find_symbol.py class DesignCanvasViewModel

# Find all usages of PlaceComponent method
find_symbol.py usage PlaceComponent

# Show all classes implementing IComponent
find_symbol.py implements IComponent
```

**Use case**:
- Agent understanding class hierarchies
- Finding where to add new implementations
- Refactoring (find all usages)

**Estimated tokens saved**: 800-1500 per use (vs. grep + manual parsing)

**Implementation complexity**: MEDIUM-HIGH (needs Roslyn or similar)

---

### 6. **GitHub PR Tool** (`tools/github_pr.py`)
**Source**: Not MCP, but useful
**What it would do**:
- Create PR with rich formatting
- Add reviewers
- Link issues
- Update PR description
- Check CI status

**Commands**:
```python
# Create PR from current branch
github_pr.py create --title "Fix #123" --body "Description"

# Add reviewers
github_pr.py add-reviewer aignermax

# Check CI status
github_pr.py status
```

**Use case**:
- Agent creating better PRs
- Adding context to PRs
- Checking if tests pass before marking as done

**Estimated tokens saved**: 300-500 per use

**Implementation complexity**: LOW (PyGithub already used)

---

### 7. **Build Analyzer** (`tools/build_errors.py`)
**Source**: Custom
**What it would do**:
- Parse `dotnet build` output
- Extract only errors and warnings
- Group by severity
- Suggest fixes for common errors

**Commands**:
```python
# Run build and show filtered output
build_errors.py

# Show only errors (no warnings)
build_errors.py --errors-only

# Suggest fixes
build_errors.py --suggest-fixes
```

**Use case**:
- Agent dealing with build failures
- Reducing token usage on verbose build logs
- Getting hints for common issues

**Estimated tokens saved**: 500-1000 per build

**Implementation complexity**: LOW (regex parsing)

---

## 🔍 Medium-Value Candidates

### 8. **File Watcher** (`tools/watch_changes.py`)
- Monitor file changes during development
- Use case: Detecting when build regenerates files
- **Complexity**: LOW

### 9. **Code Metrics** (`tools/metrics.py`)
- Lines of code per file
- Cyclomatic complexity
- Method count
- Use case: Ensuring files stay under 250 lines
- **Complexity**: MEDIUM

### 10. **Architecture Validator** (`tools/validate_arch.py`)
- Check if new code follows CLAUDE.md rules
- Verify vertical slice completeness
- Use case: Pre-commit validation
- **Complexity**: MEDIUM-HIGH

---

## 📊 Priority Ranking

| Tool | Value | Complexity | Token Savings | Priority |
|------|-------|------------|---------------|----------|
| **Dependency Analyzer** | HIGH | MEDIUM | 500-1000 | 🥇 #1 |
| **Test Coverage** | HIGH | MEDIUM | 1000-2000 | 🥈 #2 |
| **Build Analyzer** | HIGH | LOW | 500-1000 | 🥉 #3 |
| GitHub PR Tool | MEDIUM | LOW | 300-500 | #4 |
| Symbol Navigator | MEDIUM | MEDIUM-HIGH | 800-1500 | #5 |
| Code Metrics | LOW | MEDIUM | 200-400 | #6 |

---

## 🎯 Recommended Implementation Plan

### Phase 1 (Quick Wins)
1. **Build Analyzer** (2-3 hours)
   - Low complexity, high impact
   - Saves tokens on every failed build

2. **Dependency Analyzer** (3-4 hours)
   - Uses existing `dotnet` commands
   - Very useful for package management issues

### Phase 2 (High Impact)
3. **Test Coverage** (4-5 hours)
   - Requires XML parsing
   - Helps agent write better tests

4. **GitHub PR Tool** (2-3 hours)
   - PyGithub already available
   - Better PR descriptions

### Phase 3 (Advanced)
5. **Symbol Navigator** (6-8 hours)
   - More complex (Roslyn integration)
   - Very powerful for refactoring

---

## 💡 Notes

**Why Python tools over MCP?**
- ✅ Works in headless subprocess mode
- ✅ No nested session conflicts
- ✅ Easier to debug and test
- ✅ Direct control over input/output
- ✅ No dependency on Claude Code MCP support

**Integration**:
All tools follow same pattern as `semantic_search.py`:
```bash
/home/aigner/connect-a-pic-agent/venv/bin/python3 /home/aigner/connect-a-pic-agent/tools/TOOL_NAME.py [args]
```

**Cost Impact**:
Each tool saves 300-2000 tokens per use. With frequent usage:
- **Build Analyzer**: ~5-10 uses/issue → Save 2500-10k tokens
- **Dependency Analyzer**: ~1-2 uses/issue → Save 500-2k tokens
- **Test Coverage**: ~2-3 uses/issue → Save 2000-6k tokens

**Total potential savings**: 5000-18000 tokens/issue = **€0.30-1.10 per issue**

With 30 issues/month: **€9-33/month savings** from better tools alone!
