"""Precomputed embeddings for the FIXED set of RAG evidence-query strings.

Why this exists (free-tier memory, no behavior change): the report /
risk-summary / decision-intelligence / Ask-HRI-risk flows never send a
user-typed query to retrieval. They send one of a small, finite, fully
deterministic set of strings -- `DEFAULT_EVIDENCE_QUERIES` plus the topic
phrases in `app.decision_support.topic_mapping.FEATURE_TOPIC_MAP`. Embedding
one of those strings at request time forces the process to import
torch/transformers/sentence-transformers and load the MiniLM weights, which
is by far the largest memory step in this backend (roughly +300 MB over a
~400 MB baseline when measured locally) -- large enough to be a credible
problem on a 512 MB free-tier instance.

This module stores the embedding of each such string, computed offline by
the SAME `app.rag.embedding_model.embed_texts` the retrieval service already
uses (`scripts/build_query_embedding_cache.py`), so retrieval for those
strings reads a stored vector instead of running the model. Everything after
the embedding step -- the FAISS search, the relevance threshold, ranking,
citations -- is untouched.

Safety properties (each covered by backend/tests/test_query_embedding_cache.py):
  * exact-string match only: any query that is not byte-for-byte one of the
    stored strings (free-text document search, Ask HRI document questions,
    a different casing) falls through to the live model, exactly as before;
  * the artifact is used only if its recorded model name, dimension and
    normalization flag match `app.rag.config`; otherwise the whole cache is
    ignored (never partially trusted) and the live model is used;
  * a missing or unreadable artifact is not an error -- it only disables the
    optimization (a warning is logged);
  * cached vectors are returned as copies, so callers can never mutate the
    shared cache.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from app.logging_config import get_logger
from app.rag.config import (
    EMBEDDING_DIM,
    EMBEDDING_MODEL_NAME,
    FIXED_QUERY_EMBEDDINGS_PATH,
    NORMALIZE_EMBEDDINGS,
)
from app.rag.embedding_model import embed_texts

logger = get_logger("app.rag.query_cache")

_CACHE: dict[str, np.ndarray] | None = None


def load_fixed_query_embeddings(path: Path = FIXED_QUERY_EMBEDDINGS_PATH) -> dict[str, np.ndarray]:
    """Reads and validates the artifact at `path`. Returns `{query: (1, EMBEDDING_DIM)
    float32 array}`, or an empty dict (never raises) if the file is missing, unreadable,
    or was produced for a different embedding model/dimension/normalization."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.warning("Fixed-query embedding cache not found at %s; evidence queries will use the live model.", path)
        return {}
    except (OSError, ValueError) as exc:
        logger.warning("Fixed-query embedding cache at %s is unreadable (%s); ignoring it.", path, exc)
        return {}

    if (
        payload.get("embedding_model") != EMBEDDING_MODEL_NAME
        or payload.get("embedding_dim") != EMBEDDING_DIM
        or payload.get("normalized") != NORMALIZE_EMBEDDINGS
    ):
        logger.warning(
            "Fixed-query embedding cache at %s does not match the configured embedding model "
            "(%s, dim=%s, normalized=%s); ignoring it. Regenerate with "
            "`python -m scripts.build_query_embedding_cache`.",
            path,
            EMBEDDING_MODEL_NAME,
            EMBEDDING_DIM,
            NORMALIZE_EMBEDDINGS,
        )
        return {}

    cache: dict[str, np.ndarray] = {}
    for query, values in payload.get("queries", {}).items():
        vector = np.asarray(values, dtype=np.float32)
        if vector.shape != (EMBEDDING_DIM,) or not np.isfinite(vector).all():
            logger.warning(
                "Fixed-query embedding cache at %s has an invalid vector for %r; ignoring the whole cache.", path, query
            )
            return {}
        cache[query] = vector.reshape(1, EMBEDDING_DIM)
    logger.info("Loaded %d fixed-query embeddings from %s.", len(cache), path)
    return cache


def get_cached_query_embedding(query: str) -> np.ndarray | None:
    """Returns a (1, EMBEDDING_DIM) float32 copy of the stored embedding for exactly
    `query`, or None if `query` is not one of the stored fixed strings."""
    global _CACHE
    if _CACHE is None:
        _CACHE = load_fixed_query_embeddings()
    vector = _CACHE.get(query)
    return None if vector is None else vector.copy()


def embed_query(query: str) -> np.ndarray:
    """Query embedding for retrieval: the stored vector when `query` is one of the
    fixed evidence strings, otherwise the live model (lazy-loaded exactly as before)."""
    cached = get_cached_query_embedding(query)
    if cached is not None:
        return cached
    return embed_texts([query])


def reset_fixed_query_cache_for_tests() -> None:
    """Test-only hook to force a fresh load (same convention as
    `app.rag.retrieval.reset_retrieval_service_for_tests`)."""
    global _CACHE
    _CACHE = None
