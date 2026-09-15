"""Phase 14 historical and predicted portfolio trends.

HISTORICAL trend is grouped by each project's `planned_start_date` cohort
YEAR (2019-2024 in this corpus) using only terminal/actual outcome values
-- never a model prediction (section 22 of the Phase 14 brief). This axis
was chosen over `reporting_month` because a project's four outcome columns
are constant across its whole lifecycle: the only statistically meaningful
temporal axis for an ACTUAL-outcome trend is when a project's lifecycle
began, not an arbitrary snapshot month within it.

PREDICTED trend is grouped by the REPORTING-MONTH YEAR of each project's
cached "current" (latest non-terminal) snapshot -- the same definition
used everywhere else in Phase 14 -- using only
`portfolio_prediction_cache` rows, never terminal/actual data. Real
measured coverage (see docs/ADVANCED_ANALYTICS.md): eligible snapshots
span 2019-2029, with most years (2020-2026) offering 25-78 projects and
the two tail years (2019, 2027-2029) very thin -- those thin years are
flagged `small_sample=True` rather than fabricated or silently dropped.

Both trends are returned in chronological order and are never merged into
one series.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.historical import terminal_outcome_rows
from app.analytics.risk_score import compute_portfolio_risk_scores
from app.db.models import PortfolioPredictionCache

TREND_MIN_SAMPLE_THRESHOLD = 15


@dataclass(frozen=True)
class HistoricalTrendPoint:
    period: str
    project_count: int
    significant_delay_rate: float
    cost_overrun_rate: float
    mean_final_delay_days: float
    mean_final_cost_overrun_pct: float
    small_sample: bool


@dataclass(frozen=True)
class PredictedTrendPoint:
    period: str
    scored_project_count: int
    avg_significant_delay_probability: float
    avg_cost_overrun_probability: float
    avg_composite_risk_score: float
    small_sample: bool


def historical_trend_by_start_year(db: Session) -> list[HistoricalTrendPoint]:
    grouped: dict[str, list] = defaultdict(list)
    for row in terminal_outcome_rows(db):
        year = str(row.planned_start_date)[:4]
        grouped[year].append(row)

    points: list[HistoricalTrendPoint] = []
    for year in sorted(grouped):
        rows = grouped[year]
        n = len(rows)
        sig = sum(1 for r in rows if r.significant_delay == 1)
        cost = sum(1 for r in rows if r.cost_overrun == 1)
        points.append(
            HistoricalTrendPoint(
                period=year,
                project_count=n,
                significant_delay_rate=sig / n,
                cost_overrun_rate=cost / n,
                mean_final_delay_days=sum(r.final_delay_days for r in rows) / n,
                mean_final_cost_overrun_pct=sum(r.final_cost_overrun_pct for r in rows) / n,
                small_sample=n < TREND_MIN_SAMPLE_THRESHOLD,
            )
        )
    return points


def predicted_trend_by_reporting_year(db: Session) -> list[PredictedTrendPoint]:
    cache_rows = list(db.execute(select(PortfolioPredictionCache)).scalars().all())
    if not cache_rows:
        return []

    risk_results, _ = compute_portfolio_risk_scores(cache_rows)
    risk_by_project = {r.project_id: r for r in risk_results}

    grouped: dict[str, list] = defaultdict(list)
    for row in cache_rows:
        year = row.reporting_month[:4]
        grouped[year].append(row)

    points: list[PredictedTrendPoint] = []
    for year in sorted(grouped):
        rows = grouped[year]
        n = len(rows)
        risk_rows = [risk_by_project[r.project_id] for r in rows]
        points.append(
            PredictedTrendPoint(
                period=year,
                scored_project_count=n,
                avg_significant_delay_probability=sum(r.significant_delay_probability or 0.0 for r in rows) / n,
                avg_cost_overrun_probability=sum(r.cost_overrun_probability or 0.0 for r in rows) / n,
                avg_composite_risk_score=sum(rr.composite_risk_score for rr in risk_rows) / n,
                small_sample=n < TREND_MIN_SAMPLE_THRESHOLD,
            )
        )
    return points
