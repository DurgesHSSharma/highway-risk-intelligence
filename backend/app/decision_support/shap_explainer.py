"""Phase 11 REPAIR: LIVE, per-instance SHAP explanations of the EXACT model
that Phase 6 actually serves for each task (`app.ml.registry.TASK_MODEL_REGISTRY`)
-- replacing the earlier (incorrect) approach of reusing Phase 5's static,
cross-model-family global feature-importance JSON.

Verified empirically (not assumed) before this module was written -- see
the additivity assertions in this module's own tests -- that for every
task, `base_value + sum(shap_values)` reconstructs that task's actual
serving pipeline output exactly (within float tolerance):

- `significant_delay` (RandomForestClassifier via shap.TreeExplainer):
  reconstructs `pipeline.predict_proba(Xt)[:, 1]` exactly.
- `final_delay_days` (XGBRegressor via shap.TreeExplainer):
  reconstructs `pipeline.predict(Xt)` exactly.
- `cost_overrun` (LogisticRegression via shap.LinearExplainer):
  reconstructs `pipeline.decision_function(Xt)` (log-odds/margin scale,
  NOT probability) exactly.
- `final_cost_overrun_pct` (LinearRegression via shap.LinearExplainer):
  reconstructs `pipeline.predict(Xt)` exactly.

No model is retrained, refit, or reloaded here -- every explainer wraps the
exact `model` step of the exact singleton Pipeline `app.ml.registry.get_model`
already loaded once at startup. Preprocessing is never refit: the already
-fitted `preprocess` step's `.transform()` is the only preprocessing call
made, mirroring `scripts/explain_models.py`'s established Phase 5 pattern
(`pipeline.named_steps["preprocess"]` / `pipeline.named_steps["model"]`).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

from app.config import REPO_ROOT
from app.ml.registry import TASK_MODEL_REGISTRY, get_model

TREE_EXPLAINED_TASKS = {"significant_delay", "final_delay_days"}
LINEAR_EXPLAINED_TASKS = {"cost_overrun", "final_cost_overrun_pct"}

TOP_N_DRIVERS = 5

# Background data for shap.LinearExplainer is a fixed, seeded sample of the
# frozen Phase 4 TRAINING partition ONLY -- never validation/test/full
# dataset/live snapshot data (same rule Phase 10's training_feature_ranges.json
# already follows). shap.TreeExplainer needs no background at all (verified:
# it runs correctly with none, standard SHAP tree-path behavior).
BACKGROUND_SAMPLE_SIZE = 100
BACKGROUND_SEED = 42
BACKGROUND_FEATURES_PATH = REPO_ROOT / "data" / "processed" / "delay_features.csv"

_TASK_LABELS: dict[str, str] = {
    "significant_delay": "Significant Delay Classification",
    "final_delay_days": "Delay Duration Regression",
    "cost_overrun": "Cost Overrun Classification",
    "final_cost_overrun_pct": "Cost Overrun Regression",
}

# What the SHAP value axis actually means for each task's explainer/model
# combination -- required to be documented precisely (repair brief section
# C): a classification SHAP value from shap.LinearExplainer on a
# LogisticRegression is on the LINEAR DECISION FUNCTION (log-odds/margin)
# scale, not a probability, exactly analogous to how Phase 5 already
# disclosed XGBoost's classification SHAP values are log-odds-scale (see
# docs/SHAP_EXPLAINABILITY_REPORT.md's own "Output scale" section).
_SHAP_OUTPUT_SEMANTICS: dict[str, str] = {
    "significant_delay": (
        "Each SHAP value is that feature's contribution to the Random Forest's predicted "
        "PROBABILITY of the positive (significant-delay) class for this specific snapshot "
        "(probability-scale units, via shap.TreeExplainer on the served RandomForestClassifier)."
    ),
    "final_delay_days": (
        "Each SHAP value is that feature's contribution to the XGBoost model's predicted "
        "final-delay-days regression output for this specific snapshot (same units as the "
        "prediction itself: days, via shap.TreeExplainer on the served XGBRegressor)."
    ),
    "cost_overrun": (
        "Each SHAP value is that feature's contribution to the Logistic Regression baseline's "
        "LINEAR DECISION FUNCTION (log-odds / margin scale, NOT probability) for the positive "
        "(cost-overrun) class, for this specific snapshot (via shap.LinearExplainer on the "
        "served LogisticRegression -- consistent with how Phase 5 already documents XGBoost's "
        "classification SHAP values as log-odds-scale, not probability-scale)."
    ),
    "final_cost_overrun_pct": (
        "Each SHAP value is that feature's contribution to the Linear Regression baseline's "
        "predicted final-cost-overrun-percentage regression output for this specific snapshot "
        "(same units as the prediction itself: percentage points, via shap.LinearExplainer on "
        "the served LinearRegression)."
    ),
}

_RISK_PHRASE: dict[str, str] = {
    "significant_delay": "model-estimated probability of significant delay",
    "final_delay_days": "model-estimated final delay",
    "cost_overrun": "model-estimated probability of cost overrun",
    "final_cost_overrun_pct": "model-estimated final cost overrun",
}


def clean_feature_name(raw_feature: str) -> str:
    """Strips the sklearn ColumnTransformer prefix ('numeric__' /
    'categorical__') for display."""
    if raw_feature.startswith("numeric__"):
        return raw_feature[len("numeric__") :]
    if raw_feature.startswith("categorical__"):
        return raw_feature[len("categorical__") :]
    return raw_feature


def driver_identity(feature: str, raw_feature: str) -> str:
    """Reduces a (cleaned, raw) SHAP feature pair to its raw predictor
    -column identity, so e.g. 'state_Karnataka' and 'state_Assam' both
    identify as 'state' -- used to deduplicate recommendations/evidence
    queries derived from top drivers across tasks. Only a genuinely
    CATEGORICAL feature (raw_feature carries the 'categorical__'
    ColumnTransformer prefix) is reduced this way -- a numeric feature is
    never matched against a same-named categorical column just because its
    cleaned name happens to start with that column's name."""
    from scripts.prepare_features import RAW_CATEGORICAL

    if raw_feature.startswith("categorical__"):
        for col in RAW_CATEGORICAL:
            if feature.startswith(f"{col}_"):
                return col
        return feature
    return feature


