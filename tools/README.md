# Agent Tools

Custom Python tools for the autonomous agent. Call via Bash with full path.

## 🔍 semantic_search.py

**AI-powered code search** using OpenAI embeddings.

```bash
/home/aigner/connect-a-pic-agent/venv/bin/python3 /home/aigner/connect-a-pic-agent/tools/semantic_search.py "query"
```

**Examples:**
- `"ViewModel for parameter sweeping"` - Find relevant ViewModels
- `"where is bounding box calculation?"` - Find implementation
- `"test files for routing"` - Find test files

**Output:** List of files with similarity scores.

**First run:** Indexes codebase (~2 min, $0.05 cost). Cached after.

**Rebuild index:** Add `--rebuild` flag.

---

## 🧪 smart_test.py

**Filtered dotnet test output** - shows only summary instead of all test results.

```bash
/home/aigner/connect-a-pic-agent/venv/bin/python3 /home/aigner/connect-a-pic-agent/tools/smart_test.py [filter]
```

**Examples:**
- `smart_test.py` - Run all tests, compact summary
- `smart_test.py ParameterSweeper` - Only ParameterSweeper tests
- `smart_test.py --file MyTests.cs` - Run specific file

**Output:**
```
[OK] 47 tests passed (0 failed, 0 skipped) in 2.3s
```

**Benefits:** Avoids overwhelming output from 1193 tests.

---

## Setup

Both tools require the agent's venv:
```bash
cd /home/aigner/connect-a-pic-agent
source venv/bin/activate
pip install openai python-dotenv  # For semantic_search
```

`OPENAI_API_KEY` required in `.env` for semantic_search.

---

## Integration

Agent prompts include full commands with absolute paths. No manual configuration needed.
