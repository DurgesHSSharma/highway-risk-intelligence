"""Phase 10 what-if simulator endpoint tests: POST
/projects/{project_id}/simulate?reporting_month=YYYY-MM. Mirrors the Phase 6
`test_predictions_api.py` fixtures (same real project/snapshot ids) so the
consistency checks below (TEST 6/7) compare against a project/month already
known to be non-terminal.
"""

from __future__ import annotations

import joblib
import pytest

from app.ml.features import build_predictor_row
from app.ml.registry import TASK_MODEL_REGISTRY
from app.ml.training_ranges import get_range
from app.schemas.simulation import SIMULATION_DISCLAIMER

NON_TERMINAL_PROJECT_ID = "HRI-0006"
NON_TERMINAL_MONTH = "2022-12"

TERMINAL_PROJECT_ID = "HRI-0001"
TERMINAL_MONTH = "2024-03"

UNKNOWN_PROJECT_ID = "HRI-9999"

TOLERANCE = 1e-6


def _simulate(client, project_id: str, reporting_month: str, overrides: dict):
    return client.post(
        f"/projects/{project_id}/simulate",
        params={"reporting_month": reporting_month},
        json=overrides,
    )


# --- 404s (API safety: unknown project / unknown month behave like /predict) ---


def test_unknown_project_returns_404(client):
    resp = _simulate(client, UNKNOWN_PROJECT_ID, NON_TERMINAL_MONTH, {"contractor_productivity_factor": 0.6})
    assert resp.status_code == 404


def test_unknown_reporting_month_returns_404(client):
    resp = _simulate(client, NON_TERMINAL_PROJECT_ID, "1999-01", {"contractor_productivity_factor": 0.6})
    assert resp.status_code == 404


# --- TEST 1: directional sanity check ---


def test_worsening_contractor_productivity_does_not_decrease_predicted_delay(client):
    """docs/EDA_REPORT.md: contractor_productivity_factor correlates -0.685
    with final_delay_days at the final snapshot -- lower productivity is
    associated with MORE delay, never less. 0.5 is a real, plausible
    worsened value that stays inside the Phase 4 training range (0.498-1.35),
    so this checks direction in isolation from any extrapolation effect.
    Only this one directionally-relevant task is asserted -- the other three
    tasks are learned, independent model outputs and are not assumed to
    move the same way (per the Phase 10 brief)."""
    resp = _simulate(client, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH, {"contractor_productivity_factor": 0.5})
    assert resp.status_code == 200
    body = resp.json()

    baseline_delay = body["baseline_predictions"]["final_delay_days"]["predicted_final_delay_days"]
    simulated_delay = body["simulated_predictions"]["final_delay_days"]["predicted_final_delay_days"]
    assert simulated_delay >= baseline_delay


# --- TEST 2: invalid field rejection ---


@pytest.mark.parametrize(
    "field,value,expected_reason",
    [
        ("project_id", "HRI-9999", "identifier"),
        ("final_delay_days", 999, "target_column"),
        ("significant_delay", 1, "target_column"),
        ("cost_overrun", 1, "target_column"),
        ("final_cost_overrun_pct", 10.0, "target_column"),
        ("is_terminal_snapshot", True, "terminal_flag"),
        ("planned_expenditure_inr_cr", 500.0, "excluded_from_model_exact_duplicate"),
        ("totally_unknown_field", 123, "unknown_field"),
    ],
)
def test_invalid_override_field_rejected_with_422(client, field, value, expected_reason):
    resp = _simulate(client, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH, {field: value})
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    by_field = {f["field"]: f["reason"] for f in detail["invalid_fields"]}
    assert field in by_field
    assert by_field[field] == expected_reason


def test_invalid_field_is_never_silently_ignored_alongside_a_valid_one(client):
    resp = _simulate(
        client,
        NON_TERMINAL_PROJECT_ID,
        NON_TERMINAL_MONTH,
        {"contractor_productivity_factor": 0.6, "project_id": "HRI-9999"},
    )
    assert resp.status_code == 422
    invalid_field_names = [f["field"] for f in resp.json()["detail"]["invalid_fields"]]
    assert "project_id" in invalid_field_names


# --- TEST 3: terminal snapshot rejection ---


def test_terminal_snapshot_rejected_with_explanation(client):
    resp = _simulate(client, TERMINAL_PROJECT_ID, TERMINAL_MONTH, {"contractor_productivity_factor": 0.6})
    assert resp.status_code == 422
    detail = resp.json()["detail"].lower()
    assert "terminal" in detail
    assert "final outcome" in detail or "known" in detail
    assert "non-terminal" in detail or "earlier" in detail


# --- TEST 4: extrapolation warning ---


def test_extrapolation_warning_present_outside_training_range(client):
    bounds = get_range("land_acquisition_delay_days")
    outside_value = bounds["max"] + 500.0

    resp = _simulate(
        client, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH, {"land_acquisition_delay_days": outside_value}
    )
    assert resp.status_code == 200
    warned_fields = [w["field"] for w in resp.json()["extrapolation_warnings"]]
    assert "land_acquisition_delay_days" in warned_fields


