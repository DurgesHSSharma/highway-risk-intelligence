"""Phase 8 RAG constants. One place for the embedding model identity, the
FAISS index layout, and the relevance threshold, so the index-build script
and the retrieval service can never silently drift apart -- see
docs/RAG_SYSTEM.md for the rationale behind every value here.
"""

from __future__ import annotations

from pathlib import Path

from app.config import REPO_ROOT

# Same model for documents and queries -- required for the similarity
# comparison to be meaningful. Free, local, CPU-compatible, 384-dim, no API
# key (see docs/RAG_SYSTEM.md section "Embedding model").
EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384

# Embeddings are L2-normalized before indexing/querying, and the index is an
# exact FAISS IndexFlatIP -- inner product of unit vectors == cosine
# similarity. See docs/RAG_SYSTEM.md sections "Normalization" / "FAISS index".
NORMALIZE_EMBEDDINGS = True

# Chosen empirically from this corpus's real query score distribution, not
# picked arbitrarily. Measured (see docs/RAG_SYSTEM.md "Relevance threshold"
# for the full experiment): 3 unambiguous out-of-corpus queries topped out at
# 0.244 similarity; the 10 hand-verified in-corpus questions' true-positive
# chunk never scored below 0.459. 0.35 sits centered in that ~0.21-wide gap
# (>=0.10 margin on both sides), so it rejects every measured out-of-corpus
# query while keeping every measured in-corpus true positive.
RELEVANCE_THRESHOLD = 0.35

# A chunk is excluded from embedding/indexing only if it carries no
# meaningful text at all (empty or whitespace-only after stripping). This
# does NOT exclude `suspicious_text` / `low_ocr_quality` flagged chunks --
# those remain searchable, per the Phase 8 brief; their flag is carried into
# every retrieval result instead of being used to drop the chunk.
MIN_CHUNK_TEXT_LENGTH = 1

RAG_INDEX_DIR = REPO_ROOT / "rag_index"
FAISS_INDEX_PATH = RAG_INDEX_DIR / "document_chunks.faiss"
METADATA_PATH = RAG_INDEX_DIR / "metadata.json"
EMBEDDINGS_PATH = RAG_INDEX_DIR / "embeddings.npy"

DOCUMENT_CHUNKS_CSV_PATH = REPO_ROOT / "data" / "processed" / "document_chunks.csv"

# Precomputed embeddings for the FIXED evidence-query strings (see
# app/rag/query_embedding_cache.py) -- lets the report / risk-summary flows
# retrieve evidence without loading the embedding model.
FIXED_QUERY_EMBEDDINGS_PATH = RAG_INDEX_DIR / "fixed_query_embeddings.json"

NOT_FOUND_MESSAGE = "Not found in the available documents."
