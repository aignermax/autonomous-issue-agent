#!/usr/bin/env python3
"""
Semantic Code Search Tool for Autonomous Agent

Simple semantic search over codebase using OpenAI embeddings.
Can be called from agent via Bash - no MCP needed!

Usage:
    python semantic_search.py "find ViewModel for parameter sweeping"
    python semantic_search.py "where is the bounding box calculation logic?"
    python semantic_search.py "test files for analysis features"
"""

import os
import sys
import json
import hashlib
from pathlib import Path
from typing import List, Dict, Tuple
import openai
from dotenv import load_dotenv

# Load environment variables
load_dotenv(Path(__file__).parent.parent / ".env")

# Configuration
CACHE_DIR = Path(__file__).parent / ".search_cache"
INDEX_FILE = CACHE_DIR / "code_index.json"
EMBEDDING_MODEL = "text-embedding-3-small"  # Cheap and fast
TOP_K = 5  # Return top 5 results

# File patterns to index
INCLUDE_PATTERNS = [
    "**/*.cs",      # C# files
    "**/*.axaml",   # Avalonia XAML
    "**/*.md",      # Documentation
]

EXCLUDE_PATTERNS = [
    "**/bin/**",
    "**/obj/**",
    "**/.git/**",
    "**/node_modules/**",
]


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot_product = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    return dot_product / (norm_a * norm_b) if norm_a and norm_b else 0.0


def get_file_hash(path: Path) -> str:
    """Get hash of file for caching."""
    return hashlib.md5(path.read_bytes()).hexdigest()


def should_index_file(path: Path, repo_root: Path) -> bool:
    """Check if file should be indexed."""
    rel_path = path.relative_to(repo_root)

    # Check exclusions
    for pattern in EXCLUDE_PATTERNS:
        if rel_path.match(pattern):
            return False

    # Check inclusions
    for pattern in INCLUDE_PATTERNS:
        if rel_path.match(pattern):
            return True

    return False


def extract_code_chunks(file_path: Path) -> List[Dict[str, str]]:
    """Extract meaningful chunks from a code file."""
    try:
        content = file_path.read_text(encoding='utf-8')
    except:
        return []

    chunks = []

    # For C# files, extract classes and methods
    if file_path.suffix == '.cs':
        lines = content.split('\n')
        current_chunk = []
        chunk_start_line = 0

        for i, line in enumerate(lines):
            stripped = line.strip()

            # Start of class or method
            if any(keyword in stripped for keyword in ['class ', 'interface ', 'public ', 'private ', 'protected ']):
                if current_chunk:
                    chunks.append({
                        'file': str(file_path),
                        'lines': f"{chunk_start_line}-{i}",
                        'content': '\n'.join(current_chunk[:50])  # Limit to 50 lines per chunk
                    })
                current_chunk = [line]
                chunk_start_line = i + 1
            else:
                current_chunk.append(line)

        # Add last chunk
        if current_chunk:
            chunks.append({
                'file': str(file_path),
                'lines': f"{chunk_start_line}-{len(lines)}",
                'content': '\n'.join(current_chunk[:50])
            })
    else:
        # For other files, just use full content (truncated)
        chunks.append({
            'file': str(file_path),
            'lines': '1-end',
            'content': content[:5000]  # First 5000 chars
        })

    return chunks


