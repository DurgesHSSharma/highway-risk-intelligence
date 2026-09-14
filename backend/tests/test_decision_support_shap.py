"""Phase 11 REPAIR: proves the live SHAP explainer actually explains the
SAME model that Phase 6 serves for each task -- not merely that a "shap"
field exists in the output. Every additivity check reconstructs the
serving pipeline's own raw output (decision_function / predict /
predict_proba) from base_value + sum(shap_values), which only holds if the
explainer genuinely wraps that exact fitted model.
"""

from __future__ import annotations

import re

import numpy as np
import shap
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LinearRegression, LogisticRegression
from xgboost import XGBRegressor

from app.decision_support.shap_explainer import (
    LINEAR_EXPLAINED_TASKS,
    TREE_EXPLAINED_TASKS,
    _get_explainer,
    explain_instance,
)
from app.ml.features import build_predictor_row
from app.ml.registry import TASK_MODEL_REGISTRY, get_model

NON_TERMINAL_PROJECT_ID = "HRI-0006"
NON_TERMINAL_MONTH = "2022-12"

# A second real, non-terminal snapshot with materially different underlying
# feature values (different project, different point in its lifecycle) --
# used to prove SHAP output is INSTANCE-specific, not a static lookup.
OTHER_PROJECT_ID = "HRI-0132"
OTHER_MONTH = "2025-06"

EXPECTED_MODEL_CLASS = {
    "significant_delay": RandomForestClassifier,
    "final_delay_days": XGBRegressor,
    "cost_overrun": LogisticRegression,
    "final_cost_overrun_pct": LinearRegression,
}

EXPECTED_EXPLAINER_CLASS = {
    "significant_delay": shap.TreeExplainer,
    "final_delay_days": shap.TreeExplainer,
    "cost_overrun": shap.LinearExplainer,
    "final_cost_overrun_pct": shap.LinearExplainer,
}


def test_task_to_explained_model_partition_matches_registry():
    assert TREE_EXPLAINED_TASKS == {"significant_delay", "final_delay_days"}
    assert LINEAR_EXPLAINED_TASKS == {"cost_overrun", "final_cost_overrun_pct"}
    assert TREE_EXPLAINED_TASKS | LINEAR_EXPLAINED_TASKS == set(TASK_MODEL_REGISTRY.keys())


def test_served_model_class_matches_expected_registry_family():
    """Reads the actual Phase 6 registry / loaded artifacts -- does not
    assume the mapping, confirms it."""
    for task_key, expected_class in EXPECTED_MODEL_CLASS.items():
        pipeline = get_model(task_key)
        model = pipeline.named_steps["model"]
        assert isinstance(model, expected_class), (
            f"{task_key}: expected served model class {expected_class.__name__}, "
            f"got {type(model).__name__}"
        )


def test_explainer_type_matches_model_family_per_task():
    """The explainer/model relationship itself, not just 'a shap field
    exists'."""
    for task_key, expected_explainer_class in EXPECTED_EXPLAINER_CLASS.items():
        explainer = _get_explainer(task_key)
        assert isinstance(explainer, expected_explainer_class), (
            f"{task_key}: expected explainer {expected_explainer_class.__name__}, "
            f"got {type(explainer).__name__}"
        )
        pipeline = get_model(task_key)
        model = pipeline.named_steps["model"]
        assert isinstance(model, EXPECTED_MODEL_CLASS[task_key])


def test_cost_tasks_no_longer_explained_via_tree_model():
    """The exact regression this repair fixes: the two cost tasks must NOT
    be explained by a tree model (the earlier, incorrect Phase 5 static
    artifact explained XGBoost for both cost tasks even though the served
    model is the Phase 4 linear baseline)."""
    for task_key in ("cost_overrun", "final_cost_overrun_pct"):
        explainer = _get_explainer(task_key)
        assert not isinstance(explainer, shap.TreeExplainer)
        assert isinstance(explainer, shap.LinearExplainer)


