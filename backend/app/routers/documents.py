"""Phase 8 document retrieval endpoint: GET /documents/search?q=<query>&top_k=5.

Citation-grounded, extractive-by-default: results and the answer are built
only from retrieved chunk text (see app/rag/answer.py). No LLM is involved
by default -- this endpoint always works with app/rag's extractive mode.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.contradiction.detector import get_detection_summary
from app.rag.answer import build_extractive_answer
from app.rag.retrieval import InvalidQueryError, get_retrieval_service
from app.schemas.contradictions import ContradictionFlagOut, ContradictionReportResponse
from app.schemas.documents import DocumentSearchResponse, RetrievalResultOut

router = APIRouter(prefix="/documents", tags=["documents"])

MAX_TOP_K = 20


@router.get("/search", response_model=DocumentSearchResponse)
def search_documents(
    q: str = Query(..., min_length=1, description="Natural-language query."),
    top_k: int = Query(5, ge=1, le=MAX_TOP_K),
) -> DocumentSearchResponse:
    service = get_retrieval_service()
    try:
        response = service.retrieve(q, top_k=top_k)
    except InvalidQueryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    answer = build_extractive_answer(response)
    results = [
        RetrievalResultOut(
            rank=r.rank,
            similarity_score=r.similarity_score,
            chunk_id=r.chunk_id,
            document_id=r.document_id,
            page_number=r.page_number,
            section_heading=r.section_heading,
            extraction_method=r.extraction_method,
            quality_flag=r.quality_flag,
            source_filename=r.source_filename,
            citation=r.citation(),
            text=r.text,
        )
        for r in response.results
    ]

    return DocumentSearchResponse(
        query=response.query,
        top_k=response.top_k,
        threshold=response.threshold,
        not_found=response.not_found,
        results=results,
        answer=answer,
    )


@router.get("/inconsistencies", response_model=ContradictionReportResponse)
def get_inconsistencies() -> ContradictionReportResponse:
    """Phase 9: hybrid contradiction/inconsistency detector results over the
    real document corpus. Reuses the Phase 8 FAISS/embedding artifacts for
    topic pairing (see app/contradiction/). Every flag is a hedged
    "potential inconsistency requiring verification" -- never a claim that
    either source is false or wrong. A zero-flag result is a valid,
    explicit response, not an error."""
    summary = get_detection_summary()
    return ContradictionReportResponse(
        total_chunks_considered=summary.total_chunks_considered,
        total_claims_extracted=summary.total_claims_extracted,
        claim_type_counts=summary.claim_type_counts,
        candidate_chunk_pairs=summary.candidate_chunk_pairs,
        comparable_claim_pairs_evaluated=summary.comparable_claim_pairs_evaluated,
        contextual_differences_excluded=summary.contextual_differences_excluded,
        flagged_count=summary.flagged_count,
        flags=[
            ContradictionFlagOut(
                flag_id=f.flag_id,
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
            for f in summary.flags
        ],
    )
