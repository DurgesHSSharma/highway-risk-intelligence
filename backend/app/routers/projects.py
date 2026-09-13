"""Project CRUD (read-only) endpoints: GET /projects, GET /projects/{id},
GET /projects/{id}/snapshots, GET /projects/{id}/snapshots/{reporting_month}.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.base import get_db
from app.db.models import Project, ProjectSnapshot
from app.schemas.projects import ProjectListResponse, ProjectOut, SnapshotOut

router = APIRouter(prefix="/projects", tags=["projects"])


def _current_status_subquery():
    """Per project_id, the project_status of its most recent snapshot
    (max reporting_month). "YYYY-MM" strings sort lexicographically the
    same as chronologically, so MAX() is safe here.

    Note: in this synthetic dataset every project's simulated trajectory
    runs all the way to completion, so every project's *latest* snapshot is
    "Completed" -- filtering `project_status=Ongoing` will currently return
    zero projects. This is an honest property of the data, not a bug; see
    docs/API_AND_DATABASE.md.
    """
    latest = (
        select(
            ProjectSnapshot.project_id.label("project_id"),
            func.max(ProjectSnapshot.reporting_month).label("latest_month"),
        )
        .group_by(ProjectSnapshot.project_id)
        .subquery()
    )
    return (
        select(
            ProjectSnapshot.project_id.label("project_id"),
            ProjectSnapshot.project_status.label("current_status"),
        )
        .join(
            latest,
            and_(
                ProjectSnapshot.project_id == latest.c.project_id,
                ProjectSnapshot.reporting_month == latest.c.latest_month,
            ),
        )
        .subquery()
    )


@router.get("", response_model=ProjectListResponse)
def list_projects(
    page: int = Query(1, ge=1),
    page_size: int = Query(settings.default_page_size, ge=1, le=settings.max_page_size),
    state: str | None = Query(None),
    project_type: str | None = Query(None),
    project_status: str | None = Query(None, description="Filters on each project's latest snapshot status."),
    db: Session = Depends(get_db),
) -> ProjectListResponse:
    status_subq = _current_status_subquery()
    base = select(Project, status_subq.c.current_status).join(
        status_subq, Project.project_id == status_subq.c.project_id
    )

    if state is not None:
        base = base.where(Project.state == state)
    if project_type is not None:
        base = base.where(Project.project_type == project_type)
    if project_status is not None:
        base = base.where(status_subq.c.current_status == project_status)

    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()

    paged = base.order_by(Project.project_id.asc()).offset((page - 1) * page_size).limit(page_size)
    rows = db.execute(paged).all()

    items = [
        ProjectOut.model_validate({**vars(project), "current_status": current_status})
        for project, current_status in rows
    ]
    return ProjectListResponse(items=items, page=page, page_size=page_size, total=total)


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: str, db: Session = Depends(get_db)) -> ProjectOut:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")

    latest_snapshot = db.execute(
        select(ProjectSnapshot.project_status)
        .where(ProjectSnapshot.project_id == project_id)
        .order_by(ProjectSnapshot.reporting_month.desc())
        .limit(1)
    ).scalar_one_or_none()

    return ProjectOut.model_validate({**vars(project), "current_status": latest_snapshot or "Unknown"})


@router.get("/{project_id}/snapshots", response_model=list[SnapshotOut])
def list_project_snapshots(project_id: str, db: Session = Depends(get_db)) -> list[SnapshotOut]:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")

    snapshots = db.execute(
        select(ProjectSnapshot)
        .where(ProjectSnapshot.project_id == project_id)
        .order_by(ProjectSnapshot.reporting_month.asc())
    ).scalars().all()
    return [SnapshotOut.model_validate(s) for s in snapshots]


@router.get("/{project_id}/snapshots/{reporting_month}", response_model=SnapshotOut)
def get_project_snapshot(project_id: str, reporting_month: str, db: Session = Depends(get_db)) -> SnapshotOut:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")

    snapshot = db.execute(
        select(ProjectSnapshot)
        .where(ProjectSnapshot.project_id == project_id)
        .where(ProjectSnapshot.reporting_month == reporting_month)
    ).scalar_one_or_none()
    if snapshot is None:
        raise HTTPException(
            status_code=404,
            detail=f"No snapshot for project '{project_id}' at reporting_month '{reporting_month}'.",
        )
    return SnapshotOut.model_validate(snapshot)
