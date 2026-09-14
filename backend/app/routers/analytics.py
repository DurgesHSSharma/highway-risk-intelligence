"""Phase 12 read-only portfolio analytics endpoint: GET /analytics/summary.

New in Phase 12 (frontend/dashboard integration) -- not part of Phases
1-11. Purely additive and read-only: aggregates the existing `projects` /
`project_snapshots` tables (populated by the unmodified Phase 6 loader)
with plain SQL GROUP BY/aggregate queries. No ML inference, no RAG, no
contradiction detection, no simulator logic is touched here.

Why this endpoint exists: the Phase 12 dashboard/analytics pages need
portfolio-wide counts (total projects, status/state/type distribution,
significant_delay/cost_overrun counts) that no Phase 1-11 endpoint
exposes. Computing them client-side would require one HTTP call per
project (400 projects) on every dashboard load -- clearly worse than one
cheap server-side aggregate query. See docs/FRONTEND_DASHBOARD.md.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.db.models import Project, ProjectSnapshot
from app.schemas.analytics import PortfolioSummaryResponse
from app.schemas.predictions import SYNTHETIC_DATA_DISCLAIMER_ACTUAL

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _current_status_counts(db: Session) -> dict[str, int]:
    """Per-project *latest* snapshot status, grouped and counted. Mirrors
    the subquery in app/routers/projects.py::_current_status_subquery
    exactly (not reimplemented differently) so this always agrees with
    what GET /projects?project_status=... would return."""
    latest = (
        select(
            ProjectSnapshot.project_id.label("project_id"),
            func.max(ProjectSnapshot.reporting_month).label("latest_month"),
        )
        .group_by(ProjectSnapshot.project_id)
        .subquery()
    )
    rows = db.execute(
        select(ProjectSnapshot.project_status, func.count())
        .join(
            latest,
            (ProjectSnapshot.project_id == latest.c.project_id)
            & (ProjectSnapshot.reporting_month == latest.c.latest_month),
        )
        .group_by(ProjectSnapshot.project_status)
    ).all()
    return {status: count for status, count in rows}


def _group_counts(db: Session, column) -> dict[str, int]:
    rows = db.execute(select(column, func.count()).group_by(column)).all()
    return {key: count for key, count in rows}


def _terminal_outcome_counts(db: Session) -> tuple[int, int, float, float]:
    """Each project's recorded outcome columns are repeated with an
    identical value on every one of its snapshot rows (see
    app/db/models.py), and every project has exactly one terminal row
    (app/db/loader.py), so reading them off the terminal
    (is_terminal_snapshot=True) row counts each project exactly once."""
    rows = db.execute(
        select(
            ProjectSnapshot.significant_delay,
            ProjectSnapshot.cost_overrun,
            ProjectSnapshot.final_delay_days,
            ProjectSnapshot.final_cost_overrun_pct,
        ).where(ProjectSnapshot.is_terminal_snapshot.is_(True))
    ).all()
    total = len(rows)
    significant_delay_count = sum(1 for r in rows if r.significant_delay == 1)
    cost_overrun_count = sum(1 for r in rows if r.cost_overrun == 1)
    avg_delay = (sum(r.final_delay_days for r in rows) / total) if total else 0.0
    avg_cost = (sum(r.final_cost_overrun_pct for r in rows) / total) if total else 0.0
    return significant_delay_count, cost_overrun_count, avg_delay, avg_cost


@router.get("/summary", response_model=PortfolioSummaryResponse)
def portfolio_summary(db: Session = Depends(get_db)) -> PortfolioSummaryResponse:
    total_projects = db.execute(select(func.count()).select_from(Project)).scalar_one()
    status_counts = _current_status_counts(db)
    state_counts = _group_counts(db, Project.state)
    project_type_counts = _group_counts(db, Project.project_type)
    significant_delay_count, cost_overrun_count, avg_delay, avg_cost = _terminal_outcome_counts(db)

    return PortfolioSummaryResponse(
        total_projects=total_projects,
        status_counts=status_counts,
        state_counts=state_counts,
        project_type_counts=project_type_counts,
        significant_delay_count=significant_delay_count,
        cost_overrun_count=cost_overrun_count,
        avg_final_delay_days=avg_delay,
        avg_final_cost_overrun_pct=avg_cost,
        synthetic_data_disclaimer=SYNTHETIC_DATA_DISCLAIMER_ACTUAL,
    )