@dataclass(frozen=True)
class DriverFeature:
    rank: int
    feature: str  # cleaned, display name
    raw_feature: str  # original ColumnTransformer-prefixed name (identity use)
    shap_value: float
    direction: Literal["increases", "decreases", "negligible"]
    explanation: str


@dataclass(frozen=True)
class TaskRiskDrivers:
    task_key: str
    label: str
    model_used: str
    explainer_type: Literal["TreeExplainer", "LinearExplainer"]
    shap_output_semantics: str
    top_drivers: list[DriverFeature]


_EXPLAINER_CACHE: dict[str, object] = {}
_BACKGROUND_CACHE: dict[str, np.ndarray] = {}


def _build_background(preprocessor) -> np.ndarray:
    """Fixed, seeded sample of the frozen Phase 4 TRAINING partition,
    transformed through the ALREADY-FITTED preprocessor (never refit).
    Cached module-wide -- built at most once per process, mirroring the
    "load once" convention already used for models/RAG index/detector."""
    from scripts.data_split import project_level_split
    from scripts.prepare_features import PREDICTOR_COLUMNS

    df = pd.read_csv(BACKGROUND_FEATURES_PATH)
    split = project_level_split(df)  # seed=42, 70/15/15, terminal excluded -- unchanged Phase 4 defaults
    rng = np.random.default_rng(BACKGROUND_SEED)
    n = min(BACKGROUND_SAMPLE_SIZE, len(split.train))
    idx = rng.choice(len(split.train), size=n, replace=False)
    X_bg_raw = split.train[PREDICTOR_COLUMNS].reset_index(drop=True).iloc[idx]

    Xt_bg = preprocessor.transform(X_bg_raw)
    if hasattr(Xt_bg, "toarray"):
        Xt_bg = Xt_bg.toarray()
    return Xt_bg


