"""Shared Phase 6/10 prediction helper: runs all four
`app.ml.registry.TASK_MODEL_REGISTRY` models against one already-built
predictor feature row (`app.ml.features.build_predictor_row`).

Extracted from `app.routers.predictions` so the Phase 10 what-if simulator
(`app.simulation.service`) reuses the exact same model-invocation code
instead of duplicating it -- both callers therefore always agree on how a
feature row becomes a prediction. No model loading, retraining, or
preprocessing happens here; `get_model` returns the same singleton
pipelines loaded once at startup by `app.ml.registry.load_models`.
"""

from __future__ import annotations

import pandas as pd

from app.ml.registry import TASK_MODEL_REGISTRY, get_model
from app.schemas.predictions import (
    CostOverrunResult,
    FinalCostOverrunPctResult,
    FinalDelayDaysResult,
    SignificantDelayResult,
)


def _predict_classification(task_key: str, X: pd.DataFrame) -> tuple[int, float | None]:
    model = get_model(task_key)
    predicted_class = int(model.predict(X)[0])
    classes = list(model.classes_)
    proba_all = model.predict_proba(X)[0]
    proba_of_1 = float(proba_all[classes.index(1)]) if 1 in classes else None
    return predicted_class, proba_of_1


def _predict_regression(task_key: str, X: pd.DataFrame) -> float:
    model = get_model(task_key)
    return float(model.predict(X)[0])


def predict_all_tasks(
    X: pd.DataFrame,
) -> dict[str, SignificantDelayResult | FinalDelayDaysResult | CostOverrunResult | FinalCostOverrunPctResult]:
    """Runs the Phase 5-recommended model per task (see TASK_MODEL_REGISTRY)
    against the single-row feature DataFrame `X` and returns the four
    populated `*Result` response models (`actual_value` left `None` --
    these are always model predictions, never recorded outcomes)."""
    delay_spec = TASK_MODEL_REGISTRY["significant_delay"]
    delay_days_spec = TASK_MODEL_REGISTRY["final_delay_days"]
    cost_spec = TASK_MODEL_REGISTRY["cost_overrun"]
    cost_pct_spec = TASK_MODEL_REGISTRY["final_cost_overrun_pct"]

    sig_class, sig_proba = _predict_classification("significant_delay", X)
    delay_days_pred = _predict_regression("final_delay_days", X)
    cost_class, cost_proba = _predict_classification("cost_overrun", X)
    cost_pct_pred = _predict_regression("final_cost_overrun_pct", X)

    return {
        "significant_delay": SignificantDelayResult(
            model_used=delay_spec.model_name,
            predicted_class=sig_class,
            probability_of_significant_delay=sig_proba,
        ),
        "final_delay_days": FinalDelayDaysResult(
            model_used=delay_days_spec.model_name,
            predicted_final_delay_days=delay_days_pred,
        ),
        "cost_overrun": CostOverrunResult(
            model_used=cost_spec.model_name,
            predicted_class=cost_class,
            probability_of_cost_overrun=cost_proba,
        ),
        "final_cost_overrun_pct": FinalCostOverrunPctResult(
            model_used=cost_pct_spec.model_name,
            predicted_final_cost_overrun_pct=cost_pct_pred,
        ),
    }
