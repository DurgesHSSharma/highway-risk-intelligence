"""Phase 6 model registry: ONE explicit, auditable task -> model mapping.

The mapping below is taken directly from docs/MODEL_COMPARISON_REPORT.md
section 8 ("Recommended model per task"), verified against the actual
Phase 5 report rather than assumed:

| Task                    | Recommended model                         |
|-------------------------|--------------------------------------------|
| significant_delay       | Random Forest (delay classification)        |
| final_delay_days        | XGBoost (delay regression)                  |
| cost_overrun            | Phase 4 baseline: Logistic Regression       |
| final_cost_overrun_pct  | Phase 4 baseline: Linear Regression         |

Models are loaded ONCE at application startup (`load_models`, called from
app/main.py's startup event) and never retrained, refit, or reloaded per
request (see section 14/27/28 of the Phase 6 brief -- resource-constrained
dev machine, no request-time retraining). If any artifact is missing, this
module fails loudly (raises `ModelArtifactMissingError`) rather than
silently falling back to another model or fabricating predictions.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import joblib

from app.config import settings


class ModelArtifactMissingError(RuntimeError):
    pass


@dataclass(frozen=True)
class TaskModelSpec:
    task_key: str
    target_column: str
    model_name: str
    artifact_relpath: str
    task_type: Literal["classification", "regression"]
    interpretation: str

    @property
    def artifact_path(self) -> Path:
        return settings.models_dir_path / self.artifact_relpath


TASK_MODEL_REGISTRY: dict[str, TaskModelSpec] = {
    "significant_delay": TaskModelSpec(
        task_key="significant_delay",
        target_column="significant_delay",
        model_name="random_forest",
        artifact_relpath="random_forest/delay_classification_random_forest.joblib",
        task_type="classification",
        interpretation=(
            "Predicted probability that the project will experience a significant "
            "delay. Phase 5 recommended model: Random Forest beat the Phase 4 "
            "baseline (test ROC-AUC 0.915 vs. 0.875) with the smallest train/test gap."
        ),
    ),
    "final_delay_days": TaskModelSpec(
        task_key="final_delay_days",
        target_column="final_delay_days",
        model_name="xgboost",
        artifact_relpath="xgboost/delay_regression_xgboost.joblib",
        task_type="regression",
        interpretation=(
            "Predicted total project delay in days at completion. Phase 5 "
            "recommended model: XGBoost beat the Phase 4 baseline (test R² 0.571 "
            "vs. 0.492)."
        ),
    ),
    "cost_overrun": TaskModelSpec(
        task_key="cost_overrun",
        target_column="cost_overrun",
        model_name="logistic_regression_baseline",
        artifact_relpath="baseline/cost_classification_logistic_regression.joblib",
        task_type="classification",
        interpretation=(
            "Predicted probability of a cost overrun. Phase 5 recommended model: the "
            "Phase 4 Logistic Regression baseline -- neither tree model beat it on "
            "test (test ROC-AUC 0.941 vs. RF 0.934 / XGBoost 0.870)."
        ),
    ),
    "final_cost_overrun_pct": TaskModelSpec(
        task_key="final_cost_overrun_pct",
        target_column="final_cost_overrun_pct",
        model_name="linear_regression_baseline",
        artifact_relpath="baseline/cost_regression_linear_regression.joblib",
        task_type="regression",
        interpretation=(
            "Predicted final cost-overrun percentage at completion. Phase 5 "
            "recommended model: the Phase 4 Linear Regression baseline -- it "
            "substantially outperforms both tree models on test (R² 0.905 vs. "
            "RF 0.680 / XGBoost 0.749)."
        ),
    ),
}

_LOADED_MODELS: dict[str, Any] = {}


def load_models(registry: dict[str, TaskModelSpec] = TASK_MODEL_REGISTRY) -> None:
    """Load every registered model artifact once. Raises
    ModelArtifactMissingError immediately (failing the app startup) if any
    artifact is absent -- never silently substitutes another model."""
    missing = [spec.task_key for spec in registry.values() if not spec.artifact_path.exists()]
    if missing:
        details = "\n".join(f"  - {registry[k].task_key}: expected {registry[k].artifact_path}" for k in missing)
        raise ModelArtifactMissingError(
            "Phase 6 startup failed: required Phase 4/5 model artifact(s) not found:\n"
            f"{details}\n"
            "This service does not retrain models or fall back to a substitute -- "
            "restore the missing artifact(s) (they are committed to git in Phases 4/5) "
            "before starting the API."
        )
    for spec in registry.values():
        _LOADED_MODELS[spec.task_key] = joblib.load(spec.artifact_path)


def is_loaded() -> bool:
    return len(_LOADED_MODELS) == len(TASK_MODEL_REGISTRY)


def get_model(task_key: str) -> Any:
    if task_key not in _LOADED_MODELS:
        raise ModelArtifactMissingError(
            f"Model for task '{task_key}' was not loaded at startup. This should be "
            "unreachable if the application started successfully."
        )
    return _LOADED_MODELS[task_key]
