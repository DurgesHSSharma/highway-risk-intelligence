"""Builds the Phase 8 FAISS retrieval index from the Phase 7 chunk dataset.

    document_chunks.csv -> filter -> embed (all-MiniLM-L6-v2) -> FAISS IndexFlatIP
                                                                -> embeddings.npy
                                                                -> metadata.json

Reusable core for both `scripts/build_rag_index.py` (CLI) and the test
suite -- mirrors the Phase 6 `app/db/loader.py` convention of keeping the
real logic in `backend/app/` and the script as a thin wrapper.

Corpus size (~860 chunks) is small enough that an exact FAISS IndexFlatIP
(brute-force cosine similarity via inner product on L2-normalized vectors)
is used -- no IVF/HNSW/PQ approximate index. See docs/RAG_SYSTEM.md.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from app.rag.chunks import ChunkFilterResult, load_and_filter_chunks
from app.rag.config import (
    DOCUMENT_CHUNKS_CSV_PATH,
    EMBEDDING_DIM,
    EMBEDDING_MODEL_NAME,
    NORMALIZE_EMBEDDINGS,
    RAG_INDEX_DIR,
)
from app.rag.embedding_model import embed_texts

INDEX_TYPE = "IndexFlatIP"
SIMILARITY_METRIC = "cosine (inner product on L2-normalized vectors)"
NORMALIZATION_STRATEGY = "l2" if NORMALIZE_EMBEDDINGS else "none"

FAISS_INDEX_FILENAME = "document_chunks.faiss"
EMBEDDINGS_FILENAME = "embeddings.npy"
METADATA_FILENAME = "metadata.json"


@dataclass(frozen=True)
class IndexBuildSummary:
    total_chunks: int
    excluded_count: int
    included_count: int
    flagged_count: int
    vector_count: int
    mapping_count: int
    embedding_model: str
    embedding_dim: int
    normalization: str
    similarity_metric: str
    index_type: str
    source_csv_sha256: str
    skipped_rebuild: bool


def _sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def _row_to_mapping_entry(vector_index: int, row: pd.Series) -> dict:
    return {
        "vector_index": vector_index,
        "chunk_id": row["chunk_id"],
        "document_id": row["document_id"],
        "source_filename": row["source_filename"],
        "provenance_type": row["provenance_type"],
        "page_number": int(row["page_number"]),
        "section_heading": None if pd.isna(row["section_heading"]) else row["section_heading"],
        "extraction_method": row["extraction_method"],
        "extraction_quality_flag": (
            None if pd.isna(row["extraction_quality_flag"]) else row["extraction_quality_flag"]
        ),
        "chunk_word_count": int(row["chunk_word_count"]),
        "text": row["chunk_text"],
    }


def _existing_metadata_is_current(output_dir: Path, source_csv_sha256: str) -> dict | None:
    metadata_path = output_dir / METADATA_FILENAME
    faiss_path = output_dir / FAISS_INDEX_FILENAME
    embeddings_path = output_dir / EMBEDDINGS_FILENAME
    if not (metadata_path.exists() and faiss_path.exists() and embeddings_path.exists()):
        return None
    try:
        existing = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if (
        existing.get("source_csv_sha256") == source_csv_sha256
        and existing.get("embedding_model") == EMBEDDING_MODEL_NAME
        and existing.get("embedding_dim") == EMBEDDING_DIM
        and existing.get("index_type") == INDEX_TYPE
    ):
        return existing
    return None


def build_index(
    csv_path: Path = DOCUMENT_CHUNKS_CSV_PATH,
    output_dir: Path = RAG_INDEX_DIR,
    force: bool = False,
) -> IndexBuildSummary:
    """Builds (or, if `force=False` and nothing relevant changed, reuses) the
    FAISS index + embeddings + vector-to-chunk mapping for `csv_path`.

    Validates before returning: vector_count == mapping_count ==
    included_count, no duplicate chunk_ids, no orphan mapping entries.
    """
    import faiss

    source_csv_sha256 = _sha256_of_file(csv_path)

    if not force:
        existing = _existing_metadata_is_current(output_dir, source_csv_sha256)
        if existing is not None:
            return IndexBuildSummary(
                total_chunks=existing["total_chunks"],
                excluded_count=existing["excluded_count"],
                included_count=existing["included_count"],
                flagged_count=existing["flagged_count"],
                vector_count=len(existing["mapping"]),
                mapping_count=len(existing["mapping"]),
                embedding_model=existing["embedding_model"],
                embedding_dim=existing["embedding_dim"],
                normalization=existing["normalization"],
                similarity_metric=existing["similarity_metric"],
                index_type=existing["index_type"],
                source_csv_sha256=source_csv_sha256,
                skipped_rebuild=True,
            )

    result: ChunkFilterResult = load_and_filter_chunks(csv_path)
    included = result.included

    chunk_ids = included["chunk_id"].tolist()
    if len(chunk_ids) != len(set(chunk_ids)):
        dupes = included["chunk_id"][included["chunk_id"].duplicated()].tolist()
        raise ValueError(f"Duplicate chunk_id(s) found in {csv_path}: {dupes}")

    embeddings = embed_texts(included["chunk_text"].tolist())
    if embeddings.shape[0] != len(included):
        raise RuntimeError(
            f"Embedding count ({embeddings.shape[0]}) does not match included chunk "
            f"count ({len(included)})."
        )
    if embeddings.shape[1] != EMBEDDING_DIM:
        raise RuntimeError(f"Embedding dimension {embeddings.shape[1]} != expected {EMBEDDING_DIM}.")

    index = faiss.IndexFlatIP(EMBEDDING_DIM)
    index.add(embeddings)
    if index.ntotal != len(included):
        raise RuntimeError(f"FAISS vector count ({index.ntotal}) != included chunk count ({len(included)}).")

    mapping = [_row_to_mapping_entry(i, row) for i, (_, row) in enumerate(included.iterrows())]

    output_dir.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(output_dir / FAISS_INDEX_FILENAME))
    np.save(output_dir / EMBEDDINGS_FILENAME, embeddings)

    metadata = {
        "embedding_model": EMBEDDING_MODEL_NAME,
        "embedding_dim": EMBEDDING_DIM,
        "normalization": NORMALIZATION_STRATEGY,
        "similarity_metric": SIMILARITY_METRIC,
        "index_type": INDEX_TYPE,
        "source_csv_path": str(csv_path),
        "source_csv_sha256": source_csv_sha256,
        "total_chunks": result.total_chunks,
        "excluded_count": result.excluded_count,
        "included_count": result.included_count,
        "flagged_count": result.flagged_count,
        "mapping": mapping,
    }
    (output_dir / METADATA_FILENAME).write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")

    return IndexBuildSummary(
        total_chunks=result.total_chunks,
        excluded_count=result.excluded_count,
        included_count=result.included_count,
        flagged_count=result.flagged_count,
        vector_count=index.ntotal,
        mapping_count=len(mapping),
        embedding_model=EMBEDDING_MODEL_NAME,
        embedding_dim=EMBEDDING_DIM,
        normalization=NORMALIZATION_STRATEGY,
        similarity_metric=SIMILARITY_METRIC,
        index_type=INDEX_TYPE,
        source_csv_sha256=source_csv_sha256,
        skipped_rebuild=False,
    )


def summary_as_dict(summary: IndexBuildSummary) -> dict:
    return asdict(summary)
