"""Phase 6 missing-feature behavior (brief section 19 / 22 item 14).

Normal missingness in numeric predictor columns (e.g.
`actual_financial_progress_pct`, ~3.8% missing in the source dataset) is
legitimately handled by the saved pipeline's own `SimpleImputer` -- NaN is
passed straight through, never replaced by a value invented in the API.
That is exercised implicitly by every non-terminal prediction test (real
snapshots in this dataset do carry such NaNs). This file tests the other
documented case: when a valid feature row genuinely cannot be constructed
(e.g. a structurally required raw field is absent), `build_predictor_row`
itself must still raise a clear `FeatureConstructionError`, never silently
guess a value.

Phase 17B: at the API layer, that error is no longer surfaced as a raw
422 -- it's an expected data-completeness state (most commonly a newly
created project without enough monthly history yet), so
GET /predict returns HTTP 200 with prediction_status="insufficient_data"
and no populated task results instead (see app/routers/predictions.py).
"""

from __future__ import annotations

import pandas as pd
import pytest

from app.ml.features import FeatureConstructionError, build_predictor_row

NON_TERMINAL_PROJECT_ID = "HRI-0006"
NON_TERMINAL_MONTH = "2022-12"


def test_normal_missing_numeric_value_does_not_raise(db_session):
    """Sanity check: ordinary documented missingness is NOT treated as a
    construction error -- the pipeline's imputer is expected to handle it."""
    row = build_predictor_row(db_session, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH)
    assert len(row) == 1


def test_missing_required_structural_field_raises_feature_construction_error(db_session, monkeypatch):
    import app.ml.features as features_module

    real_history = features_module._project_history_dataframe

    def _drop_required_column(db, project_id, up_to_month):
        df = real_history(db, project_id, up_to_month)
        return df.drop(columns=["months_since_start"])

    monkeypatch.setattr(features_module, "_project_history_dataframe", _drop_required_column)

    with pytest.raises(FeatureConstructionError):
        build_predictor_row(db_session, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH)


def test_predict_endpoint_returns_insufficient_data_when_feature_row_cannot_be_built(client, monkeypatch):
    import app.routers.predictions as predictions_module

    def _raise(*args, **kwargs):
        raise FeatureConstructionError("simulated: a required predictor field was unavailable")

    monkeypatch.setattr(predictions_module, "build_predictor_row", _raise)

    resp = client.get(
        f"/projects/{NON_TERMINAL_PROJECT_ID}/predict",
        params={"reporting_month": NON_TERMINAL_MONTH},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["prediction_status"] == "insufficient_data"
    assert body["is_model_prediction"] is False
    assert "simulated" in body["explanation"]
    assert body["significant_delay"]["predicted_class"] is None
    assert body["final_delay_days"]["predicted_final_delay_days"] is None
    assert body["cost_overrun"]["predicted_class"] is None
    assert body["final_cost_overrun_pct"]["predicted_final_cost_overrun_pct"] is None
