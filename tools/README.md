# Semantic Code Search Tool

AI-powered semantic search for the codebase using OpenAI embeddings.

## Purpose

Provides the autonomous agent with **semantic code search** capabilities without needing MCP. The agent can call this tool via Bash to find relevant code based on natural language queries.

## How It Works

1. **Indexing Phase** (first run or with `--rebuild`):
   - Scans all C#, AXAML, and MD files in the repository
   - Extracts meaningful code chunks (classes, methods, documentation)
   - Computes OpenAI embeddings for each chunk
   - Caches the index for fast subsequent searches

2. **Search Phase**:
   - Takes natural language query
   - Computes query embedding
   - Finds top-5 most similar code chunks using cosine similarity
   - Returns file paths with similarity scores

## Usage

### From Agent (via Bash)

```bash
python3 ../tools/semantic_search.py "ViewModel for parameter sweeping"
```

### Examples

```bash
# Find ViewModels for a specific feature
python3 tools/semantic_search.py "ViewModel for analysis features"

# Find implementation details
python3 tools/semantic_search.py "where is bounding box calculation?"

# Find test files
python3 tools/semantic_search.py "test files for parameter sweeping"

# Rebuild index (after major code changes)
python3 tools/semantic_search.py --rebuild "your query"
```

## Output Format

```
## Relevant Files:
- CAP.Avalonia/ViewModels/ParameterSweepViewModel.cs (score: 0.823, lines: 1-127)
- Connect-A-Pic-Core/Analysis/ParameterSweeper.cs (score: 0.781, lines: 1-89)
- UnitTests/Analysis/ParameterSweeperTests.cs (score: 0.712, lines: 1-145)
...
```

## Configuration

### Environment

Requires `OPENAI_API_KEY` in `.env` file.

### File Patterns

Indexes these file types:
- `**/*.cs` - C# source files
- `**/*.axaml` - Avalonia XAML files
- `**/*.md` - Documentation files

Excludes:
- `**/bin/**`, `**/obj/**` - Build artifacts
- `**/.git/**` - Git internals
- `**/node_modules/**` - Dependencies

### Embedding Model

Uses `text-embedding-3-small` for fast, cheap embeddings (~$0.02 per 1M tokens).

## Performance

- **First run** (indexing): ~2-3 minutes for ~5000 code chunks
- **Subsequent searches**: <1 second (uses cached index)
- **Index size**: ~50MB for typical codebase

## Cache

Index is cached in `tools/.search_cache/code_index.json`.

To rebuild:
```bash
python3 tools/semantic_search.py --rebuild "query"
```

## Benefits Over grep/glob

| Feature | grep/glob | Semantic Search |
|---------|-----------|----------------|
| Exact matches | ✅ Fast | ✅ Fast |
| Fuzzy/similar code | ❌ No | ✅ Yes |
| Intent-based search | ❌ No | ✅ Yes |
| Natural language | ❌ No | ✅ Yes |
| Token usage | Low | Low (cached) |
| Setup cost | None | ~$0.10 one-time |

## Cost Analysis

**One-time indexing:**
- ~5000 chunks × ~500 tokens/chunk = 2.5M tokens
- Input embeddings: $0.02 per 1M tokens
- Total: **~$0.05 one-time cost**

**Per search:**
- 1 query × ~20 tokens = 20 tokens
- Cost: **~$0.000001 per search**

Essentially free after initial indexing!

## Integration with Agent

The agent is instructed to use this tool in its task prompt:

```
## 🔍 SEMANTIC SEARCH TOOL

You have access to a semantic code search tool:

python3 ../tools/semantic_search.py "your search query"

Examples:
- python3 ../tools/semantic_search.py "ViewModel for analysis features"
- python3 ../tools/semantic_search.py "where is bounding box calculation?"

This is MUCH better than grep for finding relevant code! Use it early and often.
```

## When to Rebuild Index

Rebuild the index when:
- Adding many new files
- Major refactoring
- Search results seem outdated
- Once per week/month in active development

## Troubleshooting

### "OPENAI_API_KEY not set"
Make sure `.env` file exists with:
```
OPENAI_API_KEY=sk-...
```

### "Module 'openai' not found"
Install in venv:
```bash
source venv/bin/activate
pip install openai
```

### Search returns irrelevant results
Rebuild the index:
```bash
python3 tools/semantic_search.py --rebuild "your query"
```

## Future Enhancements

Possible improvements:
- Incremental indexing (only changed files)
- Larger context chunks for better accuracy
- Hybrid search (semantic + keyword)
- Support for more file types (JSON, YAML, etc.)
