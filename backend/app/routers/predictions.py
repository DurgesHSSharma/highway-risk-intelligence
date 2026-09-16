"""Prediction endpoint: GET /projects/{project_id}/predict?reporting_month=YYYY-MM.

Terminal snapshots never touch a model (recorded actual outcomes are
returned instead); non-terminal snapshots run all four Phase 5 recommended
models (see app.ml.registry.TASK_MODEL_REGISTRY), each loaded once at
startup, against the same 45-column feature row built by
app.ml.features.build_predictor_row.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.db.models import Project, ProjectSnapshot
from app.ml.features import FeatureConstructionError, build_predictor_row
from app.ml.predict import predict_all_tasks
from app.validation import MONTH_DESCRIPTION, MONTH_PATTERN
from app.schemas.predictions import (
    NON_TERMINAL_EXPLANATION,
    SYNTHETIC_DATA_DISCLAIMER_ACTUAL,
    SYNTHETIC_DATA_DISCLAIMER_MODEL,
    TERMINAL_EXPLANATION,
    CostOverrunResult,
    FinalCostOverrunPctResult,
    FinalDelayDaysResult,
    PredictionResponse,
    SignificantDelayResult,
)

router = APIRouter(prefix="/projects", tags=["predictions"])


@router.get("/{project_id}/predict", response_model=PredictionResponse)
def predict(
    project_id: str,
    reporting_month: str = Query(..., pattern=MONTH_PATTERN, description=MONTH_DESCRIPTION),
    db: Session = Depends(get_db),
) -> PredictionResponse:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")

    snapshot = db.execute(
        select(ProjectSnapshot)
        .where(ProjectSnapshot.project_id == project_id)
        .where(ProjectSnapshot.reporting_month == reporting_month)
    ).scalar_one_or_none()
    if snapshot is None:
        raise HTTPException(
            status_code=404,
            detail=f"No snapshot for project '{project_id}' at reporting_month '{reporting_month}'.",
        )

    if snapshot.is_terminal_snapshot:
        return PredictionResponse(
            project_id=project_id,
            reporting_month=reporting_month,
            is_terminal_snapshot=True,
            prediction_status="actual_outcome",
            is_model_prediction=False,
            explanation=TERMINAL_EXPLANATION,
            synthetic_data_disclaimer=SYNTHETIC_DATA_DISCLAIMER_ACTUAL,
            significant_delay=SignificantDelayResult(actual_value=snapshot.significant_delay),
            final_delay_days=FinalDelayDaysResult(actual_value=snapshot.final_delay_days),
            cost_overrun=CostOverrunResult(actual_value=snapshot.cost_overrun),
            final_cost_overrun_pct=FinalCostOverrunPctResult(actual_value=snapshot.final_cost_overrun_pct),
        )

    try:
        X = build_predictor_row(db, project_id, reporting_month)
    except FeatureConstructionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    results = predict_all_tasks(X)

    return PredictionResponse(
        project_id=project_id,
        reporting_month=reporting_month,
        is_terminal_snapshot=False,
        prediction_status="model_prediction",
        is_model_prediction=True,
        explanation=NON_TERMINAL_EXPLANATION,
        synthetic_data_disclaimer=SYNTHETIC_DATA_DISCLAIMER_MODEL,
        significant_delay=results["significant_delay"],
        final_delay_days=results["final_delay_days"],
        cost_overrun=results["cost_overrun"],
        final_cost_overrun_pct=results["final_cost_overrun_pct"],
    )
