"""Phase 17B regression: the loader's clear-and-reload must never delete a
USER_ENTERED project. Root suite; mirrors tests/test_load_db.py's fixtures
and style, exercising the loader directly (via a raw ORM insert, bypassing
the lifecycle API) since this is a loader-level guarantee independent of
how a USER_ENTERED row was created.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

import scripts.load_db  # noqa: F401  (adds backend/ to sys.path as a side effect)
from scripts.generate_dataset import generate_dataset

from app.db.base import make_engine  # noqa: E402
from app.db.loader import load_database  # noqa: E402
from app.db.models import Project, ProjectSnapshot  # noqa: E402


@pytest.fixture()
def small_csv(tmp_path: Path) -> Path:
    df = generate_dataset(n_projects=15, seed=7)
    csv_path = tmp_path / "small_snapshots.csv"
    df.to_csv(csv_path, index=False)
    return csv_path


@pytest.fixture()
def temp_engine(tmp_path: Path):
    db_path = tmp_path / "loader_preserve_test.db"
    return make_engine(f"sqlite:///{db_path.as_posix()}")


def _insert_user_project(engine) -> None:
    """Directly ORM-inserts one USER_ENTERED project with one non-terminal
    snapshot, deliberately bypassing the Phase 17B lifecycle API -- this
    test proves the loader's own guarantee in isolation from that layer.
    """
    session = Session(bind=engine)
    try:
        session.add(
            Project(
                project_id="HRI-USER-0001",
                data_provenance="USER_ENTERED",
                project_name="Test User-Entered Highway",
                highway_number="NH-TEST",
                state="Test State",
                project_type="Greenfield",
                contractor="Test Contractor",
                project_length_km=10.0,
                original_contract_value_inr_cr=100.0,
                planned_start_date=dt.date(2025, 1, 1),
                planned_completion_date=dt.date(2027, 1, 1),
                planned_duration_months=24,
            )
        )
        session.add(
            ProjectSnapshot(
                project_id="HRI-USER-0001",
                reporting_month="2025-06",
                months_since_start=6,
                project_status="Ongoing",
                planned_physical_progress_pct=25.0,
                actual_physical_progress_pct=20.0,
                physical_progress_variance_pct=-5.0,
                planned_financial_progress_pct=25.0,
                actual_financial_progress_pct=None,
                financial_progress_variance_pct=None,
                planned_expenditure_inr_cr=25.0,
                actual_expenditure_inr_cr=None,
                expenditure_variance_pct=None,
                planned_cost_to_date_inr_cr=25.0,
                actual_cost_to_date_inr_cr=20.0,
                material_cost_inr_cr=10.0,
                labour_cost_inr_cr=5.0,
                equipment_cost_inr_cr=5.0,
                variation_cost_inr_cr=None,
                delay_related_cost_inr_cr=0.0,
                land_acquisition_delay_days=0.0,
                utility_shifting_delay_days=0.0,
                environment_clearance_delay_days=0.0,
                material_delay_days=0.0,
                labour_shortage_days=0.0,
                equipment_unavailability_days=None,
                weather_disruption_days=None,
                contractor_productivity_factor=1.0,
                traffic_diversion_delay_days=0.0,
                design_change_delay_days=0.0,
                approval_delay_days=0.0,
                is_terminal_snapshot=False,
                final_delay_days=0,
                significant_delay=0,
                final_cost_overrun_pct=0.0,
                cost_overrun=0,
            )
        )
        session.commit()
    finally:
        session.close()


def test_user_entered_project_survives_synthetic_reload(small_csv, temp_engine):
    load_database(small_csv, bind=temp_engine)
    _insert_user_project(temp_engine)

    summary = load_database(small_csv, bind=temp_engine)

    session = Session(bind=temp_engine)
    try:
        survivor = session.get(Project, "HRI-USER-0001")
        assert survivor is not None
        assert survivor.data_provenance == "USER_ENTERED"
        snapshots = (
            session.query(ProjectSnapshot)
            .filter(ProjectSnapshot.project_id == "HRI-USER-0001")
            .all()
        )
        assert len(snapshots) == 1
    finally:
        session.close()

    assert summary.preserved_user_projects == 1
    assert summary.preserved_user_snapshots == 1


def test_synthetic_reload_still_replaces_synthetic_rows(small_csv, temp_engine):
    first = load_database(small_csv, bind=temp_engine)
    _insert_user_project(temp_engine)
    second = load_database(small_csv, bind=temp_engine)

    assert second.projects_loaded == first.projects_loaded
    assert second.snapshots_loaded == first.snapshots_loaded
    assert second.reconciled


def test_loader_never_deletes_user_project_across_multiple_reloads(small_csv, temp_engine):
    load_database(small_csv, bind=temp_engine)
    _insert_user_project(temp_engine)

    for _ in range(3):
        load_database(small_csv, bind=temp_engine)

    session = Session(bind=temp_engine)
    try:
        assert session.get(Project, "HRI-USER-0001") is not None
    finally:
        session.close()
