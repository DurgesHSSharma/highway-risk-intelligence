"""Phase 6 CRUD endpoint tests (brief section 21, items 7-13)."""

from __future__ import annotations

import pandas as pd

from app.config import REPO_ROOT

DATASET_CSV_PATH = REPO_ROOT / "data" / "synthetic" / "highway_project_snapshots.csv"

KNOWN_PROJECT_ID = "HRI-0001"
UNKNOWN_PROJECT_ID = "HRI-9999"
KNOWN_MONTH = "2023-04"
UNKNOWN_MONTH = "1999-01"


def test_get_known_project_returns_details(client):
    resp = client.get(f"/projects/{KNOWN_PROJECT_ID}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["project_id"] == KNOWN_PROJECT_ID
    assert body["state"] == "Kerala"
    assert body["current_status"] == "Completed"


def test_get_unknown_project_returns_404(client):
    resp = client.get(f"/projects/{UNKNOWN_PROJECT_ID}")
    assert resp.status_code == 404


def test_get_known_snapshot(client):
    resp = client.get(f"/projects/{KNOWN_PROJECT_ID}/snapshots/{KNOWN_MONTH}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["project_id"] == KNOWN_PROJECT_ID
    assert body["reporting_month"] == KNOWN_MONTH
    assert body["is_terminal_snapshot"] is False


def test_get_unknown_snapshot_month_returns_404(client):
    resp = client.get(f"/projects/{KNOWN_PROJECT_ID}/snapshots/{UNKNOWN_MONTH}")
    assert resp.status_code == 404


def test_get_snapshots_for_unknown_project_returns_404(client):
    resp = client.get(f"/projects/{UNKNOWN_PROJECT_ID}/snapshots")
    assert resp.status_code == 404


def test_snapshots_ordered_by_reporting_month_ascending(client):
    resp = client.get(f"/projects/{KNOWN_PROJECT_ID}/snapshots")
    assert resp.status_code == 200
    months = [s["reporting_month"] for s in resp.json()]
    assert months == sorted(months)
    assert len(months) == len(set(months))
    # Terminal row (project_status == Completed) must be the last one.
    assert resp.json()[-1]["is_terminal_snapshot"] is True


def test_pagination_returns_requested_page_size(client):
    resp = client.get("/projects", params={"page": 1, "page_size": 10})
    assert resp.status_code == 200
    body = resp.json()
    assert body["page"] == 1
    assert body["page_size"] == 10
    assert len(body["items"]) == 10
    assert body["total"] == 400


def test_pagination_second_page_has_different_items(client):
    page1 = client.get("/projects", params={"page": 1, "page_size": 5}).json()
    page2 = client.get("/projects", params={"page": 2, "page_size": 5}).json()
    ids1 = {p["project_id"] for p in page1["items"]}
    ids2 = {p["project_id"] for p in page2["items"]}
    assert ids1.isdisjoint(ids2)


def test_page_size_is_capped_at_max():
    from app.config import settings

    assert settings.max_page_size <= 100


def test_state_filter_returns_only_matching_projects(client):
    raw = pd.read_csv(DATASET_CSV_PATH)
    expected_count = raw.drop_duplicates("project_id").query("state == 'Kerala'").shape[0]

    resp = client.get("/projects", params={"state": "Kerala", "page_size": 100})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == expected_count
    assert all(p["state"] == "Kerala" for p in body["items"])


def test_project_type_filter_returns_only_matching_projects(client):
    raw = pd.read_csv(DATASET_CSV_PATH)
    a_type = raw["project_type"].iloc[0]
    expected_count = raw.drop_duplicates("project_id").query("project_type == @a_type").shape[0]

    resp = client.get("/projects", params={"project_type": a_type, "page_size": 100})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == expected_count
    assert all(p["project_type"] == a_type for p in body["items"])


def test_project_status_filter_matches_latest_snapshot_status(client):
    # Every project in this synthetic dataset is simulated through to
    # completion, so every project's *latest* snapshot is "Completed" --
    # see app/routers/projects.py::_current_status_subquery docstring.
    resp = client.get("/projects", params={"project_status": "Completed", "page_size": 100})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 400
    assert all(p["current_status"] == "Completed" for p in body["items"])

    resp_ongoing = client.get("/projects", params={"project_status": "Ongoing"})
    assert resp_ongoing.status_code == 200
    assert resp_ongoing.json()["total"] == 0
