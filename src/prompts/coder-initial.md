Implement issue #{issue_number}: {issue_title}
{branch_note}

## CRITICAL: Read CLAUDE.md First
The repo has `CLAUDE.md` with full architecture guidelines. **Read it immediately.**

## Issue Type
- **Test/Investigation** ("test", "verify", "investigate") → ONLY tests, NO UI
- **User feature** ("add feature", "implement UI") → Full stack (Core + ViewModel + View + Tests)
- **Bugfix** → Fix the bug, add regression test

## Architecture (for NEW features)
1. Core logic (Connect-A-Pic-Core/)
2. ViewModel ([ObservableProperty], [RelayCommand])
3. View/AXAML (MainWindow.axaml)
4. Tests (UnitTests/)

Max 250 lines/file, SOLID principles, XML docs, no magic numbers.

## Before Finishing
1. **Build** (use build analyzer for cleaner output):
   ```bash
   {tools_python} {tools_dir}/build_errors.py --suggest-fixes
   ```
2. **Test** (use smart test tool):
   ```bash
   {tools_python} {tools_dir}/smart_test.py
   ```
3. Fix all errors/warnings
4. **Keep trying until it works**

## Issue #{issue_number}: {issue_title}

{issue_body}

## YOUR TASK

1. Read `CLAUDE.md` for architecture + `CODEBASE_MAP.md` for overview
2. **ALWAYS use semantic search first** (better than glob/grep):
   ```bash
   {tools_python} {tools_dir}/semantic_search.py "your natural language query"
   ```
   Examples: "ViewModel for analysis", "test files for bounding box", "where is GDS export?"
3. Find similar features to reuse patterns
4. Implement:
   - NEW FEATURES → Core + ViewModel + View + Tests
   - TESTS/BUGFIXES → Tests or fix only (NO UI)
5. **ALWAYS use smart test tool** (NOT `dotnet test` directly):
   ```bash
   {tools_python} {tools_dir}/smart_test.py [filter]
   ```
   Shows clean summary instead of 1000+ test results!
6. Build/test iteratively, fix errors immediately
7. **Keep trying until tests pass!**
8. **BEFORE final commit:** Review your own changes:
   - Check for code quality issues
   - Look for potential bugs or edge cases
   - Verify tests cover main scenarios
   - Fix any issues you find BEFORE committing

## ⚠️ CRITICAL: WiX Installer Projects in WSL
**WiX Toolset CANNOT build MSI installers in WSL!**
- If issue involves WiX projects (.wixproj) or MSI installers:
  - Implement the .NET/C# code changes ONLY
  - DO NOT attempt to build WiX projects
  - Add comment in PR: "WiX installer build requires Windows - test manually"
  - Mark as complete after .NET code works
- Attempting to build WiX in WSL wastes tokens and will always fail!

## 🚀 IMPORTANT: Always use tools/ folder tools!
- **build_errors.py** - Filtered build output + fix suggestions (instead of `dotnet build`)
- **semantic_search.py** - AI code search (instead of grep)
- **smart_test.py** - Filtered test output (instead of `dotnet test`)
- **find_symbol.py** - Find class/method definitions + usages (when refactoring/implementing)
- **dotnet_deps.py** - Check NuGet packages (when debugging references/conflicts)

These tools save 500-5000 tokens per use! Use them frequently!
