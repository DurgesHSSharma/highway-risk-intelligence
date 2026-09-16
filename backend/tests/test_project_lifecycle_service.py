"""Phase 17B project lifecycle SERVICE tests (app.projects.lifecycle),
run directly against a small isolated temp database -- not the FastAPI
layer (see test_project_lifecycle_api.py for the HTTP contract). Mirrors
the existing tests/test_load_db.py isolation convention: a throwaway
generated dataset in a throwaway SQLite file, never the shared session
test database backend/tests/conftest.py builds for the read-only Phase
1-16 endpoints.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.db.base import create_all, make_engine
from app.db.loader import load_database
from app.db.models import Project, ProjectSnapshot
from app.projects.lifecycle import (
    ArchivedProjectError,
    DuplicateProjectIdError,
    DuplicateSnapshotError,
    InvalidProjectDataError,
    InvalidSnapshotDataError,
    ProjectAlreadyCompletedError,
    ProjectNotFoundError,
    add_monthly_snapshot,
    archive_project,
    create_project,
    reactivate_project,
    update_project,
)
from app.schemas.project_lifecycle import ProjectCreate, ProjectUpdate, SnapshotCreate
from scripts.generate_dataset import generate_dataset


@pytest.fixture()
def engine(tmp_path: Path):
    csv_path = tmp_path / "small_snapshots.csv"
    generate_dataset(n_projects=10, seed=3).to_csv(csv_path, index=False)
    eng = make_engine(f"sqlite:///{(tmp_path / 'lifecycle_service.db').as_posix()}")
    create_all(bind=eng)
    load_database(csv_path, bind=eng)
    return eng


@pytest.fixture()
def db(engine):
    session = Session(bind=engine)
    try:
        yield session
    finally:
        session.close()


def _valid_create(**overrides) -> ProjectCreate:
    defaults = dict(
        project_name="Test Bypass Highway",
        highway_number="NH-999",
        state="Test State",
        project_type="Greenfield",
        contractor="Test Contractor Pvt Ltd",
        project_length_km=42.0,
        original_contract_value_inr_cr=500.0,
        planned_start_date=dt.date(2025, 1, 1),
        planned_completion_date=dt.date(2027, 1, 1),
        planned_duration_months=24,
    )
    defaults.update(overrides)
    return ProjectCreate(**defaults)


def _valid_snapshot(**overrides) -> SnapshotCreate:
    defaults = dict(
        reporting_month="2025-06",
        project_status="Ongoing",
        planned_physical_progress_pct=25.0,
        actual_physical_progress_pct=20.0,
        planned_financial_progress_pct=25.0,
        actual_financial_progress_pct=18.0,
        planned_cost_to_date_inr_cr=125.0,
        actual_expenditure_inr_cr=90.0,
        actual_cost_to_date_inr_cr=90.0,
        material_cost_inr_cr=40.0,
        labour_cost_inr_cr=30.0,
        equipment_cost_inr_cr=20.0,
        variation_cost_inr_cr=0.0,
        delay_related_cost_inr_cr=5.0,
        land_acquisition_delay_days=10.0,
        utility_shifting_delay_days=0.0,
        environment_clearance_delay_days=0.0,
        material_delay_days=0.0,
        labour_shortage_days=0.0,
        equipment_unavailability_days=0.0,
        weather_disruption_days=5.0,
        contractor_productivity_factor=0.9,
        traffic_diversion_delay_days=0.0,
        design_change_delay_days=0.0,
        approval_delay_days=0.0,
    )
    defaults.update(overrides)
    return SnapshotCreate(**defaults)


# --- create_project ---------------------------------------------------


def test_create_project_with_generated_id(db):
    project = create_project(db, _valid_create())
    assert project.project_id.startswith("HRI-")
    assert project.data_provenance == "USER_ENTERED"
    assert project.is_archived is False
    assert project.archived_at is None


def test_create_project_generated_id_does_not_collide_with_synthetic_ids(db):
    """The fixture DB has 10 SYNTHETIC projects HRI-0001..HRI-0010; the
    next generated id must be HRI-0011, never a collision."""
    project = create_project(db, _valid_create())
    assert project.project_id == "HRI-0011"


def test_create_project_with_supplied_id(db):
    project = create_project(db, _valid_create(project_id="HRI-5001"))
    assert project.project_id == "HRI-5001"


def test_create_project_duplicate_supplied_id_raises(db):
    create_project(db, _valid_create(project_id="HRI-5002"))
    with pytest.raises(DuplicateProjectIdError):
        create_project(db, _valid_create(project_id="HRI-5002"))


def test_create_project_duplicate_id_against_existing_synthetic_project_raises(db):
    with pytest.raises(DuplicateProjectIdError):
        create_project(db, _valid_create(project_id="HRI-0001"))


def test_project_create_schema_rejects_invalid_id_format():
    """The HRI-NNNN format is enforced by ProjectCreate's own
    field_validator (app.schemas.project_lifecycle) -- a ProjectCreate
    instance with a malformed id can never be constructed, so
    create_project() itself is never reached with one. See
    test_project_lifecycle_api.py::test_create_project_invalid_id_format_returns_422
    for the end-to-end HTTP contract."""
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        _valid_create(project_id="NOT-A-VALID-ID")


def test_create_project_completion_before_start_raises(db):
    with pytest.raises(InvalidProjectDataError):
        create_project(
            db,
            _valid_create(
                planned_start_date=dt.date(2027, 1, 1),
                planned_completion_date=dt.date(2025, 1, 1),
            ),
        )


# --- update_project -----------------------------------------------------


def test_update_project_changes_only_supplied_fields(db):
    project = create_project(db, _valid_create())
    original_name = project.project_name

    updated = update_project(db, project.project_id, ProjectUpdate(contractor="New Contractor Ltd"))

    assert updated.contractor == "New Contractor Ltd"
    assert updated.project_name == original_name  # untouched


def test_update_project_unknown_project_raises_not_found(db):
    with pytest.raises(ProjectNotFoundError):
        update_project(db, "HRI-9999", ProjectUpdate(contractor="X"))


def test_update_project_invalid_dates_raises(db):
    project = create_project(db, _valid_create())
    with pytest.raises(InvalidProjectDataError):
        update_project(
            db,
            project.project_id,
            ProjectUpdate(planned_completion_date=dt.date(2020, 1, 1)),
        )


def test_update_project_preserves_existing_snapshots(db):
    project = create_project(db, _valid_create())
    add_monthly_snapshot(db, project.project_id, _valid_snapshot())

    update_project(db, project.project_id, ProjectUpdate(contractor="Changed Co"))

    snapshots = db.query(ProjectSnapshot).filter(ProjectSnapshot.project_id == project.project_id).all()
    assert len(snapshots) == 1
    assert snapshots[0].reporting_month == "2025-06"


# --- archive / reactivate ------------------------------------------------


def test_archive_project_sets_flag_and_timestamp_without_deleting(db):
    project = create_project(db, _valid_create())
    add_monthly_snapshot(db, project.project_id, _valid_snapshot())

    archived = archive_project(db, project.project_id)
    assert archived.is_archived is True
    assert archived.archived_at is not None

    # History preserved.
    still_there = db.get(Project, project.project_id)
    assert still_there is not None
    snapshots = db.query(ProjectSnapshot).filter(ProjectSnapshot.project_id == project.project_id).all()
    assert len(snapshots) == 1


def test_archive_project_is_idempotent(db):
    project = create_project(db, _valid_create())
    first = archive_project(db, project.project_id)
    second = archive_project(db, project.project_id)
    assert first.archived_at == second.archived_at


def test_archive_unknown_project_raises_not_found(db):
    with pytest.raises(ProjectNotFoundError):
        archive_project(db, "HRI-9999")


def test_reactivate_project_clears_flag_and_timestamp(db):
    project = create_project(db, _valid_create())
    archive_project(db, project.project_id)

    reactivated = reactivate_project(db, project.project_id)
    assert reactivated.is_archived is False
    assert reactivated.archived_at is None


def test_reactivate_non_archived_project_is_idempotent_noop(db):
    project = create_project(db, _valid_create())
    reactivated = reactivate_project(db, project.project_id)
    assert reactivated.is_archived is False


# --- add_monthly_snapshot -------------------------------------------------


def test_add_monthly_snapshot_ordinary_update_has_null_outcome_fields(db):
    project = create_project(db, _valid_create())
    snapshot = add_monthly_snapshot(db, project.project_id, _valid_snapshot())

    assert snapshot.is_terminal_snapshot is False
    assert snapshot.final_delay_days is None
    assert snapshot.significant_delay is None
    assert snapshot.final_cost_overrun_pct is None
    assert snapshot.cost_overrun is None
    assert snapshot.months_since_start == 5  # 2025-01 -> 2025-06


def test_add_monthly_snapshot_derives_variance_fields(db):
    project = create_project(db, _valid_create())
    snapshot = add_monthly_snapshot(
        db,
        project.project_id,
        _valid_snapshot(actual_physical_progress_pct=20.0, planned_physical_progress_pct=25.0),
    )
    assert snapshot.physical_progress_variance_pct == pytest.approx(-5.0)


def test_add_monthly_snapshot_unknown_project_raises_not_found(db):
    with pytest.raises(ProjectNotFoundError):
        add_monthly_snapshot(db, "HRI-9999", _valid_snapshot())


def test_add_monthly_snapshot_duplicate_month_raises(db):
    project = create_project(db, _valid_create())
    add_monthly_snapshot(db, project.project_id, _valid_snapshot())
    with pytest.raises(DuplicateSnapshotError):
        add_monthly_snapshot(db, project.project_id, _valid_snapshot())


def test_add_monthly_snapshot_before_planned_start_raises(db):
    project = create_project(db, _valid_create(planned_start_date=dt.date(2025, 6, 1)))
    with pytest.raises(InvalidSnapshotDataError):
        add_monthly_snapshot(db, project.project_id, _valid_snapshot(reporting_month="2025-01"))


def test_add_monthly_snapshot_ongoing_with_outcome_fields_raises(db):
    project = create_project(db, _valid_create())
    with pytest.raises(InvalidSnapshotDataError):
        add_monthly_snapshot(db, project.project_id, _valid_snapshot(final_delay_days=10))


def test_add_monthly_snapshot_completed_without_outcome_fields_raises(db):
    project = create_project(db, _valid_create())
    with pytest.raises(InvalidSnapshotDataError):
        add_monthly_snapshot(db, project.project_id, _valid_snapshot(project_status="Completed"))


def test_add_monthly_snapshot_completed_with_full_outcome_becomes_terminal(db):
    project = create_project(db, _valid_create())
    snapshot = add_monthly_snapshot(
        db,
        project.project_id,
        _valid_snapshot(
            project_status="Completed",
            final_delay_days=45,
            significant_delay=1,
            final_cost_overrun_pct=12.5,
            cost_overrun=1,
        ),
    )
    assert snapshot.is_terminal_snapshot is True
    assert snapshot.final_delay_days == 45
    assert snapshot.significant_delay == 1
    assert snapshot.final_cost_overrun_pct == pytest.approx(12.5)
    assert snapshot.cost_overrun == 1


def test_add_monthly_snapshot_after_terminal_raises_already_completed(db):
    project = create_project(db, _valid_create())
    add_monthly_snapshot(
        db,
        project.project_id,
        _valid_snapshot(
            project_status="Completed",
            final_delay_days=0,
            significant_delay=0,
            final_cost_overrun_pct=0.0,
            cost_overrun=0,
        ),
    )
    with pytest.raises(ProjectAlreadyCompletedError):
        add_monthly_snapshot(db, project.project_id, _valid_snapshot(reporting_month="2025-07"))


def test_add_monthly_snapshot_on_archived_project_raises(db):
    project = create_project(db, _valid_create())
    archive_project(db, project.project_id)
    with pytest.raises(ArchivedProjectError):
        add_monthly_snapshot(db, project.project_id, _valid_snapshot())
