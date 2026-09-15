"""Phase 14 HTTP-contract tests for GET /analytics/portfolio,
/analytics/risk-projects, /analytics/segments, /analytics/drivers,
/analytics/trends. Uses the real committed dataset via the shared `client`
fixture -- never a mocked backend.
"""

from __future__ import annotations


def test_portfolio_overview_200_and_structurally_separated(client):
    resp = client.get("/analytics/portfolio")
    assert resp.status_code == 200
    body = resp.json()

    assert "historical" in body and "predicted" in body
    # Never one ambiguous blended field: historical and predicted are
    # always separate, differently-shaped objects.
    assert body["historical"].keys() != body["predicted"].keys()
    assert body["historical"]["label"] == "HISTORICAL / ACTUAL"
    assert body["predicted"]["label"] == "CURRENT MODEL-PREDICTED"


def test_portfolio_overview_historical_matches_known_dataset_stats(client):
    resp = client.get("/analytics/portfolio")
    body = resp.json()
    hist = body["historical"]
    # Known values (Phase 12 memory / independently re-derived in
    # test_independent_math_verification.py): every one of the 400 projects
    # is terminal, 197 flagged significant_delay, 153 flagged cost_overrun.
    assert hist["completed_project_count"] == 400
    assert hist["significant_delay_count"] == 197
    assert hist["cost_overrun_count"] == 153
    assert hist["significant_delay_rate"] == 197 / 400
    assert hist["cost_overrun_rate"] == 153 / 400


def test_portfolio_overview_predicted_is_ok_when_cache_populated(client, _phase14_batch_scoring):
    resp = client.get("/analytics/portfolio")
    body = resp.json()
    predicted = body["predicted"]
    assert predicted["status"] == "ok"
    assert predicted["scored_project_count"] == 400
    assert predicted["computed_at"] is not None
    assert set(predicted["risk_level_counts"]) <= {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
    assert sum(predicted["risk_level_counts"].values()) == 400


def test_portfolio_overview_risk_distribution_has_all_four_tasks(client):
    resp = client.get("/analytics/portfolio")
    tasks = {d["task_key"] for d in resp.json()["risk_distribution"]}
    assert tasks == {"significant_delay", "final_delay_days", "cost_overrun", "final_cost_overrun_pct"}


def test_portfolio_overview_executive_insights_are_nonempty_strings(client):
    resp = client.get("/analytics/portfolio")
    insights = resp.json()["executive_insights"]
    assert len(insights) > 0
    for insight in insights:
        assert isinstance(insight, str) and len(insight) > 0
        lowered = insight.lower()
        for banned in ("causes", "guarantees", "will definitely", "responsible for"):
            assert banned not in lowered


def test_risk_projects_sorted_deterministically_desc_by_score(client):
    resp = client.get("/analytics/risk-projects", params={"limit": 50})
    items = resp.json()["items"]
    scores = [it["risk_score"] for it in items]
    assert scores == sorted(scores, reverse=True)


def test_risk_projects_pagination_is_consistent(client):
    page1 = client.get("/analytics/risk-projects", params={"limit": 10, "offset": 0}).json()
    page2 = client.get("/analytics/risk-projects", params={"limit": 10, "offset": 10}).json()
    ids1 = {it["project_id"] for it in page1["items"]}
    ids2 = {it["project_id"] for it in page2["items"]}
    assert ids1.isdisjoint(ids2)
    assert page1["total"] == page2["total"] == 400


def test_risk_projects_filter_by_risk_level(client):
    resp = client.get("/analytics/risk-projects", params={"risk_level": "CRITICAL", "limit": 100})
    body = resp.json()
    assert body["total"] > 0
    for item in body["items"]:
        assert item["risk_level"] == "CRITICAL"


def test_risk_projects_filter_by_state(client):
    resp = client.get("/analytics/risk-projects", params={"state": "Punjab", "limit": 100})
    body = resp.json()
    for item in body["items"]:
        assert item["state"] == "Punjab"


def test_risk_projects_invalid_risk_level_is_422(client):
    resp = client.get("/analytics/risk-projects", params={"risk_level": "NOT_A_LEVEL"})
    assert resp.status_code == 422


def test_segments_state_dimension_flags_small_states(client):
    resp = client.get("/analytics/segments", params={"dimension": "state"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["min_sample_threshold"] == 15
    by_state = {e["value"]: e for e in body["entries"]}
    # Real measured counts (see docs/ADVANCED_ANALYTICS.md): Punjab has 11
    # projects (< 15, flagged), Madhya Pradesh has 31 (>= 15, not flagged).
    assert by_state["Punjab"]["small_sample"] is True
    assert by_state["Madhya Pradesh"]["small_sample"] is False


def test_segments_contractor_dimension_uses_data_driven_threshold_not_15(client):
    resp = client.get("/analytics/segments", params={"dimension": "contractor"})
    body = resp.json()
    # Inspected corpus fact: a flat 15-project minimum would leave exactly 1
    # of 50 contractors usable -- the brief requires inspecting the corpus
    # rather than blindly applying 15, so this must not be 15.
    assert body["min_sample_threshold"] == 8
    assert body["min_sample_threshold"] != 15
    small_sample_count = sum(1 for e in body["entries"] if e["small_sample"])
    not_small_sample_count = len(body["entries"]) - small_sample_count
    assert not_small_sample_count > 1  # more than just the single top contractor


def test_segments_never_blend_historical_and_predicted_in_one_field(client):
    resp = client.get("/analytics/segments", params={"dimension": "project_type"})
    for entry in resp.json()["entries"]:
        if entry["historical"] is not None and entry["predicted"] is not None:
            assert set(entry["historical"]) != set(entry["predicted"])


def test_segments_invalid_dimension_is_422(client):
    resp = client.get("/analytics/segments", params={"dimension": "not_a_dimension"})
    assert resp.status_code == 422


def test_drivers_returns_all_four_tasks_with_serving_model_flag(client):
    resp = client.get("/analytics/drivers")
    assert resp.status_code == 200
    tasks = {t["task_key"]: t for t in resp.json()["tasks"]}
    assert set(tasks) == {"significant_delay", "final_delay_days", "cost_overrun", "final_cost_overrun_pct"}
    # Known, disclosed Phase 5 characteristic: the saved global SHAP explains
    # the tree model family for every task, which matches the ACTUAL serving
    # model only for the two delay tasks (RF/XGBoost), not the two cost
    # tasks (served by the Phase 4 linear baselines).
    assert tasks["significant_delay"]["matches_serving_model"] is True
    assert tasks["final_delay_days"]["matches_serving_model"] is True
    assert tasks["cost_overrun"]["matches_serving_model"] is False
    assert tasks["final_cost_overrun_pct"]["matches_serving_model"] is False


def test_trends_historical_and_predicted_are_structurally_separate(client):
    resp = client.get("/analytics/trends")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body["historical"][0]) != set(body["predicted"][0])
    periods = [p["period"] for p in body["historical"]]
    assert periods == sorted(periods)


def test_trends_flags_thin_years_as_small_sample(client, _phase14_batch_scoring):
    resp = client.get("/analytics/trends")
    predicted = {p["period"]: p for p in resp.json()["predicted"]}
    # Real measured coverage (see docs/ADVANCED_ANALYTICS.md): 2019 has only
    # 1 eligible project, 2024 has 78 -- so 2019 must be flagged, 2024 not.
    assert predicted["2019"]["small_sample"] is True
    assert predicted["2024"]["small_sample"] is False
