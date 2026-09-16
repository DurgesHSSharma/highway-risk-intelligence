"""Project CRUD (read-only) endpoints: GET /projects, GET /projects/{id},
GET /projects/{id}/snapshots, GET /projects/{id}/snapshots/{reporting_month}.

Phase 13 adds real server-side search to GET /projects via the `q` query
parameter (see `_search_filter` below) -- it replaces the Phase 12
frontend's client-side full-list search, which fetched all 400 projects
into the browser and filtered there because this endpoint previously had no
free-text query param. Search now happens entirely in SQL, is paginated
after filtering (same as the existing `state`/`project_type`/
`project_status` filters), and composes with them via AND. See
docs/PHASE_13.md for the full contract.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.base import get_db
from app.db.models import Project, ProjectSnapshot
from app.schemas.projects import ProjectListResponse, ProjectOut, SnapshotOut
from app.validation import MONTH_DESCRIPTION, MONTH_PATTERN

router = APIRouter(prefix="/projects", tags=["projects"])

# Fields searched by `q`, matching the Phase 13 brief's candidate list
# filtered down to columns that actually exist on `Project` (there is no
# `highway` column -- the real column is `highway_number`, see
# backend/app/db/models.py).
SEARCHABLE_COLUMNS = (
    Project.project_id,
    Project.project_name,
    Project.highway_number,
    Project.state,
    Project.contractor,
    Project.project_type,
)


def _escape_like(value: str) -> str:
    """Escapes SQL LIKE wildcards (`%`, `_`) and the escape character
    itself so a literal search term (e.g. a contractor name containing
    `_`) can't be misinterpreted as a pattern -- paired with
    `.ilike(..., escape="\\")` below."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _search_filter(q: str):
    """Case-insensitive partial match across `SEARCHABLE_COLUMNS`, ORed
    together. `.ilike()` is used (not `.like()`) so matching is
    case-insensitive on every backend, including SQLite, which has no
    native ILIKE -- SQLAlchemy compiles it to `lower(col) LIKE lower(...)`.
    `contractor` is nullable (~0.9% of projects); `ilike` on a NULL column
    safely evaluates to NULL/false rather than matching, which is the
    desired "no match" behavior."""
    pattern = f"%{_escape_like(q)}%"
    return or_(*(col.ilike(pattern, escape="\\") for col in SEARCHABLE_COLUMNS))


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
    q: str | None = Query(
        None,
        description=(
            "Case-insensitive partial-match search across project_id, project_name, "
            "highway_number, state, contractor, and project_type. Performed in SQL "
            "(SQLite), never client-side. Whitespace-only or omitted values are "
            "equivalent to no search."
        ),
    ),
    state: str | None = Query(None),
    project_type: str | None = Query(None),
    project_status: str | None = Query(None, description="Filters on each project's latest snapshot status."),
    is_archived: bool | None = Query(
        None,
        description=(
            "Phase 17B: filter on archived state. Omit (default) to return both active and "
            "archived projects unchanged from the pre-Phase-17B behavior."
        ),
    ),
    db: Session = Depends(get_db),
) -> ProjectListResponse:
    status_subq = _current_status_subquery()
    # LEFT OUTER (not INNER): a just-created USER_ENTERED project has zero
    # snapshots until its first monthly update, and must still be listed
    # (with current_status "Unknown", mirroring get_project's own
    # `latest_snapshot or "Unknown"` fallback below) rather than silently
    # disappearing from this endpoint until then.
    base = select(Project, status_subq.c.current_status).outerjoin(
        status_subq, Project.project_id == status_subq.c.project_id
    )

    q_clean = q.strip() if q else ""
    if q_clean:
        base = base.where(_search_filter(q_clean))
    if state is not None:
        base = base.where(Project.state == state)
    if project_type is not None:
        base = base.where(Project.project_type == project_type)
    if project_status is not None:
        base = base.where(status_subq.c.current_status == project_status)
    if is_archived is not None:
        base = base.where(Project.is_archived == is_archived)

    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()

    paged = base.order_by(Project.project_id.asc()).offset((page - 1) * page_size).limit(page_size)
    rows = db.execute(paged).all()

    items = [
        ProjectOut.model_validate({**vars(project), "current_status": current_status or "Unknown"})
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
def get_project_snapshot(
    project_id: str,
    reporting_month: str = Path(..., pattern=MONTH_PATTERN, description=MONTH_DESCRIPTION),
    db: Session = Depends(get_db),
) -> SnapshotOut:
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
