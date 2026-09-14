"""Phase 11 (REPAIRED) HTTP contract tests:
GET /projects/{project_id}/risk-summary?reporting_month=YYYY-MM.
Mirrors the Phase 10 `test_simulation_api.py` fixtures (same real
project/snapshot ids).
"""

from __future__ import annotations

NON_TERMINAL_PROJECT_ID = "HRI-0006"
NON_TERMINAL_MONTH = "2022-12"

TERMINAL_PROJECT_ID = "HRI-0001"
TERMINAL_MONTH = "2024-03"

UNKNOWN_PROJECT_ID = "HRI-9999"


def _risk_summary(client, project_id: str, reporting_month: str):
    return client.get(
        f"/projects/{project_id}/risk-summary",
        params={"reporting_month": reporting_month},
    )


# --- exact route/method contract ---


def test_exact_get_risk_summary_route_exists(client):
    resp = _risk_summary(client, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH)
    assert resp.status_code == 200


def test_old_post_decision_support_route_no_longer_exists(client):
    resp = client.post(
        f"/projects/{NON_TERMINAL_PROJECT_ID}/decision-support",
        params={"reporting_month": NON_TERMINAL_MONTH},
    )
    assert resp.status_code in (404, 405)


def test_risk_summary_requires_no_request_body(client):
    """A plain GET with no `json=`/body at all must succeed -- the earlier
    POST design required a body-bearing request; this endpoint must not."""
    resp = client.get(
        f"/projects/{NON_TERMINAL_PROJECT_ID}/risk-summary",
        params={"reporting_month": NON_TERMINAL_MONTH},
    )
    assert resp.status_code == 200


# --- 404s (consistent with /predict and /simulate) ---


def test_unknown_project_returns_404(client):
    resp = _risk_summary(client, UNKNOWN_PROJECT_ID, NON_TERMINAL_MONTH)
    assert resp.status_code == 404


def test_unknown_reporting_month_returns_404(client):
    resp = _risk_summary(client, NON_TERMINAL_PROJECT_ID, "1999-01")
    assert resp.status_code == 404


# --- non-terminal valid response ---


def test_non_terminal_valid_response_full_schema(client):
    resp = _risk_summary(client, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH)
    assert resp.status_code == 200
    body = resp.json()

    for key in (
        "project",
        "prediction_status",
        "predictions",
        "risk_summary",
        "risk_drivers",
        "shap_skipped_reason",
        "documentary_evidence",
        "potential_inconsistencies",
        "scenario",
        "scenario_skipped_reason",
        "recommended_reviews",
        "evidence_strength",
        "evidence_strength_basis",
        "disclaimers",
    ):
        assert key in body, f"missing top-level key: {key}"

    assert body["project"]["is_terminal_snapshot"] is False
    assert body["prediction_status"] == "model_prediction"
    assert body["shap_skipped_reason"] is None
    assert body["scenario"] is not None
    assert body["scenario_skipped_reason"] is None

    for task in ("significant_delay", "final_delay_days", "cost_overrun", "final_cost_overrun_pct"):
        assert task in body["predictions"]

    assert len(body["risk_drivers"]) == 4
    for d in body["risk_drivers"]:
        assert d["explainer_type"] in ("TreeExplainer", "LinearExplainer")
        assert len(d["top_drivers"]) == 5
        for f in d["top_drivers"]:
            assert set(f.keys()) >= {"rank", "feature", "shap_value", "direction", "explanation"}

    # Cost tasks must be explained via LinearExplainer, not TreeExplainer --
    # the exact bug this repair fixes.
    by_task = {d["task_key"]: d for d in body["risk_drivers"]}
    assert by_task["cost_overrun"]["explainer_type"] == "LinearExplainer"
    assert by_task["final_cost_overrun_pct"]["explainer_type"] == "LinearExplainer"
    assert by_task["significant_delay"]["explainer_type"] == "TreeExplainer"
    assert by_task["final_delay_days"]["explainer_type"] == "TreeExplainer"

    assert body["evidence_strength"] in (
        "high evidence support",
        "moderate evidence support",
        "limited evidence support",
    )


# --- terminal snapshot: 200, not 422, with explicit skip reasons ---


def test_terminal_snapshot_returns_200_with_actual_outcome(client):
    resp = _risk_summary(client, TERMINAL_PROJECT_ID, TERMINAL_MONTH)
    assert resp.status_code == 200
    body = resp.json()

    assert body["project"]["is_terminal_snapshot"] is True
    assert body["prediction_status"] == "actual_outcome"
    assert body["predictions"]["significant_delay"]["actual_value"] is not None
    assert body["predictions"]["significant_delay"]["predicted_class"] is None

    assert body["risk_drivers"] == []
    assert body["shap_skipped_reason"] is not None
    assert "terminal" in body["shap_skipped_reason"].lower()

    assert body["scenario"] is None
    assert body["scenario_skipped_reason"] is not None
    assert "terminal" in body["scenario_skipped_reason"].lower()

    # Evidence/inconsistencies sections still present (may or may not be
    # empty, but the keys exist and are valid lists).
    assert isinstance(body["documentary_evidence"], list)
    assert len(body["documentary_evidence"]) > 0
    assert isinstance(body["potential_inconsistencies"], list)


# --- mandatory disclaimers always present ---


def test_mandatory_disclaimers_always_present(client):
    resp = _risk_summary(client, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH)
    assert resp.status_code == 200
    disclaimers = resp.json()["disclaimers"]
    for key in (
        "ml_limitation",
        "causality_limitation",
        "scenario_limitation",
        "evidence_limitation",
        "inconsistency_limitation",
        "system_identity",
        "synthetic_data_disclaimer",
    ):
        assert key in disclaimers
        assert isinstance(disclaimers[key], str)
        assert len(disclaimers[key]) > 20

    assert "nhai" in disclaimers["system_identity"].lower()
    assert "prototype" in disclaimers["system_identity"].lower()


def test_mandatory_disclaimers_present_on_terminal_response_too(client):
    resp = _risk_summary(client, TERMINAL_PROJECT_ID, TERMINAL_MONTH)
    assert resp.status_code == 200
    disclaimers = resp.json()["disclaimers"]
    assert len(disclaimers) == 7


# --- existing endpoints remain functional alongside the repaired router ---


def test_existing_predict_endpoint_still_works(client):
    resp = client.get(
        f"/projects/{NON_TERMINAL_PROJECT_ID}/predict", params={"reporting_month": NON_TERMINAL_MONTH}
    )
    assert resp.status_code == 200


def test_existing_simulate_endpoint_still_works(client):
    resp = client.post(
        f"/projects/{NON_TERMINAL_PROJECT_ID}/simulate",
        params={"reporting_month": NON_TERMINAL_MONTH},
        json={"contractor_productivity_factor": 0.6},
    )
    assert resp.status_code == 200


def test_existing_documents_search_still_works(client):
    resp = client.get("/documents/search", params={"q": "project delay"})
    assert resp.status_code == 200


def test_existing_inconsistencies_endpoint_still_works(client):
    resp = client.get("/documents/inconsistencies")
    assert resp.status_code == 200