def test_no_extrapolation_warning_inside_training_range(client):
    bounds = get_range("land_acquisition_delay_days")
    inside_value = (bounds["min"] + bounds["max"]) / 2

    resp = _simulate(
        client, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH, {"land_acquisition_delay_days": inside_value}
    )
    assert resp.status_code == 200
    warned_fields = [w["field"] for w in resp.json()["extrapolation_warnings"]]
    assert "land_acquisition_delay_days" not in warned_fields


# --- TEST 6: Phase 6 prediction consistency (baseline == GET /predict, no overrides) ---


def test_simulation_baseline_matches_predict_endpoint_with_no_overrides(client):
    predict_resp = client.get(
        f"/projects/{NON_TERMINAL_PROJECT_ID}/predict", params={"reporting_month": NON_TERMINAL_MONTH}
    )
    sim_resp = _simulate(client, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH, {})
    assert predict_resp.status_code == 200
    assert sim_resp.status_code == 200

    predicted = predict_resp.json()
    baseline = sim_resp.json()["baseline_predictions"]
    assert sim_resp.json()["overrides"] == []

    assert baseline["significant_delay"]["predicted_class"] == predicted["significant_delay"]["predicted_class"]
    assert baseline["significant_delay"]["probability_of_significant_delay"] == pytest.approx(
        predicted["significant_delay"]["probability_of_significant_delay"], abs=TOLERANCE
    )
    assert baseline["final_delay_days"]["predicted_final_delay_days"] == pytest.approx(
        predicted["final_delay_days"]["predicted_final_delay_days"], abs=1e-3
    )
    assert baseline["cost_overrun"]["predicted_class"] == predicted["cost_overrun"]["predicted_class"]
    assert baseline["cost_overrun"]["probability_of_cost_overrun"] == pytest.approx(
        predicted["cost_overrun"]["probability_of_cost_overrun"], abs=TOLERANCE
    )
    assert baseline["final_cost_overrun_pct"]["predicted_final_cost_overrun_pct"] == pytest.approx(
        predicted["final_cost_overrun_pct"]["predicted_final_cost_overrun_pct"], abs=1e-3
    )


# --- TEST 7: pipeline reuse (independent artifact reload) ---


def test_simulation_baseline_matches_independent_artifact_inference(client, db_session):
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

    resp = _simulate(client, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH, {})
    assert resp.status_code == 200
    baseline = resp.json()["baseline_predictions"]

    assert baseline["significant_delay"]["predicted_class"] == offline["significant_delay"]["predicted_class"]
    assert baseline["significant_delay"]["probability_of_significant_delay"] == pytest.approx(
        offline["significant_delay"]["probability_of_1"], abs=TOLERANCE
    )
    assert baseline["final_delay_days"]["predicted_final_delay_days"] == pytest.approx(
        offline["final_delay_days"]["predicted_value"], abs=1e-3
    )
    assert baseline["cost_overrun"]["predicted_class"] == offline["cost_overrun"]["predicted_class"]
    assert baseline["cost_overrun"]["probability_of_cost_overrun"] == pytest.approx(
        offline["cost_overrun"]["probability_of_1"], abs=TOLERANCE
    )
    assert baseline["final_cost_overrun_pct"]["predicted_final_cost_overrun_pct"] == pytest.approx(
        offline["final_cost_overrun_pct"]["predicted_value"], abs=1e-3
    )


# --- TEST 8: multiple overrides ---


def test_multiple_overrides_all_appear_with_correct_values_and_deltas(client):
    overrides = {"land_acquisition_delay_days": 45.0, "contractor_productivity_factor": 0.6}
    resp = _simulate(client, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH, overrides)
    assert resp.status_code == 200
    body = resp.json()

    by_field = {o["field"]: o for o in body["overrides"]}
    assert set(by_field) == set(overrides)
    for field, new_value in overrides.items():
        entry = by_field[field]
        assert entry["simulated_value"] == pytest.approx(new_value)
        assert entry["delta"] == pytest.approx(new_value - entry["original_value"])

    for task in ("significant_delay", "final_delay_days", "cost_overrun", "final_cost_overrun_pct"):
        assert body["simulated_predictions"][task]["model_used"] is not None
        assert body["baseline_predictions"][task]["model_used"] is not None


# --- TEST 9: mandatory disclaimer ---


def test_successful_simulation_always_includes_mandatory_disclaimer(client):
    resp = _simulate(client, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH, {"contractor_productivity_factor": 0.6})
    assert resp.status_code == 200
    assert resp.json()["simulation_disclaimer"] == SIMULATION_DISCLAIMER


def test_disclaimer_also_present_with_zero_overrides(client):
    resp = _simulate(client, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH, {})
    assert resp.status_code == 200
    assert resp.json()["simulation_disclaimer"] == SIMULATION_DISCLAIMER
    assert "synthetic" in resp.json()["synthetic_data_disclaimer"].lower()
