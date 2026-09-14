"""Phase 9 hybrid contradiction/inconsistency detector: orchestrates
extraction (extraction.py) + Phase 8 embedding reuse (pairing.py) +
context-aware tolerance comparison (comparison.py) into one deterministic
end-to-end pass over the real document corpus.

This is a heuristic verification-assistance system, NOT a fact-checker --
every flagged record is described only as a "potential inconsistency
requiring verification", never as a confirmed error in either source. See
docs/CONTRADICTION_DETECTION.md.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass

import numpy as np

from app.contradiction.comparison import compare_claims
from app.contradiction.config import PROHIBITED_ABSOLUTE_PHRASES
from app.contradiction.extraction import Claim, extract_claims_from_chunks
from app.contradiction.pairing import find_candidate_chunk_pairs
from app.rag.chunks import load_and_filter_chunks
from app.rag.config import EMBEDDINGS_PATH, METADATA_PATH


@dataclass(frozen=True)
class ContradictionFlag:
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


@dataclass(frozen=True)
class DetectionSummary:
    total_chunks_considered: int
    total_claims_extracted: int
    claim_type_counts: dict[str, int]
    candidate_chunk_pairs: int
    comparable_claim_pairs_evaluated: int
    contextual_differences_excluded: int
    flagged_count: int
    flags: list[ContradictionFlag]


_TOLERANCE_TEXT = {
    "percentage": "flagged if |difference| > 1.0 percentage point",
    "currency": "flagged if relative difference > 5.0% (normalized to crore)",
    "count": "flagged if relative difference > 5.0%",
    "date": "flagged if the normalized calendar dates differ at all",
}


def _build_description(document_a: str, page_a: int, document_b: str, page_b: int, claim_type: str) -> str:
    desc = (
        f"{document_a} (p. {page_a}) and {document_b} (p. {page_b}) appear to report this "
        f"{claim_type} figure differently -- a potential inconsistency requiring verification, "
        "not a definitive finding about either source."
    )
    lowered = desc.lower()
    for phrase in PROHIBITED_ABSOLUTE_PHRASES:
        if phrase in lowered:
            raise RuntimeError(f"Generated flag description contains prohibited absolute language: {phrase!r}")
    return desc


def _dates_by_chunk(claims: list[Claim]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = defaultdict(set)
    for c in claims:
        if c.claim_type == "date":
            out[c.chunk_id].add(str(c.normalized_value))
    return out


def run_detection(chunks_csv_path=None) -> DetectionSummary:
    """Full end-to-end Phase 9 pass over the real committed corpus:
    Phase 7 chunk dataset -> Phase 9 claim extraction -> Phase 8 embedding
    reuse for topic pairing -> context-aware tolerance comparison ->
    deterministically-sorted flags. Never recomputes embeddings; reads the
    already-built rag_index/ artifacts directly."""
    from app.rag.config import DOCUMENT_CHUNKS_CSV_PATH

    csv_path = chunks_csv_path or DOCUMENT_CHUNKS_CSV_PATH
    filter_result = load_and_filter_chunks(csv_path)
    included = filter_result.included

    claims = extract_claims_from_chunks(included)
    claims_by_chunk: dict[str, list[Claim]] = defaultdict(list)
    for c in claims:
        claims_by_chunk[c.chunk_id].append(c)
    dates_by_chunk = _dates_by_chunk(claims)

    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    mapping = metadata["mapping"]
    embeddings = np.load(EMBEDDINGS_PATH)

    candidate_pairs = find_candidate_chunk_pairs(mapping, embeddings)

    comparable_evaluated = 0
    contextual_excluded = 0
    flags: list[ContradictionFlag] = []

    for pair in candidate_pairs:
        claims_a = claims_by_chunk.get(pair.chunk_id_a, [])
        claims_b = claims_by_chunk.get(pair.chunk_id_b, [])
        if not claims_a or not claims_b:
            continue

        dates_a = dates_by_chunk.get(pair.chunk_id_a, set())
        dates_b = dates_by_chunk.get(pair.chunk_id_b, set())

        for claim_a in claims_a:
            for claim_b in claims_b:
                outcome = compare_claims(claim_a, claim_b, dates_a, dates_b)
                if outcome is None:
                    continue
                comparable_evaluated += 1
                if outcome.status == "contextual_difference":
                    contextual_excluded += 1
                    continue
                if outcome.status != "flagged":
                    continue

                description = _build_description(
                    pair.document_id_a, pair.page_a, pair.document_id_b, pair.page_b, claim_a.claim_type
                )
                flags.append(
                    ContradictionFlag(
                        flag_id="",  # assigned after deterministic sort, below
                        document_a=pair.document_id_a,
                        page_a=pair.page_a,
                        chunk_a=claim_a.chunk_id,
                        raw_claim_a=claim_a.raw_text,
                        normalized_value_a=float(claim_a.normalized_value),
                        document_b=pair.document_id_b,
                        page_b=pair.page_b,
                        chunk_b=claim_b.chunk_id,
                        raw_claim_b=claim_b.raw_text,
                        normalized_value_b=float(claim_b.normalized_value),
                        claim_type=claim_a.claim_type,
                        difference=outcome.difference,
                        similarity_score=pair.similarity,
                        tolerance_info=_TOLERANCE_TEXT[claim_a.claim_type],
                        context_info=f"claim-context word overlap (Jaccard)={outcome.context_jaccard:.3f}",
                        confidence=outcome.confidence,
                        description=description,
                    )
                )

    flags.sort(
        key=lambda f: (f.document_a, f.chunk_a, f.document_b, f.chunk_b, f.claim_type, f.raw_claim_a, f.raw_claim_b)
    )
    flags = [
        ContradictionFlag(
            flag_id=f"FLAG-{i:04d}",
            document_a=f.document_a,
            page_a=f.page_a,
            chunk_a=f.chunk_a,
            raw_claim_a=f.raw_claim_a,
            normalized_value_a=f.normalized_value_a,
            document_b=f.document_b,
            page_b=f.page_b,
            chunk_b=f.chunk_b,
            raw_claim_b=f.raw_claim_b,
            normalized_value_b=f.normalized_value_b,
            claim_type=f.claim_type,
            difference=f.difference,
            similarity_score=f.similarity_score,
            tolerance_info=f.tolerance_info,
            context_info=f.context_info,
            confidence=f.confidence,
            description=f.description,
        )
        for i, f in enumerate(flags, start=1)
    ]

    claim_type_counts: dict[str, int] = defaultdict(int)
    for c in claims:
        claim_type_counts[c.claim_type] += 1

    return DetectionSummary(
        total_chunks_considered=len(included),
        total_claims_extracted=len(claims),
        claim_type_counts=dict(sorted(claim_type_counts.items())),
        candidate_chunk_pairs=len(candidate_pairs),
        comparable_claim_pairs_evaluated=comparable_evaluated,
        contextual_differences_excluded=contextual_excluded,
        flagged_count=len(flags),
        flags=flags,
    )


_SUMMARY: DetectionSummary | None = None


def get_detection_summary() -> DetectionSummary:
    """Module-level singleton -- the detector is deterministic and cheap
    (pure regex + numpy over already-loaded Phase 8 artifacts), but is
    still computed once per process and reused, mirroring the
    app/rag/retrieval.py::get_retrieval_service() convention."""
    global _SUMMARY
    if _SUMMARY is None:
        _SUMMARY = run_detection()
    return _SUMMARY


def reset_detection_summary_for_tests() -> None:
    global _SUMMARY
    _SUMMARY = None
