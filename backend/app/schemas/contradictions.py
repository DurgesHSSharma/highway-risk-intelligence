from __future__ import annotations

from pydantic import BaseModel

CONTRADICTION_DISCLAIMER = (
    "This is a heuristic verification-assistance tool, NOT a fact-checker. Every flagged "
    "pair is a potential inconsistency requiring human verification, not a confirmed error "
    "in either source. See docs/CONTRADICTION_DETECTION.md."
)


class ContradictionFlagOut(BaseModel):
    flag_id: str
    document_a: str
    page_a: int
    chunk_a: str
    raw_claim_a: str
    normalized_value_a: float
    document_b: str
    page_b: int
    chunk_b: str
    raw_claim_b: str
    normalized_value_b: float
    claim_type: str
    difference: float | None
    similarity_score: float
    tolerance_info: str
    context_info: str
    confidence: str | None
    description: str


class ContradictionReportResponse(BaseModel):
    total_chunks_considered: int
    total_claims_extracted: int
    claim_type_counts: dict[str, int]
    candidate_chunk_pairs: int
    comparable_claim_pairs_evaluated: int
    contextual_differences_excluded: int
    flagged_count: int
    flags: list[ContradictionFlagOut]
    disclaimer: str = CONTRADICTION_DISCLAIMER
