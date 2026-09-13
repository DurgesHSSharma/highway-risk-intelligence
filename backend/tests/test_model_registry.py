"""Phase 6 model registry tests: the task->model mapping, and the
fail-loudly-on-missing-artifact startup contract (brief section 22 item 15,
section 14/28)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.ml.registry import (
    TASK_MODEL_REGISTRY,
    ModelArtifactMissingError,
    TaskModelSpec,
    load_models,
)


def test_registry_covers_all_four_tasks():
    assert set(TASK_MODEL_REGISTRY.keys()) == {
        "significant_delay",
        "final_delay_days",
        "cost_overrun",
        "final_cost_overrun_pct",
    }


def test_registry_artifact_paths_exist_on_disk():
    for spec in TASK_MODEL_REGISTRY.values():
        assert spec.artifact_path.exists(), f"Missing artifact for {spec.task_key}: {spec.artifact_path}"


def test_registry_model_mapping_matches_phase5_report():
    assert TASK_MODEL_REGISTRY["significant_delay"].model_name == "random_forest"
    assert TASK_MODEL_REGISTRY["final_delay_days"].model_name == "xgboost"
    assert TASK_MODEL_REGISTRY["cost_overrun"].model_name == "logistic_regression_baseline"
    assert TASK_MODEL_REGISTRY["final_cost_overrun_pct"].model_name == "linear_regression_baseline"


def test_missing_artifact_fails_loudly_at_load_time(tmp_path: Path):
    broken_registry = {
        "significant_delay": TaskModelSpec(
            task_key="significant_delay",
            target_column="significant_delay",
            model_name="random_forest",
            artifact_relpath="does_not_exist/nonexistent_model.joblib",
            task_type="classification",
            interpretation="test",
        ),
    }
    with pytest.raises(ModelArtifactMissingError):
        load_models(registry=broken_registry)


def test_real_registry_loads_without_error():
    # Uses the actual committed Phase 4/5 artifacts -- no retraining, no
    # substitution.
    load_models()
