"""Phase 11 (REPAIRED) decision-support response schema for
GET /projects/{project_id}/risk-summary?reporting_month=YYYY-MM.

Reuses existing Phase 6/8/9/10 schema types directly (`PredictionsBundle`,
`RetrievalResultOut`, `ContradictionFlagOut`) instead of redefining their
fields -- see docs/DECISION_SUPPORT.md for the full response contract and
rationale.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.schemas.contradictions import ContradictionFlagOut
from app.schemas.documents import RetrievalResultOut
from app.schemas.predictions import SYNTHETIC_DATA_DISCLAIMER_MODEL
from app.schemas.simulation import SIMULATION_DISCLAIMER, PredictionsBundle

SHAP_SKIPPED_TERMINAL_MESSAGE = (
    "Skipped: this snapshot is terminal (is_terminal_snapshot=true) and already records the "
    "project's known final outcome, so a live SHAP explanation of a forward-looking model "
    "prediction is not applicable -- see docs/DECISION_SUPPORT.md 'Terminal snapshot rule'."
)

SCENARIO_SKIPPED_TERMINAL_MESSAGE = (
    "Skipped: this snapshot is terminal, so no live SHAP driver exists to anchor an "
    "illustrative what-if scenario, and re-scoring a snapshot that already encodes the known "
    "outcome would not isolate a hypothetical override's effect -- see "
    "docs/DECISION_SUPPORT.md 'Terminal snapshot rule'."
)

SCENARIO_SKIPPED_CATEGORICAL_DRIVER_MESSAGE = (
    "Skipped: this snapshot's live top significant_delay SHAP driver is a categorical feature, "
    "for which no numeric illustrative reference value is well-defined."
)

ML_LIMITATION_DISCLAIMER = (
    "Model outputs are estimates produced by this project's trained models on a SYNTHETIC "
    "dataset (see docs/SYNTHETIC_DATA_METHODOLOGY.md) -- they are not validated against real "
    "highway-project outcomes and do not guarantee what will actually happen to this project."
)

CAUSALITY_LIMITATION_DISCLAIMER = (
    "Model feature importance describes association ('the model places importance on...', "
    "'is associated with...'), not causation. Nothing in this response establishes that a "
    "modeled driver causes a delay or cost overrun -- see docs/DECISION_SUPPORT.md."
)

SCENARIO_LIMITATION_DISCLAIMER = SIMULATION_DISCLAIMER

EVIDENCE_LIMITATION_DISCLAIMER = (
    "Documentary evidence is limited to this project's small real-document corpus (see "
    "docs/RAG_SYSTEM.md). A claim with no supporting citation is reported as 'Not found in "
    "the available documents' rather than filled from general knowledge."
)

INCONSISTENCY_LIMITATION_DISCLAIMER = (
    "Potential inconsistencies require human verification and do not establish that either "
    "cited source is in error -- see docs/CONTRADICTION_DETECTION.md."
)

SYSTEM_IDENTITY_DISCLAIMER = (
    "This is a prototype decision-support system inspired by highway infrastructure project "
    "monitoring/risk-management workflows, built as a student portfolio project. It is NOT an "
    "official NHAI system, NOT an autonomous decision-maker, NOT a fact-checker, and NOT a "
    "legal authority. Every output here is intended for human review, not automated action."
)


class DisclaimersOut(BaseModel):
    ml_limitation: str = ML_LIMITATION_DISCLAIMER
    causality_limitation: str = CAUSALITY_LIMITATION_DISCLAIMER
    scenario_limitation: str = SCENARIO_LIMITATION_DISCLAIMER
    evidence_limitation: str = EVIDENCE_LIMITATION_DISCLAIMER
    inconsistency_limitation: str = INCONSISTENCY_LIMITATION_DISCLAIMER
    system_identity: str = SYSTEM_IDENTITY_DISCLAIMER
    synthetic_data_disclaimer: str = SYNTHETIC_DATA_DISCLAIMER_MODEL


class ProjectSnapshotInfoOut(BaseModel):
    project_id: str
    project_name: str
    state: str
    project_type: str
    contractor: str | None
    highway_number: str
    reporting_month: str
    months_since_start: int
    project_status: str
    is_terminal_snapshot: bool


class RiskSummaryOut(BaseModel):
    significant_delay_summary: str
    final_delay_days_summary: str
    cost_overrun_summary: str
    final_cost_overrun_pct_summary: str


class DriverFeatureOut(BaseModel):
    rank: int
    feature: str
    shap_value: float
    direction: Literal["increases", "decreases", "negligible"]
    explanation: str


class TaskRiskDriversOut(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    task_key: str
    label: str
    model_used: str
    explainer_type: Literal["TreeExplainer", "LinearExplainer"]
    shap_output_semantics: str
    top_drivers: list[DriverFeatureOut]


class EvidenceQueryResultOut(BaseModel):
    query: str
    not_found: bool
    answer: str
    results: list[RetrievalResultOut]


class ScenarioOut(BaseModel):
    field: str
    reference_value: float
    label: str
    baseline: PredictionsBundle
    simulated: PredictionsBundle
    disclaimer: str = SIMULATION_DISCLAIMER


class RecommendationOut(BaseModel):
    text: str
    basis_type: Literal["model_driver", "documentary_evidence", "potential_inconsistency", "scenario"]
    basis_detail: str


class RiskSummaryResponse(BaseModel):
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
    recommended_reviews: list[RecommendationOut]
    evidence_strength: Literal["high evidence support", "moderate evidence support", "limited evidence support"]
    evidence_strength_basis: str
    disclaimers: DisclaimersOut = DisclaimersOut()
