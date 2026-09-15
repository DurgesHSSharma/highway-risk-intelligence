"""Phase 14 HISTORICAL / ACTUAL portfolio statistics.

Computed exclusively from TERMINAL (`is_terminal_snapshot=True`) snapshot
rows -- i.e. recorded actual outcomes, never a model prediction. Every
project in this synthetic corpus is simulated through to completion, so
ALL 400 projects have exactly one terminal row: these statistics cover the
full population, not a sample (see app/analytics/batch_scoring.py for the
matching "predicted" definition and why the two must never be blended --
docs/ADVANCED_ANALYTICS.md "Historical vs predicted separation").
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Project, ProjectSnapshot


@dataclass(frozen=True)
class HistoricalOverview:
    completed_project_count: int
    significant_delay_count: int
    significant_delay_rate: float
    cost_overrun_count: int
    cost_overrun_rate: float
    mean_final_delay_days: float
    mean_final_cost_overrun_pct: float


def terminal_outcome_rows(db: Session):
    """Every project's single terminal row, joined to its static Project
    fields. Returns raw SQLAlchemy Row objects (not ORM instances) -- the
    caller groups/aggregates them in plain Python, matching the existing
    Phase 12 app/routers/analytics.py convention."""
    stmt = (
        select(
            Project.project_id,
            Project.state,
            Project.project_type,
            Project.contractor,
            Project.planned_start_date,
            ProjectSnapshot.significant_delay,
            ProjectSnapshot.cost_overrun,
            ProjectSnapshot.final_delay_days,
            ProjectSnapshot.final_cost_overrun_pct,
        )
        .join(ProjectSnapshot, ProjectSnapshot.project_id == Project.project_id)
        .where(ProjectSnapshot.is_terminal_snapshot.is_(True))
    )
    return db.execute(stmt).all()


def historical_overview(db: Session) -> HistoricalOverview:
    rows = terminal_outcome_rows(db)
    n = len(rows)
    if n == 0:
        return HistoricalOverview(0, 0, 0.0, 0, 0.0, 0.0, 0.0)
    sig = sum(1 for r in rows if r.significant_delay == 1)
    cost = sum(1 for r in rows if r.cost_overrun == 1)
    return HistoricalOverview(
        completed_project_count=n,
        significant_delay_count=sig,
        significant_delay_rate=sig / n,
        cost_overrun_count=cost,
        cost_overrun_rate=cost / n,
        mean_final_delay_days=sum(r.final_delay_days for r in rows) / n,
        mean_final_cost_overrun_pct=sum(r.final_cost_overrun_pct for r in rows) / n,
    )
