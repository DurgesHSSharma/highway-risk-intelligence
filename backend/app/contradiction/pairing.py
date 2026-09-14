"""Phase 9 cross-document topic pairing.

Reuses the existing Phase 8 embeddings (rag_index/embeddings.npy +
metadata.json) -- no embeddings are recomputed here. Computes the full
cross-document pairwise cosine similarity (embeddings are already
L2-normalized, so this is a single matrix multiply) and keeps only pairs
at or above the Phase 9 topic-pairing threshold (see config.py for how
that threshold was chosen).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.contradiction.config import TOPIC_PAIRING_THRESHOLD


@dataclass(frozen=True)
class CandidatePair:
    chunk_id_a: str
    document_id_a: str
    page_a: int
    chunk_id_b: str
    document_id_b: str
    page_b: int
    similarity: float


def find_candidate_chunk_pairs(
    mapping: list[dict],
    embeddings: np.ndarray,
    threshold: float = TOPIC_PAIRING_THRESHOLD,
) -> list[CandidatePair]:
    """Cross-document chunk pairs whose Phase 8 embeddings' cosine
    similarity meets `threshold`. Never compares a document against
    itself. Deterministically ordered (descending similarity, then
    chunk_id_a, then chunk_id_b) so output never depends on unordered
    dict/set iteration."""
    if embeddings.shape[0] != len(mapping):
        raise ValueError(
            f"Embeddings row count ({embeddings.shape[0]}) does not match mapping length "
            f"({len(mapping)})."
        )

    doc_ids = np.array([m["document_id"] for m in mapping])
    similarity_matrix = embeddings @ embeddings.T
    n = similarity_matrix.shape[0]

    iu, ju = np.triu_indices(n, k=1)
    cross_doc_mask = doc_ids[iu] != doc_ids[ju]
    ci, cj = iu[cross_doc_mask], ju[cross_doc_mask]
    csim = similarity_matrix[ci, cj]

    keep_mask = csim >= threshold
    ci, cj, csim = ci[keep_mask], cj[keep_mask], csim[keep_mask]

    pairs = []
    for i, j, s in zip(ci.tolist(), cj.tolist(), csim.tolist()):
        mi, mj = mapping[i], mapping[j]
        pairs.append(
            CandidatePair(
                chunk_id_a=mi["chunk_id"],
                document_id_a=mi["document_id"],
                page_a=int(mi["page_number"]),
                chunk_id_b=mj["chunk_id"],
                document_id_b=mj["document_id"],
                page_b=int(mj["page_number"]),
                similarity=float(s),
            )
        )

    pairs.sort(key=lambda p: (-round(p.similarity, 6), p.chunk_id_a, p.chunk_id_b))
    return pairs
