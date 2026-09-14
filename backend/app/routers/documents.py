"""Phase 8 document retrieval endpoint: GET /documents/search?q=<query>&top_k=5.

Citation-grounded, extractive-by-default: results and the answer are built
only from retrieved chunk text (see app/rag/answer.py). No LLM is involved
by default -- this endpoint always works with app/rag's extractive mode.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.rag.answer import build_extractive_answer
from app.rag.retrieval import InvalidQueryError, get_retrieval_service
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
