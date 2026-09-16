"""Phase 15 Decision Intelligence endpoint:
GET /projects/{project_id}/decision-intelligence?reporting_month=YYYY-MM.

No request body. Composes Phase 11's existing risk-summary pipeline
(prediction, live SHAP, RAG evidence, potential inconsistencies,
illustrative scenario -- called once as a black box via
app.decision_support.synthesizer.run_risk_summary) with Phase 14 portfolio
context (composite risk score / percentile / portfolio-relative risk band,
state/project_type/contractor peer context) and a live-vs-portfolio SHAP
driver-alignment comparison, then merges Phase 11's four recommendation
families with a new Phase 15 portfolio_context family. See
app.decision_intelligence.synthesizer for the pipeline and
docs/DECISION_INTELLIGENCE.md for the full design and response contract.

This endpoint NEVER triggers Phase 14 batch scoring
(app.analytics.batch_scoring.run_batch_scoring) -- it only reads the
existing portfolio_prediction_cache table, exactly like the Phase 14
/analytics/* endpoints already do.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.decision_intelligence.driver_alignment import NOT_COMPARABLE_NOTE
from app.decision_intelligence.portfolio_context import (
    CURRENT_RISK_BASIS_NOTE,
    PERCENTILE_DEFINITION,
    PORTFOLIO_RELATIVE_DISCLAIMER,
)
from app.decision_intelligence.synthesizer import (
    ProjectNotFoundError,
    SnapshotNotFoundError,
    run_decision_intelligence,
)
from app.ml.features import FeatureConstructionError
from app.schemas.contradictions import ContradictionFlagOut
from app.schemas.decision_intelligence import (
    DecisionIntelligenceResponse,
    PeerContextEntryOut,
    RiskPositioningOut,
    TaskDriverAlignmentOut,
)
from app.validation import MONTH_DESCRIPTION, MONTH_PATTERN
from app.schemas.decision_support import (
    DisclaimersOut,
    DriverFeatureOut,
    EvidenceQueryResultOut,
    ProjectSnapshotInfoOut,
    ScenarioOut,
    TaskRiskDriversOut,
)
from app.schemas.documents import RetrievalResultOut
from app.schemas.portfolio_analytics import HistoricalSegmentStatOut, PredictedSegmentStatOut
from app.schemas.simulation import PredictionsBundle

router = APIRouter(prefix="/projects", tags=["decision-intelligence"])


def _project_out(result) -> ProjectSnapshotInfoOut:
    p = result.risk_summary.project
    return ProjectSnapshotInfoOut(
        project_id=p.project_id,
        project_name=p.project_name,
        state=p.state,
        project_type=p.project_type,
        contractor=p.contractor,
        highway_number=p.highway_number,
        reporting_month=p.reporting_month,
        months_since_start=p.months_since_start,
        project_status=p.project_status,
        is_terminal_snapshot=p.is_terminal_snapshot,
    )


def _risk_drivers_out(result) -> list[TaskRiskDriversOut]:
    return [
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
        for d in result.risk_summary.risk_drivers
    ]


def _documentary_evidence_out(result) -> list[EvidenceQueryResultOut]:
    return [
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
        for item in result.risk_summary.evidence
    ]


def _potential_inconsistencies_out(result) -> list[ContradictionFlagOut]:
    return [
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
        for f in result.risk_summary.inconsistencies
    ]


def _scenario_out(result) -> ScenarioOut | None:
    scenario = result.risk_summary.scenario
    if scenario is None:
        return None
    return ScenarioOut(
        field=scenario.field,
        reference_value=scenario.reference_value,
        label=scenario.label,
        baseline=PredictionsBundle(**scenario.baseline_predictions),
        simulated=PredictionsBundle(**scenario.simulated_predictions),
    )


def _risk_positioning_out(result) -> RiskPositioningOut:
    rp = result.risk_positioning
    return RiskPositioningOut(
        status=rp.status,
        message=rp.message,
        cache_computed_at=rp.cache_computed_at,
        cohort_size=rp.cohort_size,
        composite_risk_score=rp.composite_risk_score,
        risk_level=rp.risk_level,
        percentile=rp.percentile,
        delay_risk=rp.delay_risk,
        cost_risk=rp.cost_risk,
        risk_level_thresholds=rp.risk_level_thresholds,
        percentile_definition=PERCENTILE_DEFINITION,
        portfolio_relative_disclaimer=PORTFOLIO_RELATIVE_DISCLAIMER,
        current_risk_basis_note=CURRENT_RISK_BASIS_NOTE,
    )


def _peer_context_out(result) -> dict[str, PeerContextEntryOut]:
    out: dict[str, PeerContextEntryOut] = {}
    for dimension, entry in result.peer_context.items():
        seg = entry.segment
        historical_out = (
            HistoricalSegmentStatOut(
                project_count=seg.historical.project_count,
                significant_delay_rate=seg.historical.significant_delay_rate,
                cost_overrun_rate=seg.historical.cost_overrun_rate,
                mean_final_delay_days=seg.historical.mean_final_delay_days,
                mean_final_cost_overrun_pct=seg.historical.mean_final_cost_overrun_pct,
            )
            if seg and seg.historical
            else None
        )
        predicted_out = (
            PredictedSegmentStatOut(
                scored_project_count=seg.predicted.scored_project_count,
                avg_significant_delay_probability=seg.predicted.avg_significant_delay_probability,
                avg_cost_overrun_probability=seg.predicted.avg_cost_overrun_probability,
                avg_final_delay_days_predicted=seg.predicted.avg_final_delay_days_predicted,
                avg_final_cost_overrun_pct_predicted=seg.predicted.avg_final_cost_overrun_pct_predicted,
                avg_composite_risk_score=seg.predicted.avg_composite_risk_score,
                risk_level_counts=seg.predicted.risk_level_counts,
            )
            if seg and seg.predicted
            else None
        )
        out[dimension] = PeerContextEntryOut(
            dimension=dimension,
            status=entry.status,
            reason=entry.reason,
            value=entry.value,
            min_sample_threshold=seg.min_sample_threshold if seg else None,
            small_sample=seg.small_sample if seg else None,
            historical=historical_out,
            predicted=predicted_out,
        )
    return out


def _driver_alignment_out(result) -> list[TaskDriverAlignmentOut]:
    return [
        TaskDriverAlignmentOut(
            task_key=a.task_key,
            matches_serving_model=a.matches_serving_model,
            live_top_driver=a.live_top_driver,
            live_top_driver_identity=a.live_top_driver_identity,
            portfolio_top_driver=a.portfolio_top_driver,
            portfolio_top_driver_identity=a.portfolio_top_driver_identity,
            agreement=a.agreement,
            comparable=a.comparable,
            not_comparable_note=None if a.comparable else NOT_COMPARABLE_NOTE,
        )
        for a in result.driver_alignment
    ]


@router.get("/{project_id}/decision-intelligence", response_model=DecisionIntelligenceResponse)
def decision_intelligence(
    project_id: str,
    reporting_month: str = Query(..., pattern=MONTH_PATTERN, description=MONTH_DESCRIPTION),
    db: Session = Depends(get_db),
) -> DecisionIntelligenceResponse:
    try:
        result = run_decision_intelligence(db, project_id, reporting_month)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SnapshotNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FeatureConstructionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    rs = result.risk_summary

    return DecisionIntelligenceResponse(
        project=_project_out(result),
        prediction_status=rs.prediction_status,
        predictions=PredictionsBundle(**rs.predictions),
        risk_summary=rs.risk_summary,
        risk_drivers=_risk_drivers_out(result),
        shap_skipped_reason=rs.shap_skipped_reason,
        documentary_evidence=_documentary_evidence_out(result),
        potential_inconsistencies=_potential_inconsistencies_out(result),
        scenario=_scenario_out(result),
        scenario_skipped_reason=rs.scenario_skipped_reason,
        evidence_strength=rs.evidence_strength,
        evidence_strength_basis=rs.evidence_strength_basis,
        risk_positioning=_risk_positioning_out(result),
        peer_context=_peer_context_out(result),
        driver_alignment=_driver_alignment_out(result),
        recommended_reviews=result.recommended_reviews,
        disclaimers=DisclaimersOut(),
    )
