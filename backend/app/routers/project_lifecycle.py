"""Phase 17B project lifecycle write endpoints:

    POST   /projects                   create
    PATCH  /projects/{project_id}      edit
    POST   /projects/{project_id}/archive
    POST   /projects/{project_id}/reactivate
    POST   /projects/{project_id}/snapshots   monthly progress update

A separate router object from app.routers.projects (the existing
read-only GET endpoints on the same `/projects` prefix) -- same convention
Phase 14 already used for portfolio_analytics.py alongside analytics.py.
All business logic lives in app.projects.lifecycle; this module only
translates its typed exceptions into HTTP responses (same split as
app.routers.simulation / app.simulation.service).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import get_db
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
from app.schemas.projects import ProjectOut, SnapshotOut

router = APIRouter(prefix="/projects", tags=["project-lifecycle"])


def _project_out(db: Session, project: Project) -> ProjectOut:
    """Mirrors app.routers.projects.get_project's current-status lookup
    (latest snapshot's project_status, or "Unknown" if there isn't one yet
    -- true for a just-created project) -- reused here rather than
    reimplemented so both routers always agree."""
    latest_snapshot = db.execute(
        select(ProjectSnapshot.project_status)
        .where(ProjectSnapshot.project_id == project.project_id)
        .order_by(ProjectSnapshot.reporting_month.desc())
        .limit(1)
    ).scalar_one_or_none()
    return ProjectOut.model_validate({**vars(project), "current_status": latest_snapshot or "Unknown"})


@router.post("", response_model=ProjectOut, status_code=201)
def create_project_endpoint(payload: ProjectCreate, db: Session = Depends(get_db)) -> ProjectOut:
    try:
        project = create_project(db, payload)
    except DuplicateProjectIdError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except InvalidProjectDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return _project_out(db, project)


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project_endpoint(
    project_id: str, payload: ProjectUpdate, db: Session = Depends(get_db)
) -> ProjectOut:
    try:
        project = update_project(db, project_id, payload)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidProjectDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return _project_out(db, project)


@router.post("/{project_id}/archive", response_model=ProjectOut)
def archive_project_endpoint(project_id: str, db: Session = Depends(get_db)) -> ProjectOut:
    try:
        project = archive_project(db, project_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return _project_out(db, project)


@router.post("/{project_id}/reactivate", response_model=ProjectOut)
def reactivate_project_endpoint(project_id: str, db: Session = Depends(get_db)) -> ProjectOut:
    try:
        project = reactivate_project(db, project_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return _project_out(db, project)


@router.post("/{project_id}/snapshots", response_model=SnapshotOut, status_code=201)
def add_monthly_snapshot_endpoint(
    project_id: str, payload: SnapshotCreate, db: Session = Depends(get_db)
) -> SnapshotOut:
    try:
        snapshot = add_monthly_snapshot(db, project_id, payload)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DuplicateSnapshotError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (InvalidSnapshotDataError, ProjectAlreadyCompletedError, ArchivedProjectError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return SnapshotOut.model_validate(snapshot)
