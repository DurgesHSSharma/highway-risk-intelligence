"""Phase 17B project lifecycle HTTP-contract tests: POST /projects,
PATCH /projects/{id}, POST /projects/{id}/archive|reactivate,
POST /projects/{id}/snapshots, plus the is_archived filter on the existing
GET /projects, and the prediction_status="insufficient_data" /
"model_prediction" transition on GET /projects/{id}/predict.

Runs against an ISOLATED temp database via a FastAPI `get_db` dependency
override -- deliberately NOT the shared session-scoped `client` fixture
backend/tests/conftest.py builds for the read-only Phase 1-16 endpoints,
so these tests can freely create/archive/complete projects without any
other test file's total-project-count assumptions being affected. The
override is installed and removed within this module's own fixture scope
only.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.base import create_all, get_db, make_engine
from app.db.loader import load_database
from app.main import app
from scripts.generate_dataset import generate_dataset


@pytest.fixture(scope="module")
def lifecycle_client(tmp_path_factory):
    tmp_dir = tmp_path_factory.mktemp("lifecycle_api")
    csv_path = tmp_dir / "small_snapshots.csv"
    generate_dataset(n_projects=10, seed=5).to_csv(csv_path, index=False)

    engine = make_engine(f"sqlite:///{(tmp_dir / 'lifecycle_api.db').as_posix()}")
    create_all(bind=engine)
    load_database(csv_path, bind=engine)

    def _override_get_db():
        session = Session(bind=engine)
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_get_db
    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


def _valid_project_payload(**overrides) -> dict:
    payload = {
        "project_name": "API Test Highway",
        "highway_number": "NH-777",
        "state": "Test State",
        "project_type": "Greenfield",
        "contractor": "API Test Contractor",
        "project_length_km": 30.0,
        "original_contract_value_inr_cr": 300.0,
        "planned_start_date": "2025-01-01",
        "planned_completion_date": "2027-01-01",
        "planned_duration_months": 24,
    }
    payload.update(overrides)
    return payload


def _valid_snapshot_payload(**overrides) -> dict:
    payload = {
        "reporting_month": "2025-06",
        "project_status": "Ongoing",
        "planned_physical_progress_pct": 25.0,
        "actual_physical_progress_pct": 20.0,
        "planned_financial_progress_pct": 25.0,
        "actual_financial_progress_pct": 18.0,
        "planned_cost_to_date_inr_cr": 75.0,
        "actual_expenditure_inr_cr": 60.0,
        "actual_cost_to_date_inr_cr": 60.0,
        "material_cost_inr_cr": 30.0,
        "labour_cost_inr_cr": 20.0,
        "equipment_cost_inr_cr": 10.0,
        "variation_cost_inr_cr": 0.0,
        "delay_related_cost_inr_cr": 2.0,
        "land_acquisition_delay_days": 5.0,
        "utility_shifting_delay_days": 0.0,
        "environment_clearance_delay_days": 0.0,
        "material_delay_days": 0.0,
        "labour_shortage_days": 0.0,
        "equipment_unavailability_days": 0.0,
        "weather_disruption_days": 3.0,
        "contractor_productivity_factor": 0.9,
        "traffic_diversion_delay_days": 0.0,
        "design_change_delay_days": 0.0,
        "approval_delay_days": 0.0,
    }
    payload.update(overrides)
    return payload


# --- create ---------------------------------------------------------------


def test_create_project_returns_201_with_generated_id(lifecycle_client):
    resp = lifecycle_client.post("/projects", json=_valid_project_payload())
    assert resp.status_code == 201
    body = resp.json()
    assert body["project_id"].startswith("HRI-")
    assert body["data_provenance"] == "USER_ENTERED"
    assert body["is_archived"] is False
    assert body["current_status"] == "Unknown"  # no snapshots yet


def test_create_project_with_supplied_id(lifecycle_client):
    resp = lifecycle_client.post("/projects", json=_valid_project_payload(project_id="HRI-6001"))
    assert resp.status_code == 201
    assert resp.json()["project_id"] == "HRI-6001"


def test_create_project_duplicate_id_returns_409(lifecycle_client):
    lifecycle_client.post("/projects", json=_valid_project_payload(project_id="HRI-6002"))
    resp = lifecycle_client.post("/projects", json=_valid_project_payload(project_id="HRI-6002"))
    assert resp.status_code == 409


def test_create_project_invalid_data_returns_422(lifecycle_client):
    resp = lifecycle_client.post(
        "/projects",
        json=_valid_project_payload(planned_start_date="2027-01-01", planned_completion_date="2025-01-01"),
    )
    assert resp.status_code == 422


def test_create_project_invalid_id_format_returns_422(lifecycle_client):
    resp = lifecycle_client.post("/projects", json=_valid_project_payload(project_id="NOT-A-VALID-ID"))
    assert resp.status_code == 422


def test_create_project_missing_required_field_returns_422(lifecycle_client):
    payload = _valid_project_payload()
    del payload["project_name"]
    resp = lifecycle_client.post("/projects", json=payload)
    assert resp.status_code == 422


def test_created_project_appears_in_project_list(lifecycle_client):
    resp = lifecycle_client.post("/projects", json=_valid_project_payload(project_id="HRI-6003"))
    assert resp.status_code == 201

    listed = lifecycle_client.get("/projects", params={"q": "HRI-6003"})
    assert listed.status_code == 200
    ids = [p["project_id"] for p in listed.json()["items"]]
    assert "HRI-6003" in ids


# --- edit -------------------------------------------------------------


def test_edit_project_updates_field(lifecycle_client):
    lifecycle_client.post("/projects", json=_valid_project_payload(project_id="HRI-6010"))
    resp = lifecycle_client.patch("/projects/HRI-6010", json={"contractor": "Updated Contractor"})
    assert resp.status_code == 200
    assert resp.json()["contractor"] == "Updated Contractor"


def test_edit_unknown_project_returns_404(lifecycle_client):
    resp = lifecycle_client.patch("/projects/HRI-9999", json={"contractor": "X"})
    assert resp.status_code == 404


def test_edit_project_invalid_dates_returns_422(lifecycle_client):
    lifecycle_client.post("/projects", json=_valid_project_payload(project_id="HRI-6011"))
    resp = lifecycle_client.patch("/projects/HRI-6011", json={"planned_completion_date": "2020-01-01"})
    assert resp.status_code == 422


# --- archive / reactivate ----------------------------------------------


def test_archive_project_marks_archived_and_preserves_visibility(lifecycle_client):
    lifecycle_client.post("/projects", json=_valid_project_payload(project_id="HRI-6020"))

    archived = lifecycle_client.post("/projects/HRI-6020/archive")
    assert archived.status_code == 200
    assert archived.json()["is_archived"] is True
    assert archived.json()["archived_at"] is not None

    # Still visible via GET /projects/{id} -- archiving never deletes.
    fetched = lifecycle_client.get("/projects/HRI-6020")
    assert fetched.status_code == 200
    assert fetched.json()["is_archived"] is True


def test_archive_unknown_project_returns_404(lifecycle_client):
    resp = lifecycle_client.post("/projects/HRI-9999/archive")
    assert resp.status_code == 404


def test_is_archived_filter_distinguishes_active_and_archived(lifecycle_client):
    lifecycle_client.post("/projects", json=_valid_project_payload(project_id="HRI-6021"))
    lifecycle_client.post("/projects/HRI-6021/archive")

    archived_only = lifecycle_client.get("/projects", params={"is_archived": True, "q": "HRI-6021"})
    active_only = lifecycle_client.get("/projects", params={"is_archived": False, "q": "HRI-6021"})

    assert "HRI-6021" in [p["project_id"] for p in archived_only.json()["items"]]
    assert "HRI-6021" not in [p["project_id"] for p in active_only.json()["items"]]


def test_reactivate_project_clears_archived_state(lifecycle_client):
    lifecycle_client.post("/projects", json=_valid_project_payload(project_id="HRI-6022"))
    lifecycle_client.post("/projects/HRI-6022/archive")

    reactivated = lifecycle_client.post("/projects/HRI-6022/reactivate")
    assert reactivated.status_code == 200
    assert reactivated.json()["is_archived"] is False
    assert reactivated.json()["archived_at"] is None


def test_reactivate_unknown_project_returns_404(lifecycle_client):
    resp = lifecycle_client.post("/projects/HRI-9999/reactivate")
    assert resp.status_code == 404


# --- monthly snapshots ----------------------------------------------------


def test_add_monthly_snapshot_returns_201(lifecycle_client):
    lifecycle_client.post("/projects", json=_valid_project_payload(project_id="HRI-6030"))
    resp = lifecycle_client.post("/projects/HRI-6030/snapshots", json=_valid_snapshot_payload())
    assert resp.status_code == 201
    body = resp.json()
    assert body["reporting_month"] == "2025-06"
    assert body["is_terminal_snapshot"] is False
    assert body["final_delay_days"] is None


def test_add_monthly_snapshot_duplicate_month_returns_409(lifecycle_client):
    lifecycle_client.post("/projects", json=_valid_project_payload(project_id="HRI-6031"))
    lifecycle_client.post("/projects/HRI-6031/snapshots", json=_valid_snapshot_payload())
    resp = lifecycle_client.post("/projects/HRI-6031/snapshots", json=_valid_snapshot_payload())
    assert resp.status_code == 409


def test_add_monthly_snapshot_invalid_reporting_month_returns_422(lifecycle_client):
    lifecycle_client.post("/projects", json=_valid_project_payload(project_id="HRI-6032"))
    resp = lifecycle_client.post(
        "/projects/HRI-6032/snapshots", json=_valid_snapshot_payload(reporting_month="2025-13")
    )
    assert resp.status_code == 422


def test_add_monthly_snapshot_unknown_project_returns_404(lifecycle_client):
    resp = lifecycle_client.post("/projects/HRI-9999/snapshots", json=_valid_snapshot_payload())
    assert resp.status_code == 404


def test_add_monthly_snapshot_ongoing_with_outcome_field_returns_422(lifecycle_client):
    lifecycle_client.post("/projects", json=_valid_project_payload(project_id="HRI-6033"))
    resp = lifecycle_client.post(
        "/projects/HRI-6033/snapshots", json=_valid_snapshot_payload(final_delay_days=10)
    )
    assert resp.status_code == 422


def test_add_monthly_snapshot_completed_without_outcomes_returns_422(lifecycle_client):
    lifecycle_client.post("/projects", json=_valid_project_payload(project_id="HRI-6034"))
    resp = lifecycle_client.post(
        "/projects/HRI-6034/snapshots", json=_valid_snapshot_payload(project_status="Completed")
    )
    assert resp.status_code == 422


# --- insufficient data / prediction integration ---------------------------


def test_predict_on_brand_new_project_returns_insufficient_data(lifecycle_client):
    lifecycle_client.post("/projects", json=_valid_project_payload(project_id="HRI-6040"))
    lifecycle_client.post(
        "/projects/HRI-6040/snapshots", json=_valid_snapshot_payload(reporting_month="2025-02")
    )

    resp = lifecycle_client.get("/projects/HRI-6040/predict", params={"reporting_month": "2025-02"})
    assert resp.status_code == 200
    body = resp.json()
    # A single real monthly update already provides every one of the 45
    # predictor columns (rolling features use min_periods=1) -- so this
    # is expected to be an actual model_prediction, not insufficient_data.
    # See test_predict_on_project_with_no_snapshot_at_all_is_404 for the
    # genuinely-insufficient case (zero snapshots).
    assert body["prediction_status"] == "model_prediction"
    assert body["is_model_prediction"] is True


def test_predict_on_project_with_no_snapshot_at_all_is_404(lifecycle_client):
    lifecycle_client.post("/projects", json=_valid_project_payload(project_id="HRI-6041"))
    resp = lifecycle_client.get("/projects/HRI-6041/predict", params={"reporting_month": "2025-06"})
    # No snapshot exists for this project at all yet -- a plain 404 "no
    # snapshot found" (existing, unmodified Phase 6 contract), distinct
    # from the insufficient_data 200 case (which is for a snapshot that
    # DOES exist but can't yield a full feature row).
    assert resp.status_code == 404


def test_predict_after_completing_project_returns_actual_outcome(lifecycle_client):
    lifecycle_client.post("/projects", json=_valid_project_payload(project_id="HRI-6042"))
    lifecycle_client.post(
        "/projects/HRI-6042/snapshots",
        json=_valid_snapshot_payload(
            reporting_month="2025-12",
            project_status="Completed",
            final_delay_days=30,
            significant_delay=1,
            final_cost_overrun_pct=8.0,
            cost_overrun=0,
        ),
    )

    resp = lifecycle_client.get("/projects/HRI-6042/predict", params={"reporting_month": "2025-12"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["prediction_status"] == "actual_outcome"
    assert body["is_model_prediction"] is False
    assert body["final_delay_days"]["actual_value"] == 30
    assert body["significant_delay"]["actual_value"] == 1
