"""Single shared embedding-model loader, used for both document chunks
(index build time) and queries (retrieval time). Loading the model is
comparatively expensive (~1-4s, CPU-only) so it is cached as a module-level
singleton -- loaded once per process, never per call.
"""

from __future__ import annotations

import numpy as np

from app.rag.config import EMBEDDING_DIM, EMBEDDING_MODEL_NAME, NORMALIZE_EMBEDDINGS

_MODEL = None


def get_embedding_model():
    global _MODEL
    if _MODEL is None:
        from sentence_transformers import SentenceTransformer

        _MODEL = SentenceTransformer(EMBEDDING_MODEL_NAME)
        actual_dim = _MODEL.get_sentence_embedding_dimension()
        if actual_dim != EMBEDDING_DIM:
            raise RuntimeError(
                f"Loaded embedding model '{EMBEDDING_MODEL_NAME}' reports dimension "
                f"{actual_dim}, expected {EMBEDDING_DIM}. Refusing to continue with an "
                "unexpected embedding shape."
            )
    return _MODEL


def embed_texts(texts: list[str]) -> np.ndarray:
    """Encodes a list of strings to a (len(texts), EMBEDDING_DIM) float32
    array, L2-normalized when NORMALIZE_EMBEDDINGS is True (so that FAISS
    IndexFlatIP inner product == cosine similarity)."""
    model = get_embedding_model()
    embeddings = model.encode(
        list(texts),
        normalize_embeddings=NORMALIZE_EMBEDDINGS,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    return embeddings.astype(np.float32)
