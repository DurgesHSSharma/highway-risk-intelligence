"""Phase 15 Decision Intelligence response schema for
GET /projects/{project_id}/decision-intelligence?reporting_month=YYYY-MM.

Reuses Phase 11's decision-support schema types (`ProjectSnapshotInfoOut`,
`RiskSummaryOut`, `TaskRiskDriversOut`, `EvidenceQueryResultOut`,
`ContradictionFlagOut`, `ScenarioOut`, `DisclaimersOut`) and Phase 14's
portfolio-analytics schema types (`HistoricalSegmentStatOut`,
`PredictedSegmentStatOut`) directly, instead of redefining their fields --
see docs/DECISION_INTELLIGENCE.md for the full response contract.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.schemas.decision_support import (
    ContradictionFlagOut,
    DisclaimersOut,
    EvidenceQueryResultOut,
    ProjectSnapshotInfoOut,
    RiskSummaryOut,
    ScenarioOut,
    TaskRiskDriversOut,
)
from app.schemas.portfolio_analytics import HistoricalSegmentStatOut, PredictedSegmentStatOut
from app.schemas.simulation import PredictionsBundle


class PeerContextEntryOut(BaseModel):
    dimension: Literal["state", "project_type", "contractor"]
    status: Literal["ok", "unavailable"]
    reason: str | None
    value: str | None
    min_sample_threshold: int | None
    small_sample: bool | None
    historical: HistoricalSegmentStatOut | None
    predicted: PredictedSegmentStatOut | None


class RiskPositioningOut(BaseModel):
    status: Literal["ok", "cache_unavailable", "project_not_in_cache"]
    message: str | None
    cache_computed_at: str | None
    cohort_size: int | None
    composite_risk_score: float | None
    risk_level: str | None
    percentile: float | None
    delay_risk: float | None
    cost_risk: float | None
    risk_level_thresholds: dict[str, float] | None
    percentile_definition: str
    portfolio_relative_disclaimer: str
    current_risk_basis_note: str


class TaskDriverAlignmentOut(BaseModel):
    task_key: str
    matches_serving_model: bool
    live_top_driver: str | None
    live_top_driver_identity: str | None
    portfolio_top_driver: str | None
    portfolio_top_driver_identity: str | None
    agreement: bool | None
    comparable: bool
    not_comparable_note: str | None


class DecisionIntelligenceRecommendationOut(BaseModel):
    text: str
    basis_type: Literal[
        "model_driver", "documentary_evidence", "potential_inconsistency", "scenario", "portfolio_context"
    ]
    basis_detail: str


class DecisionIntelligenceResponse(BaseModel):
    # --- Composed unchanged from Phase 11's run_risk_summary (see
    # app.decision_support.synthesizer, called once as a black box) ---
    project: ProjectSnapshotInfoOut
    prediction_status: Literal["actual_outcome", "model_prediction"]
    predictions: PredictionsBundle
    risk_summary: RiskSummaryOut
    risk_drivers: list[TaskRiskDriversOut]
    shap_skipped_reason: str | None
    documentary_evidence: list[EvidenceQueryResultOut]
    potential_inconsistencies: list[ContradictionFlagOut]
    scenario: ScenarioOut | None
    scenario_skipped_reason: str | None
    evidence_strength: Literal["high evidence support", "moderate evidence support", "limited evidence support"]
    evidence_strength_basis: str

    # --- New Phase 15 portfolio-context composition ---
    risk_positioning: RiskPositioningOut
    peer_context: dict[str, PeerContextEntryOut]
    driver_alignment: list[TaskDriverAlignmentOut]

    # --- Phase 11's 4 recommendation families + Phase 15's 5th family,
    # merged and capped at app.decision_support.recommendations.MAX_TOTAL_RECOMMENDATIONS ---
    recommended_reviews: list[DecisionIntelligenceRecommendationOut]

    disclaimers: DisclaimersOut = DisclaimersOut()
