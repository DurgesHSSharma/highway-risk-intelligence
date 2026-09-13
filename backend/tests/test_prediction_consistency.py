"""Phase 6 prediction-consistency test (brief section 20): proves the API
is actually using the saved Phase 4/5 training pipeline correctly, by
reconstructing the same feature vector and running the same saved model
artifact completely independently of the API/router code, then checking
the API's response matches within tolerance.
"""

from __future__ import annotations

import joblib
import pandas as pd
import pytest

from app.config import REPO_ROOT
from app.db.models import Project, ProjectSnapshot
from app.ml.features import build_predictor_row
from app.ml.registry import TASK_MODEL_REGISTRY
from scripts.prepare_features import PREDICTOR_COLUMNS

NON_TERMINAL_PROJECT_ID = "HRI-0006"
NON_TERMINAL_MONTH = "2022-12"

TOLERANCE = 1e-6


def test_feature_row_matches_phase3_precomputed_features(db_session):
    """build_predictor_row's on-the-fly (prefix-history) computation must
    exactly reproduce Phase 3's full-file computation for the same row --
    this is the core technical assumption behind reusing the project's own
    truncated history at prediction time."""
    row = build_predictor_row(db_session, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH)

    delay_features = pd.read_csv(REPO_ROOT / "data" / "processed" / "delay_features.csv")
    ref = delay_features[
        (delay_features["project_id"] == NON_TERMINAL_PROJECT_ID)
        & (delay_features["reporting_month"] == NON_TERMINAL_MONTH)
    ].iloc[0]

    for col in PREDICTOR_COLUMNS:
        actual = row.iloc[0][col]
        expected = ref[col]
        if pd.isna(actual) and pd.isna(expected):
            continue
        if isinstance(expected, (int, float)):
            assert actual == pytest.approx(expected, abs=TOLERANCE), f"mismatch in {col}"
        else:
            assert actual == expected, f"mismatch in {col}"


def test_api_prediction_matches_offline_pipeline_prediction(client, db_session):
    row = build_predictor_row(db_session, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH)

    offline = {}
    for task_key, spec in TASK_MODEL_REGISTRY.items():
        model = joblib.load(spec.artifact_path)
        if spec.task_type == "classification":
            classes = list(model.classes_)
            proba = model.predict_proba(row)[0]
            offline[task_key] = {
                "predicted_class": int(model.predict(row)[0]),
                "probability_of_1": float(proba[classes.index(1)]),
            }
        else:
            offline[task_key] = {"predicted_value": float(model.predict(row)[0])}

    resp = client.get(
        f"/projects/{NON_TERMINAL_PROJECT_ID}/predict",
        params={"reporting_month": NON_TERMINAL_MONTH},
    )
    assert resp.status_code == 200
    body = resp.json()

    assert body["significant_delay"]["predicted_class"] == offline["significant_delay"]["predicted_class"]
    assert body["significant_delay"]["probability_of_significant_delay"] == pytest.approx(
        offline["significant_delay"]["probability_of_1"], abs=TOLERANCE
    )

    assert body["final_delay_days"]["predicted_final_delay_days"] == pytest.approx(
        offline["final_delay_days"]["predicted_value"], abs=1e-3
    )

    assert body["cost_overrun"]["predicted_class"] == offline["cost_overrun"]["predicted_class"]
    assert body["cost_overrun"]["probability_of_cost_overrun"] == pytest.approx(
        offline["cost_overrun"]["probability_of_1"], abs=TOLERANCE
    )

    assert body["final_cost_overrun_pct"]["predicted_final_cost_overrun_pct"] == pytest.approx(
        offline["final_cost_overrun_pct"]["predicted_value"], abs=1e-3
    )
