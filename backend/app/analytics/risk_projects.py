"""Phase 14 ranked top-risk project list.

Built entirely from `portfolio_prediction_cache` (app/analytics/batch_scoring.py)
plus the composite risk score (app/analytics/risk_score.py) joined to
static `Project` fields -- never live per-project inference. Powers both
the Top-Risk table and the Risk Matrix (delay_risk vs cost_risk scatter)
sections, since both are just different views of the same ranked list.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.risk_score import RiskScoreCohortMetadata, compute_portfolio_risk_scores
from app.db.models import Project, PortfolioPredictionCache

VALID_RISK_LEVELS = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}


class InvalidFilterError(ValueError):
    pass


@dataclass(frozen=True)
class RiskProjectRow:
    project_id: str
    project_name: str
    state: str
    project_type: str
    contractor: str | None
    reporting_month: str
    risk_score: float
    risk_level: str
    delay_risk: float
    cost_risk: float
    significant_delay_probability: float | None
    final_delay_days_predicted: float
    cost_overrun_probability: float | None
    final_cost_overrun_pct_predicted: float


def ranked_risk_projects(
    db: Session,
    *,
    state: str | None = None,
    project_type: str | None = None,
    contractor: str | None = None,
    risk_level: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[list[RiskProjectRow], RiskScoreCohortMetadata | None, int]:
    """Returns (page of rows, cohort metadata, total matching count before
    pagination). Sorted deterministically: risk_score DESC, project_id ASC
    tie-break."""
    if risk_level is not None and risk_level not in VALID_RISK_LEVELS:
        raise InvalidFilterError(f"Invalid risk_level {risk_level!r}; expected one of {sorted(VALID_RISK_LEVELS)}")

    cache_rows = list(db.execute(select(PortfolioPredictionCache)).scalars().all())
    if not cache_rows:
        return [], None, 0

    risk_results, metadata = compute_portfolio_risk_scores(cache_rows)
    risk_by_project = {r.project_id: r for r in risk_results}
    projects = {p.project_id: p for p in db.execute(select(Project)).scalars().all()}

    rows: list[RiskProjectRow] = []
    for cache_row in cache_rows:
        project = projects.get(cache_row.project_id)
        if project is None:
            continue
        if state is not None and project.state != state:
            continue
        if project_type is not None and project.project_type != project_type:
            continue
        if contractor is not None and project.contractor != contractor:
            continue
        risk = risk_by_project[cache_row.project_id]
        if risk_level is not None and risk.risk_level != risk_level:
            continue
        rows.append(
            RiskProjectRow(
                project_id=cache_row.project_id,
                project_name=project.project_name,
                state=project.state,
                project_type=project.project_type,
                contractor=project.contractor,
                reporting_month=cache_row.reporting_month,
                risk_score=risk.composite_risk_score,
                risk_level=risk.risk_level,
                delay_risk=risk.delay_risk,
                cost_risk=risk.cost_risk,
                significant_delay_probability=cache_row.significant_delay_probability,
                final_delay_days_predicted=cache_row.final_delay_days_predicted,
                cost_overrun_probability=cache_row.cost_overrun_probability,
                final_cost_overrun_pct_predicted=cache_row.final_cost_overrun_pct_predicted,
            )
        )

    rows.sort(key=lambda r: (-r.risk_score, r.project_id))
    total = len(rows)
    if limit is not None:
        rows = rows[offset : offset + limit]
    elif offset:
        rows = rows[offset:]
    return rows, metadata, total