def test_additivity_reconstructs_actual_served_pipeline_output(db_session):
    """base_value + sum(shap_values) must reconstruct the serving
    pipeline's own raw output exactly -- this can only hold if the
    explainer wraps the exact fitted model actually used for prediction."""
    X = build_predictor_row(db_session, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH)

    for task_key in TASK_MODEL_REGISTRY:
        pipeline = get_model(task_key)
        preprocessor = pipeline.named_steps["preprocess"]
        model = pipeline.named_steps["model"]
        Xt = preprocessor.transform(X)
        if hasattr(Xt, "toarray"):
            Xt = Xt.toarray()

        explainer = _get_explainer(task_key)
        explanation = explainer(Xt)
        values = np.array(explanation.values)
        base = np.array(explanation.base_values)

        if task_key == "significant_delay":
            values = values[..., 1]
            base = base[..., 1] if base.ndim > 1 else base
            expected = model.predict_proba(Xt)[:, 1]
        elif task_key == "cost_overrun":
            expected = model.decision_function(Xt)
        else:
            expected = model.predict(Xt)

        reconstructed = np.array(base).reshape(-1) + values.reshape(1, -1).sum(axis=1)
        assert np.allclose(reconstructed, expected, atol=1e-3), (
            f"{task_key}: base+sum(shap)={reconstructed} does not match the served "
            f"pipeline's own raw output={expected}"
        )


def test_top_drivers_returned_for_all_four_tasks(db_session):
    X = build_predictor_row(db_session, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH)
    for task_key in TASK_MODEL_REGISTRY:
        result = explain_instance(task_key, X)
        assert result.task_key == task_key
        assert result.model_used == TASK_MODEL_REGISTRY[task_key].model_name
        assert len(result.top_drivers) == 5
        # sorted by |shap_value| descending
        magnitudes = [abs(d.shap_value) for d in result.top_drivers]
        assert magnitudes == sorted(magnitudes, reverse=True)
        for d in result.top_drivers:
            assert d.direction in {"increases", "decreases", "negligible"}
            assert d.rank >= 1


def test_shap_is_instance_specific_not_a_static_lookup(db_session):
    """The core proof this repair requires: two different real snapshots
    must be able to produce different SHAP driver rankings/values, and
    THIS snapshot's live top driver must differ from Phase 5's OLD static
    global top driver ('contractor_productivity_factor') -- proving the
    output is computed from the current snapshot, not read from the
    superseded static artifact."""
    X1 = build_predictor_row(db_session, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH)
    X2 = build_predictor_row(db_session, OTHER_PROJECT_ID, OTHER_MONTH)

    result1 = explain_instance("significant_delay", X1)
    result2 = explain_instance("significant_delay", X2)

    top1 = result1.top_drivers[0]
    top2 = result2.top_drivers[0]

    # Different snapshots -> not guaranteed identical top feature AND/OR
    # value; assert at least the numeric SHAP value differs (a stronger,
    # always-true check than feature identity, which could coincidentally
    # match).
    assert top1.shap_value != top2.shap_value

    # THIS specific snapshot's live top driver differs from Phase 5's old
    # static global-importance top feature for the same task (verified
    # real value, see docs/artifacts/shap_local_examples.json's
    # delay_classification.global_feature_ranking[0] == 'contractor_productivity_factor').
    assert top1.feature != "contractor_productivity_factor", (
        "expected the LIVE per-instance top driver for HRI-0006/2022-12 to differ from "
        "Phase 5's static global top driver -- if this now matches, verify it's a genuine "
        "coincidence and not a regression back to reading the static artifact"
    )


def test_shap_output_semantics_documented_per_task(db_session):
    X = build_predictor_row(db_session, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH)
    semantics = {task_key: explain_instance(task_key, X).shap_output_semantics for task_key in TASK_MODEL_REGISTRY}

    assert "probability" in semantics["significant_delay"].lower()
    assert "days" in semantics["final_delay_days"].lower()
    # The classification linear-explained task must be explicit that it is
    # NOT on a probability scale (log-odds/margin) -- this is the precise
    # distinction the repair brief requires.
    assert "log-odds" in semantics["cost_overrun"].lower() or "margin" in semantics["cost_overrun"].lower()
    assert "not probability" in semantics["cost_overrun"].lower()
    assert "percentage" in semantics["final_cost_overrun_pct"].lower()


def test_driver_explanations_are_non_causal(db_session):
    X = build_predictor_row(db_session, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH)
    for task_key in TASK_MODEL_REGISTRY:
        result = explain_instance(task_key, X)
        for d in result.top_drivers:
            lowered = d.explanation.lower()
            assert not re.search(r"\bcauses\b", lowered)
            assert "will definitely" not in lowered
            assert not re.search(r"\bguaranteed\b", lowered)
            assert "associated with" in lowered or "negligible effect" in lowered
