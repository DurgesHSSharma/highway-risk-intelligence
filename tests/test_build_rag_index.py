"""Phase 8 RAG index-build tests, run at the repo root (mirrors the existing
tests/test_load_db.py convention): most tests use a small synthetic chunk
CSV in an isolated tmp_path so they never touch the real committed
rag_index/; a couple of tests assert the real, actual filtering counts on
the real Phase 7 corpus (data/processed/document_chunks.csv), per the Phase
8 brief's "report actual counts from the real dataset" requirement.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import scripts.build_rag_index  # noqa: F401  (adds backend/ to sys.path as a side effect)

from app.rag.chunks import load_and_filter_chunks  # noqa: E402
from app.rag.config import DOCUMENT_CHUNKS_CSV_PATH, EMBEDDING_DIM  # noqa: E402
from app.rag.index_builder import build_index  # noqa: E402

CHUNK_COLUMNS = [
    "chunk_id",
    "document_id",
    "source_filename",
    "provenance_type",
    "page_number",
    "section_heading",
    "extraction_method",
    "extraction_quality_flag",
    "chunk_index",
    "chunk_word_count",
    "chunk_text",
]


def _make_chunk_row(chunk_id, document_id, page_number, text, quality_flag=None, section=None):
    return {
        "chunk_id": chunk_id,
        "document_id": document_id,
        "source_filename": f"{document_id.lower()}.pdf",
        "provenance_type": "REAL PUBLIC DATA",
        "page_number": page_number,
        "section_heading": section,
        "extraction_method": "native_text",
        "extraction_quality_flag": quality_flag,
        "chunk_index": 0,
        "chunk_word_count": len(str(text).split()),
        "chunk_text": text,
    }


@pytest.fixture()
def small_chunk_csv(tmp_path: Path) -> Path:
    rows = [
        _make_chunk_row("DOC-X_p0001_c00", "DOC-X", 1, "Highway construction delayed due to land acquisition issues."),
        _make_chunk_row("DOC-X_p0002_c00", "DOC-X", 2, "The contractor requested a cost overrun review for the bridge segment."),
        _make_chunk_row("DOC-X_p0003_c00", "DOC-X", 3, "Environmental clearance was pending for six months in this stretch."),
        _make_chunk_row("DOC-X_p0004_c00", "DOC-X", 4, "", quality_flag="empty_native_text_placeholder"),
        _make_chunk_row("DOC-X_p0005_c00", "DOC-X", 5, "   ", quality_flag=None),
        _make_chunk_row("DOC-X_p0006_c00", "DOC-X", 6, "garbled Ok i F 8 Pe.", quality_flag="suspicious_text"),
        _make_chunk_row("DOC-X_p0007_c00", "DOC-X", 7, "CHAPTER 1", quality_flag="low_ocr_quality"),
    ]
    df = pd.DataFrame(rows, columns=CHUNK_COLUMNS)
    csv_path = tmp_path / "small_document_chunks.csv"
    df.to_csv(csv_path, index=False)
    return csv_path


def test_load_and_filter_chunks_excludes_only_empty_text(small_chunk_csv: Path):
    result = load_and_filter_chunks(small_chunk_csv)

    assert result.total_chunks == 7
    assert result.excluded_count == 2  # the "" row and the whitespace-only row
    assert result.included_count == 5
    # suspicious_text + low_ocr_quality rows are KEPT, not excluded.
    included_ids = set(result.included["chunk_id"])
    assert "DOC-X_p0006_c00" in included_ids
    assert "DOC-X_p0007_c00" in included_ids
    assert result.flagged_count == 2  # only the two still-included flagged rows


def test_load_and_filter_chunks_missing_csv_raises_clear_error(tmp_path: Path):
    missing = tmp_path / "does_not_exist.csv"
    with pytest.raises(FileNotFoundError):
        load_and_filter_chunks(missing)


def test_build_index_creates_valid_index(small_chunk_csv: Path, tmp_path: Path):
    output_dir = tmp_path / "index_out"
    summary = build_index(csv_path=small_chunk_csv, output_dir=output_dir, force=True)

    assert summary.included_count == 5
    assert summary.vector_count == 5
    assert summary.mapping_count == 5
    assert summary.embedding_dim == EMBEDDING_DIM
    assert (output_dir / "document_chunks.faiss").exists()
    assert (output_dir / "embeddings.npy").exists()
    assert (output_dir / "metadata.json").exists()

    embeddings = np.load(output_dir / "embeddings.npy")
    assert embeddings.shape == (5, EMBEDDING_DIM)


def test_build_index_raises_on_duplicate_chunk_ids(tmp_path: Path):
    rows = [
        _make_chunk_row("DUP_p0001_c00", "DUP", 1, "First duplicate chunk about highway delay."),
        _make_chunk_row("DUP_p0001_c00", "DUP", 1, "Second duplicate chunk, same chunk_id, different text."),
    ]
    df = pd.DataFrame(rows, columns=CHUNK_COLUMNS)
    csv_path = tmp_path / "dup_chunks.csv"
    df.to_csv(csv_path, index=False)

    with pytest.raises(ValueError, match="Duplicate chunk_id"):
        build_index(csv_path=csv_path, output_dir=tmp_path / "dup_out", force=True)


def test_mapping_entries_reference_real_included_chunks(small_chunk_csv: Path, tmp_path: Path):
    output_dir = tmp_path / "index_out"
    build_index(csv_path=small_chunk_csv, output_dir=output_dir, force=True)

    import json

    metadata = json.loads((output_dir / "metadata.json").read_text(encoding="utf-8"))
    mapping = metadata["mapping"]
    result = load_and_filter_chunks(small_chunk_csv)
    included_ids = set(result.included["chunk_id"])

    mapped_ids = [entry["chunk_id"] for entry in mapping]
    assert len(mapped_ids) == len(set(mapped_ids)), "duplicate chunk_id in mapping"
    assert set(mapped_ids) == included_ids, "mapping does not exactly match included chunks (orphan or missing entries)"


def test_build_index_skips_rebuild_when_unchanged(small_chunk_csv: Path, tmp_path: Path):
    output_dir = tmp_path / "index_out"
    first = build_index(csv_path=small_chunk_csv, output_dir=output_dir, force=True)
    assert first.skipped_rebuild is False

    second = build_index(csv_path=small_chunk_csv, output_dir=output_dir, force=False)
    assert second.skipped_rebuild is True
    assert second.included_count == first.included_count
    assert second.vector_count == first.vector_count


def test_build_index_force_rebuilds_even_when_unchanged(small_chunk_csv: Path, tmp_path: Path):
    output_dir = tmp_path / "index_out"
    build_index(csv_path=small_chunk_csv, output_dir=output_dir, force=True)
    second = build_index(csv_path=small_chunk_csv, output_dir=output_dir, force=True)
    assert second.skipped_rebuild is False


def test_index_build_is_deterministic_across_independent_runs(small_chunk_csv: Path, tmp_path: Path):
    dir1 = tmp_path / "out1"
    dir2 = tmp_path / "out2"
    build_index(csv_path=small_chunk_csv, output_dir=dir1, force=True)
    build_index(csv_path=small_chunk_csv, output_dir=dir2, force=True)

    emb1 = np.load(dir1 / "embeddings.npy")
    emb2 = np.load(dir2 / "embeddings.npy")
    assert np.array_equal(emb1, emb2), "embeddings differ across independent rebuilds of the same source CSV"

    faiss1 = (dir1 / "document_chunks.faiss").read_bytes()
    faiss2 = (dir2 / "document_chunks.faiss").read_bytes()
    assert faiss1 == faiss2, "FAISS index files are not byte-identical across independent rebuilds"

    meta1 = (dir1 / "metadata.json").read_text(encoding="utf-8")
    meta2 = (dir2 / "metadata.json").read_text(encoding="utf-8")
    assert meta1 == meta2, "metadata.json is not byte-identical across independent rebuilds"


# --- Real Phase 7 corpus: actual counts, not estimated ---


def test_real_corpus_chunk_filter_counts_match_actual_data():
    """Locks in the ACTUAL measured counts from the real Phase 7 chunk
    dataset (data/processed/document_chunks.csv) -- verified by direct
    inspection during Phase 8 planning, not assumed."""
    result = load_and_filter_chunks(DOCUMENT_CHUNKS_CSV_PATH)

    assert result.total_chunks == 861
    assert result.excluded_count == 0
    assert result.included_count == 861
    assert result.flagged_count == 10  # 5 suspicious_text + 5 low_ocr_quality