def build_index(repo_root: Path, force_rebuild: bool = False) -> Dict:
    """Build or load code index with embeddings."""
    CACHE_DIR.mkdir(exist_ok=True)

    # Check if index exists and is fresh
    if INDEX_FILE.exists() and not force_rebuild:
        print(f"Loading existing index from {INDEX_FILE}", file=sys.stderr)
        with open(INDEX_FILE, 'r') as f:
            return json.load(f)

    print(f"Building code index for {repo_root}...", file=sys.stderr)

    # Find all code files
    code_files = []
    for pattern in INCLUDE_PATTERNS:
        code_files.extend(repo_root.glob(pattern))

    code_files = [f for f in code_files if should_index_file(f, repo_root)]

    print(f"Found {len(code_files)} files to index", file=sys.stderr)

    # Extract chunks
    all_chunks = []
    for file_path in code_files:
        chunks = extract_code_chunks(file_path)
        all_chunks.extend(chunks)

    print(f"Extracted {len(all_chunks)} code chunks", file=sys.stderr)

    # Get embeddings (batch for efficiency)
    if not os.environ.get('OPENAI_API_KEY'):
        print("ERROR: OPENAI_API_KEY not set. Cannot create embeddings.", file=sys.stderr)
        sys.exit(1)

    client = openai.OpenAI()

    print(f"Computing embeddings...", file=sys.stderr)
    texts = [chunk['content'] for chunk in all_chunks]

    # Batch embeddings (max 2048 per request)
    batch_size = 2048
    all_embeddings = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i+batch_size]
        print(f"  Batch {i//batch_size + 1}/{(len(texts)-1)//batch_size + 1}", file=sys.stderr)

        response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=batch
        )
        all_embeddings.extend([item.embedding for item in response.data])

    # Build index
    index = {
        'chunks': all_chunks,
        'embeddings': all_embeddings,
        'repo_root': str(repo_root),
        'num_files': len(code_files),
        'num_chunks': len(all_chunks)
    }

    # Save index
    with open(INDEX_FILE, 'w') as f:
        json.dump(index, f)

    print(f"Index saved to {INDEX_FILE}", file=sys.stderr)
    return index


def search(query: str, index: Dict, top_k: int = TOP_K) -> List[Tuple[str, float, str]]:
    """Search for relevant code chunks."""
    # Get query embedding
    client = openai.OpenAI()

    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=query
    )
    query_embedding = response.data[0].embedding

    # Compute similarities
    similarities = []
    for i, chunk_embedding in enumerate(index['embeddings']):
        sim = cosine_similarity(query_embedding, chunk_embedding)
        similarities.append((i, sim))

    # Sort by similarity
    similarities.sort(key=lambda x: x[1], reverse=True)

    # Return top-k results
    results = []
    for i, sim in similarities[:top_k]:
        chunk = index['chunks'][i]
        results.append((
            chunk['file'],
            sim,
            chunk['lines']
        ))

    return results


def main():
    if len(sys.argv) < 2:
        print("Usage: semantic_search.py <query>", file=sys.stderr)
        print("Example: semantic_search.py 'find ViewModel for analysis features'", file=sys.stderr)
        sys.exit(1)

    query = ' '.join(sys.argv[1:])

    # Determine repo root - support two scenarios:
    # 1. Tool in autonomous-issue-agent/tools/ → repo is ../repo/
    # 2. Tool in Connect-A-PIC-Pro/tools/ → repo is ../

    tool_dir = Path(__file__).parent
    parent_dir = tool_dir.parent

    # First check if parent directory looks like the actual project (has .sln or .csproj)
    has_solution = list(parent_dir.glob("*.sln"))
    has_project = (parent_dir / "Connect-A-Pic-Core").exists()

    if has_solution or has_project:
        # We're directly in the project! (tools/ is inside Connect-A-PIC-Pro/)
        repo_root = parent_dir
    # Otherwise check if we're in autonomous-issue-agent setup (has separate repo/ directory)
    elif (parent_dir / "repo").exists():
        repo_root = parent_dir / "repo"
    # Fallback: use current working directory
    else:
        repo_root = Path.cwd()

    if not repo_root.exists():
        print(f"ERROR: Repository not found at {repo_root}", file=sys.stderr)
        print(f"       Tool location: {tool_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"📁 Repository: {repo_root}", file=sys.stderr)

    # Build or load index
    force_rebuild = '--rebuild' in sys.argv
    index = build_index(repo_root, force_rebuild=force_rebuild)

    # Search
    print(f"\nSearching for: {query}\n", file=sys.stderr)
    results = search(query, index)

    # Output results (parseable format for agent)
    print("## Relevant Files:")
    for file_path, score, lines in results:
        # Make path relative to repo root
        rel_path = Path(file_path).relative_to(repo_root)
        print(f"- {rel_path} (score: {score:.3f}, lines: {lines})")

    # Also output detailed results to stderr for debugging
    print("\n## Details:", file=sys.stderr)
    for file_path, score, lines in results:
        rel_path = Path(file_path).relative_to(repo_root)
        print(f"\n{rel_path} (similarity: {score:.3f})", file=sys.stderr)
        print(f"  Lines: {lines}", file=sys.stderr)


if __name__ == '__main__':
    main()
