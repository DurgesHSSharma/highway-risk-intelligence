"""Phase 15 HTTP-contract tests for
GET /projects/{project_id}/decision-intelligence?reporting_month=YYYY-MM,
against the real running FastAPI app (via the session-scoped `client`
fixture in conftest.py) -- mirrors the fixture convention already used by
test_decision_support_api.py / test_portfolio_analytics_api.py.
"""

from __future__ import annotations

NON_TERMINAL_PROJECT_ID = "HRI-0006"
NON_TERMINAL_MONTH = "2022-12"

TERMINAL_PROJECT_ID = "HRI-0001"
TERMINAL_MONTH = "2024-03"

CRITICAL_PROJECT_ID = "HRI-0328"
CRITICAL_MONTH = "2025-08"


def _url(project_id: str) -> str:
    return f"/projects/{project_id}/decision-intelligence"


# --- endpoint exists and returns the full expected shape ---


def test_endpoint_exists_and_returns_200_for_valid_non_terminal_request(client, _phase14_batch_scoring):
    resp = client.get(_url(NON_TERMINAL_PROJECT_ID), params={"reporting_month": NON_TERMINAL_MONTH})
    assert resp.status_code == 200
    body = resp.json()

    for key in (
        "project", "prediction_status", "predictions", "risk_summary", "risk_drivers",
        "shap_skipped_reason", "documentary_evidence", "potential_inconsistencies", "scenario",
        "scenario_skipped_reason", "evidence_strength", "evidence_strength_basis",
        "risk_positioning", "peer_context", "driver_alignment", "recommended_reviews", "disclaimers",
    ):
        assert key in body, f"missing top-level key: {key}"


def test_valid_non_terminal_project_response_content(client, _phase14_batch_scoring):
    resp = client.get(_url(NON_TERMINAL_PROJECT_ID), params={"reporting_month": NON_TERMINAL_MONTH})
    body = resp.json()

    assert body["prediction_status"] == "model_prediction"
    assert body["project"]["is_terminal_snapshot"] is False
    assert len(body["risk_drivers"]) == 4
    assert body["risk_positioning"]["status"] == "ok"
    assert set(body["peer_context"].keys()) == {"state", "project_type", "contractor"}
    assert len(body["driver_alignment"]) == 4


def test_valid_terminal_project_response_content(client, _phase14_batch_scoring):
    resp = client.get(_url(TERMINAL_PROJECT_ID), params={"reporting_month": TERMINAL_MONTH})
    assert resp.status_code == 200
    body = resp.json()

    assert body["prediction_status"] == "actual_outcome"
    assert body["risk_drivers"] == []
    assert body["shap_skipped_reason"] is not None
    assert body["scenario"] is None
    assert body["scenario_skipped_reason"] is not None
    # Portfolio context (based on the cache, not the requested month) can
    # still render for a terminal request.
    assert body["risk_positioning"]["status"] == "ok"
    for a in body["driver_alignment"]:
        assert a["live_top_driver"] is None
        assert a["agreement"] is None


# --- error handling ---


def test_unknown_project_returns_404(client):
    resp = client.get(_url("NOT-A-REAL-PROJECT"), params={"reporting_month": "2022-12"})
    assert resp.status_code == 404


def test_unknown_reporting_month_returns_404(client):
    resp = client.get(_url(NON_TERMINAL_PROJECT_ID), params={"reporting_month": "1999-01"})
    assert resp.status_code == 404


def test_missing_reporting_month_param_returns_422(client):
    resp = client.get(_url(NON_TERMINAL_PROJECT_ID))
    assert resp.status_code == 422


# --- non-comparable cost-task presentation ---


def test_non_comparable_cost_tasks_carry_explicit_note(client, _phase14_batch_scoring):
    resp = client.get(_url(NON_TERMINAL_PROJECT_ID), params={"reporting_month": NON_TERMINAL_MONTH})
    body = resp.json()
    by_task = {a["task_key"]: a for a in body["driver_alignment"]}

    for task_key in ("cost_overrun", "final_cost_overrun_pct"):
        entry = by_task[task_key]
        assert entry["matches_serving_model"] is False
        assert entry["comparable"] is False
        assert entry["not_comparable_note"] == "Not a meaningful comparison -- different model family."

    for task_key in ("significant_delay", "final_delay_days"):
        entry = by_task[task_key]
        assert entry["comparable"] is True
        assert entry["not_comparable_note"] is None


