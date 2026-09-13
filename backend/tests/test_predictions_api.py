"""Phase 6 prediction endpoint tests (brief section 22, items 1-14)."""

from __future__ import annotations

NON_TERMINAL_PROJECT_ID = "HRI-0006"
NON_TERMINAL_MONTH = "2022-12"

TERMINAL_PROJECT_ID = "HRI-0001"
TERMINAL_MONTH = "2024-03"

UNKNOWN_PROJECT_ID = "HRI-9999"


def _predict(client, project_id: str, reporting_month: str):
    return client.get(f"/projects/{project_id}/predict", params={"reporting_month": reporting_month})


def test_unknown_project_returns_404(client):
    resp = _predict(client, UNKNOWN_PROJECT_ID, NON_TERMINAL_MONTH)
    assert resp.status_code == 404


def test_unknown_reporting_month_returns_404(client):
    resp = _predict(client, NON_TERMINAL_PROJECT_ID, "1999-01")
    assert resp.status_code == 404


def test_non_terminal_snapshot_returns_all_four_predictions(client):
    resp = _predict(client, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH)
    assert resp.status_code == 200
    body = resp.json()

    assert body["prediction_status"] == "model_prediction"
    assert body["is_model_prediction"] is True
    assert body["is_terminal_snapshot"] is False

    for task in ("significant_delay", "final_delay_days", "cost_overrun", "final_cost_overrun_pct"):
        assert body[task]["model_used"] is not None, f"{task} missing model_used"


def test_correct_model_name_per_task_matches_phase5_report(client):
    resp = _predict(client, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH)
    body = resp.json()

    # Verified against docs/MODEL_COMPARISON_REPORT.md section 8.
    assert body["significant_delay"]["model_used"] == "random_forest"
    assert body["final_delay_days"]["model_used"] == "xgboost"
    assert body["cost_overrun"]["model_used"] == "logistic_regression_baseline"
    assert body["final_cost_overrun_pct"]["model_used"] == "linear_regression_baseline"


def test_classification_tasks_return_probabilities(client):
    resp = _predict(client, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH)
    body = resp.json()

    sig = body["significant_delay"]
    assert sig["predicted_class"] in (0, 1)
    assert 0.0 <= sig["probability_of_significant_delay"] <= 1.0

    cost = body["cost_overrun"]
    assert cost["predicted_class"] in (0, 1)
    assert 0.0 <= cost["probability_of_cost_overrun"] <= 1.0


def test_regression_tasks_return_numeric_predictions(client):
    resp = _predict(client, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH)
    body = resp.json()

    assert isinstance(body["final_delay_days"]["predicted_final_delay_days"], (int, float))
    assert isinstance(body["final_cost_overrun_pct"]["predicted_final_cost_overrun_pct"], (int, float))


def test_non_terminal_response_carries_synthetic_disclaimer(client):
    resp = _predict(client, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH)
    body = resp.json()
    disclaimer = body["synthetic_data_disclaimer"].lower()
    assert "synthetic" in disclaimer
    assert "real nhai" in disclaimer or "not" in disclaimer


def test_terminal_snapshot_does_not_run_a_model(client):
    resp = _predict(client, TERMINAL_PROJECT_ID, TERMINAL_MONTH)
    assert resp.status_code == 200
    body = resp.json()

    assert body["is_model_prediction"] is False
    assert body["prediction_status"] == "actual_outcome"
    for task in ("significant_delay", "final_delay_days", "cost_overrun", "final_cost_overrun_pct"):
        assert body[task]["model_used"] is None
        assert body[task]["predicted_class"] is None if "class" in body[task] else True


def test_terminal_snapshot_returns_recorded_actual_outcomes(client):
    resp = _predict(client, TERMINAL_PROJECT_ID, TERMINAL_MONTH)
    body = resp.json()

    assert body["final_delay_days"]["actual_value"] == 0
    assert body["significant_delay"]["actual_value"] == 0
    assert body["final_cost_overrun_pct"]["actual_value"] == 5.11
    assert body["cost_overrun"]["actual_value"] == 0


def test_terminal_response_clearly_labelled_as_actual_outcome(client):
    resp = _predict(client, TERMINAL_PROJECT_ID, TERMINAL_MONTH)
    body = resp.json()
    assert "terminal" in body["explanation"].lower()
    assert "actual" in body["explanation"].lower() or "recorded" in body["explanation"].lower()
    assert body["is_terminal_snapshot"] is True


def test_terminal_response_still_carries_a_synthetic_data_notice(client):
    resp = _predict(client, TERMINAL_PROJECT_ID, TERMINAL_MONTH)
    body = resp.json()
    assert "synthetic" in body["synthetic_data_disclaimer"].lower()
