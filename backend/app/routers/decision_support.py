"""Phase 11 (REPAIRED) decision-support endpoint:
GET /projects/{project_id}/risk-summary?reporting_month=YYYY-MM.

No request body. Synthesizes existing Phase 6 (ML predictions), LIVE
per-instance Phase 5-style SHAP (computed here against the exact Phase 6
serving model per task -- see app.decision_support.shap_explainer), Phase 8
(RAG evidence), Phase 9 (potential inconsistencies), and Phase 10
(illustrative what-if scenario) output into one evidence-grounded, hedged
response. See app.decision_support.synthesizer for the pipeline and
docs/DECISION_SUPPORT.md for the full design and mandatory disclaimers.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.decision_support.synthesizer import (
    ProjectNotFoundError,
    SnapshotNotFoundError,
    run_risk_summary,
)
from app.ml.features import FeatureConstructionError
from app.schemas.contradictions import ContradictionFlagOut
from app.schemas.decision_support import (
    DisclaimersOut,
    DriverFeatureOut,
    EvidenceQueryResultOut,
    ProjectSnapshotInfoOut,
    RiskSummaryResponse,
    ScenarioOut,
    TaskRiskDriversOut,
)
from app.schemas.documents import RetrievalResultOut
from app.schemas.simulation import PredictionsBundle

router = APIRouter(prefix="/projects", tags=["decision-support"])


@router.get("/{project_id}/risk-summary", response_model=RiskSummaryResponse)
def risk_summary(
    project_id: str,
    reporting_month: str = Query(..., description="YYYY-MM"),
    db: Session = Depends(get_db),
) -> RiskSummaryResponse:
    try:
        result = run_risk_summary(db, project_id, reporting_month)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SnapshotNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FeatureConstructionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    project_out = ProjectSnapshotInfoOut(
        project_id=result.project.project_id,
        project_name=result.project.project_name,
        state=result.project.state,
        project_type=result.project.project_type,
        contractor=result.project.contractor,
        highway_number=result.project.highway_number,
        reporting_month=result.project.reporting_month,
        months_since_start=result.project.months_since_start,
        project_status=result.project.project_status,
        is_terminal_snapshot=result.project.is_terminal_snapshot,
    )

    risk_drivers_out = [
        TaskRiskDriversOut(
            task_key=d.task_key,
            label=d.label,
            model_used=d.model_used,
            explainer_type=d.explainer_type,
            shap_output_semantics=d.shap_output_semantics,
            top_drivers=[
                DriverFeatureOut(
                    rank=f.rank, feature=f.feature, shap_value=f.shap_value,
                    direction=f.direction, explanation=f.explanation,
                )
                for f in d.top_drivers
            ],
        )
        for d in result.risk_drivers
    ]

    documentary_evidence_out = [
        EvidenceQueryResultOut(
            query=item.query,
            not_found=item.not_found,
            answer=item.answer,
            results=[
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
                for r in item.results
            ],
        )
        for item in result.evidence
    ]

    potential_inconsistencies_out = [
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
        for f in result.inconsistencies
    ]

    scenario_out = None
    if result.scenario is not None:
        scenario_out = ScenarioOut(
            field=result.scenario.field,
            reference_value=result.scenario.reference_value,
            label=result.scenario.label,
            baseline=PredictionsBundle(**result.scenario.baseline_predictions),
            simulated=PredictionsBundle(**result.scenario.simulated_predictions),
        )

    return RiskSummaryResponse(
        project=project_out,
        prediction_status=result.prediction_status,
        predictions=PredictionsBundle(**result.predictions),
        risk_summary=result.risk_summary,
        risk_drivers=risk_drivers_out,
        shap_skipped_reason=result.shap_skipped_reason,
        documentary_evidence=documentary_evidence_out,
        potential_inconsistencies=potential_inconsistencies_out,
        scenario=scenario_out,
        scenario_skipped_reason=result.scenario_skipped_reason,
        recommended_reviews=result.recommendations,
        evidence_strength=result.evidence_strength,
        evidence_strength_basis=result.evidence_strength_basis,
        disclaimers=DisclaimersOut(),
    )
