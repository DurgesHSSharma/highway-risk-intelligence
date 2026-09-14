"""Phase 11 (REPAIRED) decision-support synthesis pipeline for
GET /projects/{project_id}/risk-summary?reporting_month=YYYY-MM:

    project snapshot
           |
           v
    terminal? --yes--> actual outcome (Phase 6) + evidence/inconsistencies only
           |no
           v
    ML predictions (Phase 6: app.ml.predict.predict_all_tasks)
           |
           v
    LIVE per-instance SHAP risk drivers (app.decision_support.shap_explainer,
    the EXACT model Phase 6 serves for each task)
           |
           +------------------------+
           |                        |
           v                        v
    RAG evidence queries      illustrative scenario
    (top 1-2 live SHAP        (top live significant_delay driver,
     drivers -> topics)        reused via Phase 10's run_simulation)
           |                        |
           v                        |
    RAG evidence (Phase 8)          |
           |                        |
           v                        |
    potential inconsistencies       |
    (Phase 9, scoped to evidence)   |
           |                        |
           +-----------+------------+
                       |
                       v
              decision-support output

Every step reuses an existing Phase 5/6/8/9/10 service unchanged -- see
docs/DECISION_SUPPORT.md for the full design and rationale, including why
this is NOT the earlier (incorrect) static-Phase-5-global-importance
approach.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contradiction.detector import get_detection_summary
from app.db.models import Project, ProjectSnapshot
from app.decision_support.evidence import (
    DEFAULT_EVIDENCE_QUERIES,
    EvidenceQueryResult,
    any_evidence_found,
    evidence_chunk_ids,
    gather_evidence,
    generate_evidence_queries_from_drivers,
)
from app.decision_support.inconsistencies import scope_inconsistencies_to_evidence
from app.decision_support.recommendations import generate_recommendations
from app.decision_support.risk_summary import build_risk_summary
from app.decision_support.scenario import IllustrativeScenario, build_illustrative_scenario
from app.decision_support.shap_explainer import TaskRiskDrivers, explain_instance
from app.ml.features import build_predictor_row
from app.ml.predict import predict_all_tasks
from app.rag.retrieval import get_retrieval_service
from app.schemas.decision_support import (
    SCENARIO_SKIPPED_CATEGORICAL_DRIVER_MESSAGE,
    SCENARIO_SKIPPED_TERMINAL_MESSAGE,
    SHAP_SKIPPED_TERMINAL_MESSAGE,
    RecommendationOut,
    RiskSummaryOut,
)
from app.schemas.predictions import (
    CostOverrunResult,
    FinalCostOverrunPctResult,
    FinalDelayDaysResult,
    SignificantDelayResult,
)
from app.simulation.service import ProjectNotFoundError, SnapshotNotFoundError

TASK_ORDER = ["significant_delay", "final_delay_days", "cost_overrun", "final_cost_overrun_pct"]

__all__ = [
    "RiskSummaryResult",
    "ProjectInfo",
    "ProjectNotFoundError",
    "SnapshotNotFoundError",
    "run_risk_summary",
]


@dataclass(frozen=True)
class ProjectInfo:
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


@dataclass(frozen=True)
class RiskSummaryResult:
    project: ProjectInfo
    prediction_status: str
    predictions: dict
    risk_summary: RiskSummaryOut
    risk_drivers: list[TaskRiskDrivers]
    shap_skipped_reason: str | None
    evidence: list[EvidenceQueryResult]
    inconsistencies: list
    scenario: IllustrativeScenario | None
    scenario_skipped_reason: str | None
    recommendations: list[RecommendationOut]
    evidence_strength: str
    evidence_strength_basis: str


def _evidence_strength(evidence_found: bool, inconsistency_found: bool) -> tuple[str, str]:
    if evidence_found and not inconsistency_found:
        return (
            "high evidence support",
            "High evidence support: the response is accompanied by relevant retrieved "
            "documentary evidence, and no potential inconsistency was flagged against that evidence.",
        )
    if evidence_found and inconsistency_found:
        return (
            "moderate evidence support",
            "Moderate evidence support: relevant documentary evidence was retrieved, but at least one "
            "potential inconsistency touching that evidence was flagged and requires verification.",
        )
    return (
        "limited evidence support",
        "Limited evidence support: no relevant documentary evidence was retrieved from the available "
        "corpus for the evidence queries used.",
    )


def _project_and_snapshot(db: Session, project_id: str, reporting_month: str) -> tuple[Project, ProjectSnapshot]:
    project = db.get(Project, project_id)
    if project is None:
        raise ProjectNotFoundError(f"Project '{project_id}' not found.")

    snapshot = db.execute(
        select(ProjectSnapshot)
        .where(ProjectSnapshot.project_id == project_id)
        .where(ProjectSnapshot.reporting_month == reporting_month)
    ).scalar_one_or_none()
    if snapshot is None:
        raise SnapshotNotFoundError(
            f"No snapshot for project '{project_id}' at reporting_month '{reporting_month}'."
        )
    return project, snapshot


def _project_info(project: Project, snapshot: ProjectSnapshot, reporting_month: str) -> ProjectInfo:
    return ProjectInfo(
        project_id=project.project_id,
        project_name=project.project_name,
        state=project.state,
        project_type=project.project_type,
        contractor=project.contractor,
        highway_number=project.highway_number,
        reporting_month=reporting_month,
        months_since_start=snapshot.months_since_start,
        project_status=snapshot.project_status,
        is_terminal_snapshot=snapshot.is_terminal_snapshot,
    )


def _actual_outcome_predictions(snapshot: ProjectSnapshot) -> dict:
    """Mirrors Phase 6's own terminal-snapshot branch
    (app.routers.predictions.predict) exactly: recorded actual outcomes,
    never a model prediction, for a terminal snapshot."""
    return {
        "significant_delay": SignificantDelayResult(actual_value=snapshot.significant_delay),
        "final_delay_days": FinalDelayDaysResult(actual_value=snapshot.final_delay_days),
        "cost_overrun": CostOverrunResult(actual_value=snapshot.cost_overrun),
        "final_cost_overrun_pct": FinalCostOverrunPctResult(actual_value=snapshot.final_cost_overrun_pct),
    }


def _terminal_risk_summary(snapshot: ProjectSnapshot) -> RiskSummaryOut:
    sig = "yes" if snapshot.significant_delay == 1 else "no"
    cost = "yes" if snapshot.cost_overrun == 1 else "no"
    return RiskSummaryOut(
        significant_delay_summary=(
            f"Recorded actual outcome (terminal snapshot, not a model prediction): "
            f"significant delay = {sig}."
        ),
        final_delay_days_summary=(
            f"Recorded actual outcome (terminal snapshot, not a model prediction): "
            f"final delay = {snapshot.final_delay_days} days."
        ),
        cost_overrun_summary=(
            f"Recorded actual outcome (terminal snapshot, not a model prediction): "
            f"cost overrun = {cost}."
        ),
        final_cost_overrun_pct_summary=(
            f"Recorded actual outcome (terminal snapshot, not a model prediction): "
            f"final cost overrun = {snapshot.final_cost_overrun_pct:.1f}%."
        ),
    )


def _gather_evidence_and_inconsistencies(
    evidence_queries: list[str],
) -> tuple[list[EvidenceQueryResult], list]:
    retrieval_service = get_retrieval_service()
    evidence = gather_evidence(retrieval_service, evidence_queries)
    relevant_chunk_ids = evidence_chunk_ids(evidence)
    detection_summary = get_detection_summary()
    scoped_inconsistencies = scope_inconsistencies_to_evidence(detection_summary, relevant_chunk_ids)
    return evidence, scoped_inconsistencies


def run_risk_summary(db: Session, project_id: str, reporting_month: str) -> RiskSummaryResult:
    project, snapshot = _project_and_snapshot(db, project_id, reporting_month)
    project_info = _project_info(project, snapshot, reporting_month)

    if snapshot.is_terminal_snapshot:
        # Terminal snapshot: DO NOT run prediction/SHAP/simulation (repair
        # brief section F) -- actual recorded outcomes only, mirroring
        # Phase 6's own terminal branch. Evidence/inconsistencies still run
        # (permitted), using the fixed default queries since no live SHAP
        # driver exists to derive queries from.
        predictions = _actual_outcome_predictions(snapshot)
        risk_summary = _terminal_risk_summary(snapshot)
        evidence, scoped_inconsistencies = _gather_evidence_and_inconsistencies(list(DEFAULT_EVIDENCE_QUERIES))

        evidence_found = any_evidence_found(evidence)
        inconsistency_found = len(scoped_inconsistencies) > 0
        strength, basis = _evidence_strength(evidence_found, inconsistency_found)

        recommendations = generate_recommendations(
            risk_drivers=[], evidence=evidence, inconsistencies=scoped_inconsistencies, scenario=None
        )

        return RiskSummaryResult(
            project=project_info,
            prediction_status="actual_outcome",
            predictions=predictions,
            risk_summary=risk_summary,
            risk_drivers=[],
            shap_skipped_reason=SHAP_SKIPPED_TERMINAL_MESSAGE,
            evidence=evidence,
            inconsistencies=scoped_inconsistencies,
            scenario=None,
            scenario_skipped_reason=SCENARIO_SKIPPED_TERMINAL_MESSAGE,
            recommendations=recommendations,
            evidence_strength=strength,
            evidence_strength_basis=basis,
        )

    # --- Non-terminal: full live pipeline ---
    X = build_predictor_row(db, project_id, reporting_month)
    predictions = predict_all_tasks(X)
    risk_summary = build_risk_summary(
        predictions["significant_delay"],
        predictions["final_delay_days"],
        predictions["cost_overrun"],
        predictions["final_cost_overrun_pct"],
    )

    # LIVE per-instance SHAP, one call per task, each against the EXACT
    # model app.ml.registry.TASK_MODEL_REGISTRY serves for that task.
    risk_drivers = [explain_instance(task_key, X) for task_key in TASK_ORDER]
    significant_delay_drivers = risk_drivers[0]

    evidence_queries = generate_evidence_queries_from_drivers(risk_drivers)
    evidence, scoped_inconsistencies = _gather_evidence_and_inconsistencies(evidence_queries)

    scenario = build_illustrative_scenario(db, project_id, reporting_month, significant_delay_drivers)
    scenario_skipped_reason = None if scenario is not None else SCENARIO_SKIPPED_CATEGORICAL_DRIVER_MESSAGE

    evidence_found = any_evidence_found(evidence)
    inconsistency_found = len(scoped_inconsistencies) > 0
    strength, basis = _evidence_strength(evidence_found, inconsistency_found)

    recommendations = generate_recommendations(
        risk_drivers=risk_drivers,
        evidence=evidence,
        inconsistencies=scoped_inconsistencies,
        scenario=scenario,
    )

    return RiskSummaryResult(
        project=project_info,
        prediction_status="model_prediction",
        predictions=predictions,
        risk_summary=risk_summary,
        risk_drivers=risk_drivers,
        shap_skipped_reason=None,
        evidence=evidence,
        inconsistencies=scoped_inconsistencies,
        scenario=scenario,
        scenario_skipped_reason=scenario_skipped_reason,
        recommendations=recommendations,
        evidence_strength=strength,
        evidence_strength_basis=basis,
    )