def _get_explainer(task_key: str):
    if task_key in _EXPLAINER_CACHE:
        return _EXPLAINER_CACHE[task_key]

    # Imported lazily, not at module import: `import shap` pulls in numba, llvmlite
    # and matplotlib (~50 MB resident, measured), which every process would
    # otherwise pay for at startup -- including requests that never compute SHAP
    # values (project lists, analytics, terminal-snapshot reports). Behavior is
    # identical; only WHEN the import happens moves, to the first SHAP request.
    import shap

    pipeline = get_model(task_key)
    model = pipeline.named_steps["model"]

    if task_key in TREE_EXPLAINED_TASKS:
        explainer = shap.TreeExplainer(model)
    elif task_key in LINEAR_EXPLAINED_TASKS:
        preprocessor = pipeline.named_steps["preprocess"]
        cache_key = f"bg::{task_key}"
        if cache_key not in _BACKGROUND_CACHE:
            _BACKGROUND_CACHE[cache_key] = _build_background(preprocessor)
        explainer = shap.LinearExplainer(model, _BACKGROUND_CACHE[cache_key])
    else:
        raise ValueError(f"No SHAP explainer strategy registered for task_key={task_key!r}")

    _EXPLAINER_CACHE[task_key] = explainer
    return explainer


def _direction(shap_value: float) -> Literal["increases", "decreases", "negligible"]:
    if shap_value > 0:
        return "increases"
    if shap_value < 0:
        return "decreases"
    return "negligible"


def _driver_explanation(task_key: str, feature: str, direction: str, shap_value: float) -> str:
    risk_phrase = _RISK_PHRASE[task_key]
    if direction == "negligible":
        return f"`{feature}` has a negligible effect on the {risk_phrase} for this snapshot."
    return (
        f"`{feature}` is associated with a {direction} {risk_phrase} for this snapshot "
        f"(live SHAP contribution: {shap_value:+.4f}, not a causal claim)."
    )


def explain_instance(task_key: str, X_raw: pd.DataFrame, top_n: int = TOP_N_DRIVERS) -> TaskRiskDrivers:
    """Computes LIVE SHAP values for the given single-row predictor
    DataFrame using the EXACT model that Phase 6's registry serves for this
    task. `X_raw` must be the same 45-column predictor row produced by
    `app.ml.features.build_predictor_row` (or an equivalent single-row
    DataFrame with the same columns)."""
    pipeline = get_model(task_key)
    preprocessor = pipeline.named_steps["preprocess"]

    Xt = preprocessor.transform(X_raw)
    if hasattr(Xt, "toarray"):
        Xt = Xt.toarray()
    feature_names = list(preprocessor.get_feature_names_out())

    explainer = _get_explainer(task_key)
    explanation = explainer(Xt)
    values = np.array(explanation.values)

    if values.ndim == 3:
        # RandomForestClassifier via TreeExplainer: shape (n, features,
        # n_classes) -- keep class 1 (verified against predict_proba[:, 1]).
        values = values[..., 1]

    row_values = values[0]
    order = np.argsort(np.abs(row_values))[::-1][:top_n]

    spec = TASK_MODEL_REGISTRY[task_key]
    explainer_type: Literal["TreeExplainer", "LinearExplainer"] = (
        "TreeExplainer" if task_key in TREE_EXPLAINED_TASKS else "LinearExplainer"
    )

    drivers: list[DriverFeature] = []
    for rank, i in enumerate(order, start=1):
        shap_value = float(row_values[i])
        direction = _direction(shap_value)
        raw_name = feature_names[i]
        cleaned = clean_feature_name(raw_name)
        drivers.append(
            DriverFeature(
                rank=rank,
                feature=cleaned,
                raw_feature=raw_name,
                shap_value=shap_value,
                direction=direction,
                explanation=_driver_explanation(task_key, cleaned, direction, shap_value),
            )
        )

    return TaskRiskDrivers(
        task_key=task_key,
        label=_TASK_LABELS[task_key],
        model_used=spec.model_name,
        explainer_type=explainer_type,
        shap_output_semantics=_SHAP_OUTPUT_SEMANTICS[task_key],
        top_drivers=drivers,
    )


def reset_explainer_cache_for_tests() -> None:
    global _EXPLAINER_CACHE, _BACKGROUND_CACHE
    _EXPLAINER_CACHE = {}
    _BACKGROUND_CACHE = {}
