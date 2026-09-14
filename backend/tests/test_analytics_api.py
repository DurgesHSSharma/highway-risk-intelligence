"""Phase 12 tests for the new read-only GET /analytics/summary endpoint.

Asserts internal consistency (group counts sum to the total) rather than
hard-coding derived numbers that could silently drift from the real
dataset, plus the two known, already-disclosed data properties from
Phase 6/memory: every project's *current* status is "Completed" (the
synthetic generator always simulates a project through to completion),
and every project has exactly one terminal snapshot.
"""

from __future__ import annotations


def test_summary_returns_200(client):
    resp = client.get("/analytics/summary")
    assert resp.status_code == 200


def test_total_projects_matches_known_dataset_size(client):
    resp = client.get("/analytics/summary")
    body = resp.json()
    assert body["total_projects"] == 400


def test_status_counts_sum_to_total_and_are_all_completed(client):
    resp = client.get("/analytics/summary")
    body = resp.json()
    assert sum(body["status_counts"].values()) == body["total_projects"]
    # Known, disclosed data property (docs/API_AND_DATABASE.md): every
    # project's synthetic trajectory runs to completion, so its *latest*
    # snapshot status is always "Completed".
    assert body["status_counts"] == {"Completed": body["total_projects"]}


def test_state_and_project_type_counts_sum_to_total(client):
    resp = client.get("/analytics/summary")
    body = resp.json()
    assert sum(body["state_counts"].values()) == body["total_projects"]
    assert sum(body["project_type_counts"].values()) == body["total_projects"]


def test_outcome_counts_are_within_valid_bounds(client):
    resp = client.get("/analytics/summary")
    body = resp.json()
    total = body["total_projects"]
    assert 0 <= body["significant_delay_count"] <= total
    assert 0 <= body["cost_overrun_count"] <= total
    assert body["avg_final_delay_days"] >= 0
    assert isinstance(body["avg_final_cost_overrun_pct"], float)


def test_disclaimer_present_and_not_overridden(client):
    resp = client.get("/analytics/summary")
    body = resp.json()
    assert "SYNTHETIC" in body["synthetic_data_disclaimer"]
    assert "recorded final outcomes" in body["synthetic_data_disclaimer"]
