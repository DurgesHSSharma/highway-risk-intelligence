from __future__ import annotations

from pydantic import BaseModel

DOCUMENT_CORPUS_DISCLAIMER = (
    "This corpus contains only 4 real public documents (~861 usable chunks): a CAG "
    "performance audit, an NHAI annual report, a MoRTH annual report, and a PRS "
    "budget analysis (see data/documents/metadata.csv). Retrieval quality should NOT "
    "be generalized to a large national infrastructure document corpus. A "
    "'not found' result for a question outside these 4 documents' scope is expected "
    "behavior, not a bug -- see docs/RAG_SYSTEM.md."
)


class RetrievalResultOut(BaseModel):
    rank: int
    similarity_score: float
    chunk_id: str
    document_id: str
    page_number: int
    section_heading: str | None
    extraction_method: str
    quality_flag: str | None
    source_filename: str
    citation: str
    text: str


class DocumentSearchResponse(BaseModel):
    query: str
    mode: str = "extractive"
    top_k: int
    threshold: float
    not_found: bool
    results: list[RetrievalResultOut]
    answer: str
    corpus_disclaimer: str = DOCUMENT_CORPUS_DISCLAIMER