# --- risk positioning / percentile / disclaimer presence ---


def test_risk_positioning_carries_percentile_definition_and_disclaimer(client, _phase14_batch_scoring):
    resp = client.get(_url(NON_TERMINAL_PROJECT_ID), params={"reporting_month": NON_TERMINAL_MONTH})
    body = resp.json()
    rp = body["risk_positioning"]

    assert rp["percentile_definition"]
    assert "percentile" in rp["percentile_definition"].lower()
    assert rp["portfolio_relative_disclaimer"]
    assert "PORTFOLIO-RELATIVE" in rp["portfolio_relative_disclaimer"]
    assert "not an official nhai" in rp["portfolio_relative_disclaimer"].lower()
    assert rp["current_risk_basis_note"]
    assert "synthetic corpus" in rp["current_risk_basis_note"].lower()


def test_percentile_within_bounds(client, _phase14_batch_scoring):
    resp = client.get(_url(CRITICAL_PROJECT_ID), params={"reporting_month": CRITICAL_MONTH})
    body = resp.json()
    assert 0.0 <= body["risk_positioning"]["percentile"] <= 100.0


# --- peer group context ---


def test_peer_state_context_present(client, _phase14_batch_scoring):
    resp = client.get(_url(NON_TERMINAL_PROJECT_ID), params={"reporting_month": NON_TERMINAL_MONTH})
    body = resp.json()
    state_entry = body["peer_context"]["state"]
    assert state_entry["status"] == "ok"
    assert state_entry["historical"] is not None
    assert state_entry["historical"]["project_count"] > 0


def test_peer_project_type_context_present(client, _phase14_batch_scoring):
    resp = client.get(_url(NON_TERMINAL_PROJECT_ID), params={"reporting_month": NON_TERMINAL_MONTH})
    body = resp.json()
    entry = body["peer_context"]["project_type"]
    assert entry["status"] == "ok"
    assert entry["historical"] is not None


def test_peer_contractor_context_present(client, _phase14_batch_scoring):
    resp = client.get(_url(NON_TERMINAL_PROJECT_ID), params={"reporting_month": NON_TERMINAL_MONTH})
    body = resp.json()
    entry = body["peer_context"]["contractor"]
    assert entry["status"] == "ok"
    assert entry["historical"] is not None


# --- recommendations ---


def test_recommended_reviews_have_full_traceability(client, _phase14_batch_scoring):
    resp = client.get(_url(CRITICAL_PROJECT_ID), params={"reporting_month": CRITICAL_MONTH})
    body = resp.json()
    assert len(body["recommended_reviews"]) > 0
    for rec in body["recommended_reviews"]:
        assert rec["text"]
        assert rec["basis_type"]
        assert rec["basis_detail"]


def test_recommended_reviews_include_portfolio_context_family_for_critical_project(client, _phase14_batch_scoring):
    resp = client.get(_url(CRITICAL_PROJECT_ID), params={"reporting_month": CRITICAL_MONTH})
    body = resp.json()
    basis_types = {r["basis_type"] for r in body["recommended_reviews"]}
    assert "portfolio_context" in basis_types


def test_recommended_reviews_capped_at_eight(client, _phase14_batch_scoring):
    resp = client.get(_url(CRITICAL_PROJECT_ID), params={"reporting_month": CRITICAL_MONTH})
    body = resp.json()
    assert len(body["recommended_reviews"]) <= 8


# --- existing endpoints unaffected (spot check per master-prompt section 40) ---


def test_existing_risk_summary_endpoint_still_works(client, _phase14_batch_scoring):
    resp = client.get(f"/projects/{NON_TERMINAL_PROJECT_ID}/risk-summary", params={"reporting_month": NON_TERMINAL_MONTH})
    assert resp.status_code == 200


def test_existing_portfolio_analytics_endpoint_still_works(client, _phase14_batch_scoring):
    resp = client.get("/analytics/portfolio")
    assert resp.status_code == 200


def test_existing_predict_endpoint_still_works(client):
    resp = client.get(f"/projects/{NON_TERMINAL_PROJECT_ID}/predict", params={"reporting_month": NON_TERMINAL_MONTH})
    assert resp.status_code == 200
