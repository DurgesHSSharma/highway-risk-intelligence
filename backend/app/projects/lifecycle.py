"""Phase 17B project lifecycle service: typed operations for creating,
editing, archiving, reactivating a project, and appending a monthly
progress snapshot -- the first WRITE path this app has ever had (Phases
1-16 were entirely read-only, reproducible from the committed CSV).
Mirrors the existing service-layer convention (app.simulation.service,
app.decision_support.synthesizer): typed exceptions here, HTTP status
translation only happens in app.routers.project_lifecycle.

Every created project gets `data_provenance = DATA_PROVENANCE_USER_ENTERED`
(app.db.models) -- never SYNTHETIC, which app/db/loader.py's clear-and-
reload reserves exclusively for CSV-sourced rows. That single label is what
makes a USER_ENTERED project immune to the loader however many times it's
rerun (see tests/test_loader_preserves_user_projects.py).

Archiving/reactivating never deletes a project or any of its snapshots --
only `is_archived` / `archived_at` change. There is no delete operation in
this module by design (see the master prompt: "If a delete-like UI is
required, interpret it as archive/deactivation, not destructive deletion").
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DATA_PROVENANCE_USER_ENTERED, Project, ProjectSnapshot
from app.schemas.project_lifecycle import ProjectCreate, ProjectUpdate, SnapshotCreate
from app.simulation.service import ProjectNotFoundError  # reused, never redefined

__all__ = [
    "ProjectNotFoundError",
    "DuplicateProjectIdError",
    "InvalidProjectDataError",
    "DuplicateSnapshotError",
    "InvalidSnapshotDataError",
    "ProjectAlreadyCompletedError",
    "ArchivedProjectError",
    "create_project",
    "update_project",
    "archive_project",
    "reactivate_project",
    "add_monthly_snapshot",
]

_OUTCOME_FIELDS = ("final_delay_days", "significant_delay", "final_cost_overrun_pct", "cost_overrun")


class DuplicateProjectIdError(ValueError):
    pass


class InvalidProjectDataError(ValueError):
    pass


class DuplicateSnapshotError(ValueError):
    pass


class InvalidSnapshotDataError(ValueError):
    pass


class ProjectAlreadyCompletedError(ValueError):
    pass


class ArchivedProjectError(ValueError):
    pass


def _next_project_id(db: Session) -> str:
    """Next `HRI-NNNN` id (4-digit, zero-padded, growing past HRI-9999 with
    more digits rather than failing). Takes the max numeric suffix across
    ALL existing projects -- SYNTHETIC and USER_ENTERED alike -- so an
    auto-generated id can never collide with either, regardless of the
    order projects were created/loaded in."""
    ids = db.execute(select(Project.project_id)).scalars().all()
    max_n = 0
    for pid in ids:
        m = re.fullmatch(r"HRI-(\d+)", pid)
        if m:
            max_n = max(max_n, int(m.group(1)))
    return f"HRI-{max_n + 1:04d}"


def _validate_dates(planned_start_date: date, planned_completion_date: date) -> None:
    if planned_completion_date <= planned_start_date:
        raise InvalidProjectDataError("planned_completion_date must be after planned_start_date.")


def create_project(db: Session, payload: ProjectCreate) -> Project:
    """Creates a USER_ENTERED project record -- the government/project
    estimate layer only (contract value, planned dates, length, etc.). No
    snapshot is created here and no ML assessment is attempted: a project
    has no predictor history until its first `add_monthly_snapshot` call
    (see GET /projects/{id}/predict's prediction_status="insufficient_data"
    for that state, app/routers/predictions.py)."""
    _validate_dates(payload.planned_start_date, payload.planned_completion_date)

    # project_id's HRI-NNNN format is already enforced by ProjectCreate's
    # own field_validator (app.schemas.project_lifecycle) -- not re-checked
    # here, since a ProjectCreate instance can't exist with an invalid one.
    project_id = payload.project_id or _next_project_id(db)
    if db.get(Project, project_id) is not None:
        raise DuplicateProjectIdError(f"Project '{project_id}' already exists.")

    project = Project(
        project_id=project_id,
        data_provenance=DATA_PROVENANCE_USER_ENTERED,
        project_name=payload.project_name,
        highway_number=payload.highway_number,
        state=payload.state,
        project_type=payload.project_type,
        contractor=payload.contractor,
        project_length_km=payload.project_length_km,
        original_contract_value_inr_cr=payload.original_contract_value_inr_cr,
        planned_start_date=payload.planned_start_date,
        planned_completion_date=payload.planned_completion_date,
        planned_duration_months=payload.planned_duration_months,
        is_archived=False,
        archived_at=None,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def update_project(db: Session, project_id: str, payload: ProjectUpdate) -> Project:
    """Partial update of project-level (government/estimate) fields.
    `project_id` and `data_provenance` are immutable -- neither is a field
    on `ProjectUpdate`, so there is nothing to strip here. Existing
    snapshots are never touched."""
    project = db.get(Project, project_id)
    if project is None:
        raise ProjectNotFoundError(f"Project '{project_id}' not found.")

    changes = payload.model_dump(exclude_unset=True)
    new_start = changes.get("planned_start_date", project.planned_start_date)
    new_completion = changes.get("planned_completion_date", project.planned_completion_date)
    _validate_dates(new_start, new_completion)

    for field, value in changes.items():
        setattr(project, field, value)

    db.commit()
    db.refresh(project)
    return project


def archive_project(db: Session, project_id: str) -> Project:
    """Non-destructive: sets is_archived/archived_at only. Idempotent --
    archiving an already-archived project is a no-op (its original
    archived_at is preserved, not bumped)."""
    project = db.get(Project, project_id)
    if project is None:
        raise ProjectNotFoundError(f"Project '{project_id}' not found.")
    if not project.is_archived:
        project.is_archived = True
        project.archived_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.commit()
        db.refresh(project)
    return project


def reactivate_project(db: Session, project_id: str) -> Project:
    """Idempotent inverse of archive_project. Never touches snapshots."""
    project = db.get(Project, project_id)
    if project is None:
        raise ProjectNotFoundError(f"Project '{project_id}' not found.")
    if project.is_archived:
        project.is_archived = False
        project.archived_at = None
        db.commit()
        db.refresh(project)
    return project


def _months_between(start: date, reporting_month: str) -> int:
    year, month = (int(p) for p in reporting_month.split("-"))
    return (year - start.year) * 12 + (month - start.month)


def add_monthly_snapshot(db: Session, project_id: str, payload: SnapshotCreate) -> ProjectSnapshot:
    """Appends one monthly progress snapshot. Two write-time guarantees
    the schema alone can't express:

    1. The 4 actual-outcome columns are REQUIRED when project_status is
       "Completed" and FORBIDDEN otherwise -- never optional, never
       silently defaulted, never a model prediction (see
       app/db/models.py's ck_terminal_outcomes_populated CHECK for the
       DB-level half of this guarantee).
    2. Once a project has a terminal (Completed) snapshot, no further
       monthly update is accepted -- mirrors the synthetic dataset's own
       "exactly one terminal row per project" invariant that the rest of
       this app (analytics, decision support, etc.) already assumes.

    `physical_progress_variance_pct` / `financial_progress_variance_pct`
    are mechanically derived (actual - planned), never asked of the
    caller. `planned_expenditure_inr_cr` and `expenditure_variance_pct`
    are the existing schema's documented exact-duplicate columns (see
    app/db/models.py) -- populated from the single caller-supplied
    `planned_cost_to_date_inr_cr` / the derived financial variance,
    never asked for twice.
    """
    project = db.get(Project, project_id)
    if project is None:
        raise ProjectNotFoundError(f"Project '{project_id}' not found.")
    if project.is_archived:
        raise ArchivedProjectError(
            f"Project '{project_id}' is archived; reactivate it before adding a monthly update."
        )

    existing_terminal = db.execute(
        select(ProjectSnapshot.reporting_month)
        .where(ProjectSnapshot.project_id == project_id)
        .where(ProjectSnapshot.is_terminal_snapshot.is_(True))
    ).scalar_one_or_none()
    if existing_terminal is not None:
        raise ProjectAlreadyCompletedError(
            f"Project '{project_id}' already has a completed (terminal) snapshot at "
            f"'{existing_terminal}'; no further monthly updates are accepted."
        )

    duplicate = db.execute(
        select(ProjectSnapshot.id)
        .where(ProjectSnapshot.project_id == project_id)
        .where(ProjectSnapshot.reporting_month == payload.reporting_month)
    ).scalar_one_or_none()
    if duplicate is not None:
        raise DuplicateSnapshotError(
            f"Project '{project_id}' already has a snapshot for reporting_month "
            f"'{payload.reporting_month}'."
        )

    months_since_start = _months_between(project.planned_start_date, payload.reporting_month)
    if months_since_start < 0:
        raise InvalidSnapshotDataError(
            f"reporting_month '{payload.reporting_month}' is before this project's "
            f"planned_start_date ({project.planned_start_date})."
        )

    is_terminal = payload.project_status == "Completed"
    outcome_values = {field: getattr(payload, field) for field in _OUTCOME_FIELDS}
    if is_terminal:
        missing = [f for f, v in outcome_values.items() if v is None]
        if missing:
            raise InvalidSnapshotDataError(
                "project_status is 'Completed', which requires all four actual-outcome "
                f"fields; missing: {', '.join(missing)}."
            )
    else:
        supplied = [f for f, v in outcome_values.items() if v is not None]
        if supplied:
            raise InvalidSnapshotDataError(
                "Actual-outcome fields (final_delay_days, significant_delay, "
                "final_cost_overrun_pct, cost_overrun) may only be supplied when "
                f"project_status is 'Completed'; got project_status='Ongoing' with: "
                f"{', '.join(supplied)}."
            )
        outcome_values = {field: None for field in _OUTCOME_FIELDS}

    physical_progress_variance_pct = payload.actual_physical_progress_pct - payload.planned_physical_progress_pct
    if payload.actual_financial_progress_pct is None:
        financial_progress_variance_pct = None
    else:
        financial_progress_variance_pct = (
            payload.actual_financial_progress_pct - payload.planned_financial_progress_pct
        )

    snapshot = ProjectSnapshot(
        project_id=project_id,
        reporting_month=payload.reporting_month,
        months_since_start=months_since_start,
        project_status=payload.project_status,
        planned_physical_progress_pct=payload.planned_physical_progress_pct,
        actual_physical_progress_pct=payload.actual_physical_progress_pct,
        physical_progress_variance_pct=physical_progress_variance_pct,
        planned_financial_progress_pct=payload.planned_financial_progress_pct,
        actual_financial_progress_pct=payload.actual_financial_progress_pct,
        financial_progress_variance_pct=financial_progress_variance_pct,
        planned_expenditure_inr_cr=payload.planned_cost_to_date_inr_cr,
        actual_expenditure_inr_cr=payload.actual_expenditure_inr_cr,
        expenditure_variance_pct=financial_progress_variance_pct,
        planned_cost_to_date_inr_cr=payload.planned_cost_to_date_inr_cr,
        actual_cost_to_date_inr_cr=payload.actual_cost_to_date_inr_cr,
        material_cost_inr_cr=payload.material_cost_inr_cr,
        labour_cost_inr_cr=payload.labour_cost_inr_cr,
        equipment_cost_inr_cr=payload.equipment_cost_inr_cr,
        variation_cost_inr_cr=payload.variation_cost_inr_cr,
        delay_related_cost_inr_cr=payload.delay_related_cost_inr_cr,
        land_acquisition_delay_days=payload.land_acquisition_delay_days,
        utility_shifting_delay_days=payload.utility_shifting_delay_days,
        environment_clearance_delay_days=payload.environment_clearance_delay_days,
        material_delay_days=payload.material_delay_days,
        labour_shortage_days=payload.labour_shortage_days,
        equipment_unavailability_days=payload.equipment_unavailability_days,
        weather_disruption_days=payload.weather_disruption_days,
        contractor_productivity_factor=payload.contractor_productivity_factor,
        traffic_diversion_delay_days=payload.traffic_diversion_delay_days,
        design_change_delay_days=payload.design_change_delay_days,
        approval_delay_days=payload.approval_delay_days,
        is_terminal_snapshot=is_terminal,
        **outcome_values,
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot
