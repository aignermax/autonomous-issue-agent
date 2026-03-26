# Search Code (Semantic)

Use semantic search to find relevant code using AI embeddings.

## Instructions

Run the semantic search tool with the user's query:

```bash
python3 ~/.cap-tools/semantic_search.py "<query>"
```

Show the results to the user, then optionally read the most relevant files.

## Examples

- `/search-code ViewModel for parameter sweeping`
- `/search-code where is bounding box calculation`
- `/search-code test files for components`

The tool uses OpenAI embeddings to find semantically similar code - much better than grep!
