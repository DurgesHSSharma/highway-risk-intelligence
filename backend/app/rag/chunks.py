"""Loads the Phase 7 chunk dataset and applies the Phase 8 pre-embedding
filter: exclude only chunks with no meaningful text at all. Everything else
-- including `suspicious_text` / `low_ocr_quality` flagged chunks -- is kept
and remains searchable, per the Phase 8 brief.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from app.rag.config import DOCUMENT_CHUNKS_CSV_PATH, MIN_CHUNK_TEXT_LENGTH

REQUIRED_COLUMNS = [
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


@dataclass(frozen=True)
class ChunkFilterResult:
    included: pd.DataFrame
    excluded: pd.DataFrame
    total_chunks: int
    included_count: int
    excluded_count: int
    flagged_count: int


def _is_meaningless(text: object) -> bool:
    if pd.isna(text):
        return True
    stripped = str(text).strip()
    return len(stripped) < MIN_CHUNK_TEXT_LENGTH


def load_and_filter_chunks(csv_path=DOCUMENT_CHUNKS_CSV_PATH) -> ChunkFilterResult:
    """Reads `document_chunks.csv` and splits it into included/excluded
    chunks. Exclusion is based ONLY on having no meaningful text (empty or
    whitespace-only) -- never on the `extraction_quality_flag` column, which
    is preserved and carried into retrieval results instead of being used to
    drop rows."""
    if not csv_path.exists():
        raise FileNotFoundError(
            f"Phase 7 chunk dataset not found at {csv_path}. Run "
            "scripts/ingest_documents.py first (see docs/DOCUMENT_INGESTION.md)."
        )

    df = pd.read_csv(csv_path)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"{csv_path} is missing required columns: {missing}")

    is_meaningless = df["chunk_text"].apply(_is_meaningless)
    included = df.loc[~is_meaningless].reset_index(drop=True)
    excluded = df.loc[is_meaningless].reset_index(drop=True)
    flagged = included["extraction_quality_flag"].notna().sum()

    return ChunkFilterResult(
        included=included,
        excluded=excluded,
        total_chunks=len(df),
        included_count=len(included),
        excluded_count=len(excluded),
        flagged_count=int(flagged),
    )
