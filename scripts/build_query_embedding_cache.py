"""Build the fixed-query embedding cache (rag_index/fixed_query_embeddings.json).

The report / risk-summary / decision-intelligence / Ask-HRI-risk flows only ever
send retrieval one of a finite, deterministic set of evidence-query strings:
`DEFAULT_EVIDENCE_QUERIES` plus every phrase in
`app.decision_support.topic_mapping.FEATURE_TOPIC_MAP`. This script embeds each
of those strings ONCE, with the same `app.rag.embedding_model.embed_texts` the
retrieval service uses (one string per call, exactly as retrieval calls it), and
stores the vectors so those flows do not need to load torch / the embedding model
at request time -- see backend/app/rag/query_embedding_cache.py for the runtime
side and its safety properties.

Output is deterministic (sorted by query string, no timestamps), so re-running it
on an unchanged model reproduces the committed file.

Re-run this whenever `DEFAULT_EVIDENCE_QUERIES` or `FEATURE_TOPIC_MAP` changes, or
the embedding model changes (backend/tests/test_query_embedding_cache.py fails if
the committed file is missing any fixed query).

Usage (from repo root, using the existing backend/.venv):
    ./backend/.venv/Scripts/python.exe -m scripts.build_query_embedding_cache
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"

# Same import pattern as scripts/build_rag_index.py / scripts/load_db.py.
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.decision_support.evidence import DEFAULT_EVIDENCE_QUERIES  # noqa: E402
from app.decision_support.topic_mapping import FEATURE_TOPIC_MAP  # noqa: E402
from app.rag.config import (  # noqa: E402
    EMBEDDING_DIM,
    EMBEDDING_MODEL_NAME,
    FIXED_QUERY_EMBEDDINGS_PATH,
    NORMALIZE_EMBEDDINGS,
)
from app.rag.embedding_model import embed_texts  # noqa: E402


def enumerate_fixed_queries() -> list[str]:
    """Every distinct query string the evidence pipeline can send to retrieval,
    sorted for a deterministic output file."""
    return sorted(set(DEFAULT_EVIDENCE_QUERIES) | set(FEATURE_TOPIC_MAP.values()))


def build_payload_text(queries: list[str]) -> str:
    """Serializes the artifact as JSON text, one query per line. Vectors are
    float32 values written via their exact double representation, so reading
    them back into float32 is bit-exact."""
    entries = []
    for query in queries:
        vector = embed_texts([query])[0]
        if vector.shape != (EMBEDDING_DIM,):
            raise RuntimeError(f"Unexpected embedding shape {vector.shape} for query {query!r}.")
        entries.append((query, vector.tolist()))

    lines = [
        "{",
        f'  "embedding_model": {json.dumps(EMBEDDING_MODEL_NAME)},',
        f'  "embedding_dim": {EMBEDDING_DIM},',
        f'  "normalized": {json.dumps(NORMALIZE_EMBEDDINGS)},',
        f'  "query_count": {len(entries)},',
        '  "queries": {',
    ]
    for i, (query, values) in enumerate(entries):
        comma = "," if i < len(entries) - 1 else ""
        lines.append(f"    {json.dumps(query, ensure_ascii=False)}: {json.dumps(values)}{comma}")
    lines += ["  }", "}", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=FIXED_QUERY_EMBEDDINGS_PATH)
    args = parser.parse_args()

    queries = enumerate_fixed_queries()
    print(f"Fixed evidence queries: {len(queries)}")
    print(f"Embedding model:        {EMBEDDING_MODEL_NAME} (dim={EMBEDDING_DIM}, normalized={NORMALIZE_EMBEDDINGS})")

    text = build_payload_text(queries)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8", newline="\n")
    print(f"Wrote {args.output} ({len(text.encode('utf-8')):,} bytes)")


if __name__ == "__main__":
    main()
