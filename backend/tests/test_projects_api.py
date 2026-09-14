"""Phase 6 CRUD endpoint tests (brief section 21, items 7-13).

Phase 13 adds server-side search tests (`q` param) below the original
Phase 6 tests.
"""

from __future__ import annotations

import pandas as pd
import pytest

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


def test_invalid_pagination_page_zero_returns_422(client):
    resp = client.get("/projects", params={"page": 0})
    assert resp.status_code == 422


def test_invalid_pagination_page_size_zero_returns_422(client):
    resp = client.get("/projects", params={"page_size": 0})
    assert resp.status_code == 422


def test_invalid_pagination_page_size_over_max_returns_422(client):
    resp = client.get("/projects", params={"page_size": 1000})
    assert resp.status_code == 422


def test_no_search_param_preserves_existing_listing_behavior(client):
    """Backward compatibility: a call with no `q` behaves exactly like the
    pre-Phase-13 endpoint (item 17 of the brief's test list)."""
    resp = client.get("/projects", params={"page": 1, "page_size": 10})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 400
    assert len(body["items"]) == 10


def test_search_exact_project_id_match(client):
    resp = client.get("/projects", params={"q": KNOWN_PROJECT_ID})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["project_id"] == KNOWN_PROJECT_ID


def test_search_partial_project_id_match(client):
    resp = client.get("/projects", params={"q": "HRI-000", "page_size": 100})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 9  # HRI-0001..HRI-0009 at minimum
    assert all("HRI-000" in p["project_id"] for p in body["items"])


def test_search_project_name_match(client):
    known = client.get(f"/projects/{KNOWN_PROJECT_ID}").json()
    name_fragment = known["project_name"].split(" ")[0]

    resp = client.get("/projects", params={"q": name_fragment, "page_size": 100})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    assert any(p["project_id"] == KNOWN_PROJECT_ID for p in body["items"])


def test_search_highway_number_match(client):
    known = client.get(f"/projects/{KNOWN_PROJECT_ID}").json()
    highway_fragment = known["highway_number"][:4]

    resp = client.get("/projects", params={"q": highway_fragment, "page_size": 100})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    assert all(highway_fragment.lower() in p["highway_number"].lower() for p in body["items"])


def test_search_state_match(client):
    resp = client.get("/projects", params={"q": "kerala", "page_size": 100})
    assert resp.status_code == 200
    body = resp.json()
    raw = pd.read_csv(DATASET_CSV_PATH)
    expected_count = raw.drop_duplicates("project_id").query("state == 'Kerala'").shape[0]
    assert body["total"] == expected_count
    assert all(p["state"] == "Kerala" for p in body["items"])


def test_search_contractor_match(client):
    known = client.get(f"/projects/{KNOWN_PROJECT_ID}").json()
    contractor = known["contractor"]
    if not contractor:
        pytest.skip(f"{KNOWN_PROJECT_ID} has no recorded contractor.")
    fragment = contractor.split(" ")[0]

    resp = client.get("/projects", params={"q": fragment, "page_size": 100})
    assert resp.status_code == 200
    body = resp.json()
    assert any(p["project_id"] == KNOWN_PROJECT_ID for p in body["items"])


def test_search_is_case_insensitive(client):
    lower = client.get("/projects", params={"q": KNOWN_PROJECT_ID.lower()}).json()
    upper = client.get("/projects", params={"q": KNOWN_PROJECT_ID.upper()}).json()
    mixed = client.get("/projects", params={"q": "hri-0001"}).json()
    assert lower["total"] == upper["total"] == mixed["total"] == 1


def test_search_handles_surrounding_whitespace(client):
    padded = client.get("/projects", params={"q": f"  {KNOWN_PROJECT_ID}  "}).json()
    clean = client.get("/projects", params={"q": KNOWN_PROJECT_ID}).json()
    assert padded["total"] == clean["total"] == 1


def test_search_whitespace_only_behaves_like_no_search(client):
    resp = client.get("/projects", params={"q": "   ", "page_size": 10})
    assert resp.status_code == 200
    assert resp.json()["total"] == 400


def test_empty_search_string_behaves_like_no_search(client):
    resp = client.get("/projects", params={"q": "", "page_size": 10})
    assert resp.status_code == 200
    assert resp.json()["total"] == 400


def test_search_no_result_returns_empty_response(client):
    resp = client.get("/projects", params={"q": "no-such-project-xyz-zzz"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["items"] == []


def test_search_combined_with_state_filter(client):
    resp = client.get("/projects", params={"q": "Expressway", "state": "Kerala", "page_size": 100})
    assert resp.status_code == 200
    body = resp.json()
    assert all(p["state"] == "Kerala" for p in body["items"])
    for p in body["items"]:
        assert (
            "expressway" in p["project_id"].lower()
            or "expressway" in p["project_name"].lower()
            or "expressway" in p["highway_number"].lower()
            or "expressway" in p["project_type"].lower()
            or (p["contractor"] and "expressway" in p["contractor"].lower())
        )


def test_search_combined_with_project_type_filter(client):
    raw = pd.read_csv(DATASET_CSV_PATH)
    a_type = raw["project_type"].iloc[0]

    resp = client.get("/projects", params={"q": "HRI-0", "project_type": a_type, "page_size": 100})
    assert resp.status_code == 200
    body = resp.json()
    assert all(p["project_type"] == a_type for p in body["items"])
    assert all("hri-0" in p["project_id"].lower() for p in body["items"])


def test_search_combined_with_status_filter(client):
    resp = client.get("/projects", params={"q": "HRI-000", "project_status": "Completed", "page_size": 100})
    assert resp.status_code == 200
    body = resp.json()
    assert all(p["current_status"] == "Completed" for p in body["items"])
    assert all("hri-000" in p["project_id"].lower() for p in body["items"])


def test_search_is_paginated_after_filtering(client):
    full = client.get("/projects", params={"q": "HRI-00", "page_size": 100}).json()
    assert full["total"] > 10

    page1 = client.get("/projects", params={"q": "HRI-00", "page": 1, "page_size": 5}).json()
    page2 = client.get("/projects", params={"q": "HRI-00", "page": 2, "page_size": 5}).json()
    assert page1["total"] == page2["total"] == full["total"]
    assert len(page1["items"]) == 5
    assert len(page2["items"]) == 5
    ids1 = {p["project_id"] for p in page1["items"]}
    ids2 = {p["project_id"] for p in page2["items"]}
    assert ids1.isdisjoint(ids2)


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
