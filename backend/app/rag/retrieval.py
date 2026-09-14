"""Phase 8 retrieval service: embeds a query with the same model used for
documents, searches the FAISS index, and returns citation-ready ranked
results filtered by the documented relevance threshold (see
docs/RAG_SYSTEM.md "Relevance threshold").

The index/metadata/model are loaded once (module-level singleton via
`get_retrieval_service()`) and reused across requests -- never rebuilt or
reloaded per query. See app/main.py's lifespan for the FastAPI startup wire-up.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from app.rag.config import (
    EMBEDDINGS_PATH,
    FAISS_INDEX_PATH,
    METADATA_PATH,
    RELEVANCE_THRESHOLD,
)
from app.rag.embedding_model import embed_texts


class RagIndexNotBuiltError(RuntimeError):
    pass


class InvalidQueryError(ValueError):
    pass


@dataclass(frozen=True)
class RetrievalResult:
    rank: int
    similarity_score: float
    chunk_id: str
    document_id: str
    page_number: int
    section_heading: str | None
    extraction_method: str
    quality_flag: str | None
    source_filename: str
    text: str

    def citation(self) -> str:
        return f"[{self.document_id}, p. {self.page_number}]"


@dataclass(frozen=True)
class RetrievalResponse:
    query: str
    top_k: int
    threshold: float
    results: list[RetrievalResult]
    not_found: bool


class RetrievalService:
    """Loads the FAISS index + vector-to-chunk mapping once and answers
    `retrieve()` calls against them. Construct via `get_retrieval_service()`
    (module-level singleton), not directly, so the app never loads it twice."""

    def __init__(self, index, mapping: list[dict]):
        self._index = index
        self._mapping = mapping

    @property
    def vector_count(self) -> int:
        return self._index.ntotal

    @property
    def mapping_count(self) -> int:
        return len(self._mapping)

    def retrieve(self, query: str, top_k: int = 5, threshold: float = RELEVANCE_THRESHOLD) -> RetrievalResponse:
        if query is None or not str(query).strip():
            raise InvalidQueryError("Query must be a non-empty string.")
        if top_k < 1:
            raise InvalidQueryError("top_k must be at least 1.")

        query_embedding = embed_texts([query])
        k = min(top_k, self._index.ntotal)
        scores, indices = self._index.search(query_embedding, k)

        candidates: list[RetrievalResult] = []
        for rank, (score, idx) in enumerate(zip(scores[0], indices[0]), start=1):
            if idx < 0:
                continue
            entry = self._mapping[idx]
            candidates.append(
                RetrievalResult(
                    rank=rank,
                    similarity_score=float(score),
                    chunk_id=entry["chunk_id"],
                    document_id=entry["document_id"],
                    page_number=entry["page_number"],
                    section_heading=entry["section_heading"],
                    extraction_method=entry["extraction_method"],
                    quality_flag=entry["extraction_quality_flag"],
                    source_filename=entry["source_filename"],
                    text=entry["text"],
                )
            )

        relevant = [c for c in candidates if c.similarity_score >= threshold]
        # Re-rank so the returned results are numbered 1..len(relevant), even
        # if some higher-rank FAISS candidates fell below the threshold.
        relevant = [
            RetrievalResult(
                rank=i,
                similarity_score=c.similarity_score,
                chunk_id=c.chunk_id,
                document_id=c.document_id,
                page_number=c.page_number,
                section_heading=c.section_heading,
                extraction_method=c.extraction_method,
                quality_flag=c.quality_flag,
                source_filename=c.source_filename,
                text=c.text,
            )
            for i, c in enumerate(relevant, start=1)
        ]

        return RetrievalResponse(
            query=query,
            top_k=top_k,
            threshold=threshold,
            results=relevant,
            not_found=len(relevant) == 0,
        )


_SERVICE: RetrievalService | None = None


def load_retrieval_service(
    index_path=FAISS_INDEX_PATH,
    embeddings_path=EMBEDDINGS_PATH,
    metadata_path=METADATA_PATH,
) -> RetrievalService:
    """Loads the FAISS index and vector-to-chunk mapping from disk. Does NOT
    cache into the module singleton -- use `get_retrieval_service()` for
    that. Raises RagIndexNotBuiltError with a clear message if the index has
    not been built yet (run scripts/build_rag_index.py)."""
    import faiss
    import numpy as np

    if not (index_path.exists() and metadata_path.exists() and embeddings_path.exists()):
        raise RagIndexNotBuiltError(
            f"RAG index not found at {index_path} / {metadata_path} / {embeddings_path}. Run "
            "`python -m scripts.build_rag_index` from the repo root first."
        )

    index = faiss.read_index(str(index_path))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    mapping = metadata["mapping"]
    embeddings = np.load(embeddings_path)

    if not (index.ntotal == len(mapping) == embeddings.shape[0]):
        raise RagIndexNotBuiltError(
            f"RAG index is inconsistent: {index.ntotal} vectors, {len(mapping)} mapping "
            f"entries, {embeddings.shape[0]} rows in embeddings.npy -- these must all match. "
            "Rebuild with `python -m scripts.build_rag_index --force`."
        )

    return RetrievalService(index=index, mapping=mapping)


def get_retrieval_service() -> RetrievalService:
    """Module-level singleton -- loaded once per process and reused across
    requests (see app/main.py lifespan)."""
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = load_retrieval_service()
    return _SERVICE


def reset_retrieval_service_for_tests() -> None:
    """Test-only hook to force a fresh load (e.g. against a temp index)."""
    global _SERVICE
    _SERVICE = None
