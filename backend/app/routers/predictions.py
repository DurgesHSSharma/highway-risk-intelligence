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
from app.ml.registry import TASK_MODEL_REGISTRY, get_model
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


def _predict_classification(task_key: str, X) -> tuple[int, float]:
    model = get_model(task_key)
    predicted_class = int(model.predict(X)[0])
    classes = list(model.classes_)
    proba_all = model.predict_proba(X)[0]
    proba_of_1 = float(proba_all[classes.index(1)]) if 1 in classes else None
    return predicted_class, proba_of_1


def _predict_regression(task_key: str, X) -> float:
    model = get_model(task_key)
    return float(model.predict(X)[0])


@router.get("/{project_id}/predict", response_model=PredictionResponse)
def predict(
    project_id: str,
    reporting_month: str = Query(..., description="YYYY-MM"),
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

    delay_spec = TASK_MODEL_REGISTRY["significant_delay"]
    delay_days_spec = TASK_MODEL_REGISTRY["final_delay_days"]
    cost_spec = TASK_MODEL_REGISTRY["cost_overrun"]
    cost_pct_spec = TASK_MODEL_REGISTRY["final_cost_overrun_pct"]

    sig_class, sig_proba = _predict_classification("significant_delay", X)
    delay_days_pred = _predict_regression("final_delay_days", X)
    cost_class, cost_proba = _predict_classification("cost_overrun", X)
    cost_pct_pred = _predict_regression("final_cost_overrun_pct", X)

    return PredictionResponse(
        project_id=project_id,
        reporting_month=reporting_month,
        is_terminal_snapshot=False,
        prediction_status="model_prediction",
        is_model_prediction=True,
        explanation=NON_TERMINAL_EXPLANATION,
        synthetic_data_disclaimer=SYNTHETIC_DATA_DISCLAIMER_MODEL,
        significant_delay=SignificantDelayResult(
            model_used=delay_spec.model_name,
            predicted_class=sig_class,
            probability_of_significant_delay=sig_proba,
        ),
        final_delay_days=FinalDelayDaysResult(
            model_used=delay_days_spec.model_name,
            predicted_final_delay_days=delay_days_pred,
        ),
        cost_overrun=CostOverrunResult(
            model_used=cost_spec.model_name,
            predicted_class=cost_class,
            probability_of_cost_overrun=cost_proba,
        ),
        final_cost_overrun_pct=FinalCostOverrunPctResult(
            model_used=cost_pct_spec.model_name,
            predicted_final_cost_overrun_pct=cost_pct_pred,
        ),
    )
