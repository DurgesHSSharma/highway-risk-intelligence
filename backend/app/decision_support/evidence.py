"""Phase 11 documentary-evidence gathering: runs each evidence query through
the existing Phase 8 `RetrievalService` (already loaded once at startup --
never rebuilt here) and reuses `app.rag.answer.build_extractive_answer` for
the citation-grounded extractive answer text. No new retrieval, embedding,
or answering logic.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.decision_support.shap_explainer import TaskRiskDrivers, driver_identity
from app.decision_support.topic_mapping import topic_for_raw_predictor_column
from app.rag.answer import build_extractive_answer
from app.rag.retrieval import RetrievalResult, RetrievalService

# Fallback only: used for a TERMINAL snapshot, where no live SHAP driver
# exists to derive queries from (prediction/SHAP are skipped entirely --
# see app.decision_support.synthesizer). Never used for a non-terminal
# snapshot, which always derives queries from that snapshot's own live SHAP
# drivers via `generate_evidence_queries_from_drivers` below.
DEFAULT_EVIDENCE_QUERIES: tuple[str, ...] = ("project delay", "cost overrun")

MAX_EVIDENCE_QUERIES = 5
DEFAULT_TOP_K = 3
MAX_SHAP_DERIVED_QUERIES = 2


@dataclass(frozen=True)
class EvidenceQueryResult:
    query: str
    not_found: bool
    answer: str
    results: list[RetrievalResult]


def gather_evidence(
    service: RetrievalService, queries: list[str] | None
) -> list[EvidenceQueryResult]:
    """Runs Phase 8 retrieval for each query (defaulting to
    `DEFAULT_EVIDENCE_QUERIES` when the caller supplies none) and returns one
    `EvidenceQueryResult` per query, preserving every retrieved chunk's
    provenance (document_id/page_number/chunk_id/citation)."""
    effective_queries = list(queries) if queries else list(DEFAULT_EVIDENCE_QUERIES)
    effective_queries = effective_queries[:MAX_EVIDENCE_QUERIES]

    out: list[EvidenceQueryResult] = []
    for query in effective_queries:
        response = service.retrieve(query, top_k=DEFAULT_TOP_K)
        answer = build_extractive_answer(response)
        out.append(
            EvidenceQueryResult(
                query=response.query,
                not_found=response.not_found,
                answer=answer,
                results=response.results,
            )
        )
    return out


def generate_evidence_queries_from_drivers(risk_drivers: list[TaskRiskDrivers]) -> list[str]:
    """Generates 1-2 RAG evidence queries from the union of each task's LIVE
    top-1 SHAP driver for this specific snapshot, deduped by raw predictor
    -column identity and mapped through
    app.decision_support.topic_mapping -- replaces the earlier fixed
    default query pair for non-terminal snapshots (see repair brief
    section G: "Generate evidence queries from the TOP 1-2 LIVE SHAP
    drivers")."""
    seen: list[str] = []
    for drivers in risk_drivers:
        if not drivers.top_drivers:
            continue
        top = drivers.top_drivers[0]
        identity = driver_identity(top.feature, top.raw_feature)
        if identity not in seen:
            seen.append(identity)
        if len(seen) >= MAX_SHAP_DERIVED_QUERIES:
            break
    return [topic_for_raw_predictor_column(f) for f in seen]


def evidence_chunk_ids(evidence: list[EvidenceQueryResult]) -> set[str]:
    ids: set[str] = set()
    for item in evidence:
        for r in item.results:
            ids.add(r.chunk_id)
    return ids


def any_evidence_found(evidence: list[EvidenceQueryResult]) -> bool:
    return any(not item.not_found for item in evidence)
