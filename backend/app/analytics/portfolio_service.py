"""Phase 14 orchestration layer. Each `/analytics/*` (Phase 14) router
function calls exactly one of these and translates the returned dataclass
into its Pydantic response field-by-field -- no business logic lives in
the router itself (same convention as app.simulation.service /
app.decision_support.synthesizer). Nothing here performs live ML
inference: predicted-side data always comes from
`portfolio_prediction_cache` (app/analytics/batch_scoring.py).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analytics.batch_scoring import get_cache_metadata
from app.analytics.distribution import TaskDistribution, portfolio_risk_distribution
from app.analytics.drivers import TaskPortfolioDrivers, portfolio_drivers
from app.analytics.historical import HistoricalOverview, historical_overview
from app.analytics.insights import generate_executive_insights
from app.analytics.risk_projects import InvalidFilterError, RiskProjectRow, ranked_risk_projects
from app.analytics.risk_score import RiskScoreCohortMetadata, compute_portfolio_risk_scores
from app.analytics.segments import DIMENSIONS, MIN_SAMPLE_THRESHOLDS, SegmentEntry, segment_report
from app.analytics.trends import (
    HistoricalTrendPoint,
    PredictedTrendPoint,
    historical_trend_by_start_year,
    predicted_trend_by_reporting_year,
)
from app.db.models import Project, PortfolioPredictionCache

CACHE_MISSING_MESSAGE = (
    "The portfolio prediction cache has not been generated yet. Run "
    "`python -m scripts.batch_score_portfolio` from the repo root (after loading the "
    "database with scripts/load_db.py), then retry."
)


class InvalidDimensionError(ValueError):
    pass


@dataclass(frozen=True)
class PredictedOverview:
    status: str  # "ok" | "cache_unavailable"
    message: str | None
    scored_project_count: int
    avg_significant_delay_probability: float | None
    avg_cost_overrun_probability: float | None
    avg_final_delay_days_predicted: float | None
    avg_final_cost_overrun_pct_predicted: float | None
    risk_level_counts: dict[str, int]
    computed_at: str | None


@dataclass(frozen=True)
class PortfolioOverviewData:
    total_projects: int
    historical: HistoricalOverview
    predicted: PredictedOverview
    risk_distribution: list[TaskDistribution]
    top_risks: list[RiskProjectRow]
    executive_insights: list[str]


@dataclass(frozen=True)
class RiskProjectsData:
    cache_status: str
    cache_message: str | None
    total: int
    cohort_metadata: RiskScoreCohortMetadata | None
    items: list[RiskProjectRow]


@dataclass(frozen=True)
class SegmentsData:
    dimension: str
    min_sample_threshold: int
    entries: list[SegmentEntry]


@dataclass(frozen=True)
class TrendsData:
    historical: list[HistoricalTrendPoint]
    predicted_status: str
    predicted_message: str | None
    predicted: list[PredictedTrendPoint]


def _empty_cache_rows(db: Session) -> list[PortfolioPredictionCache]:
    return list(db.execute(select(PortfolioPredictionCache)).scalars().all())


def _predicted_overview(db: Session) -> PredictedOverview:
    cache_meta = get_cache_metadata(db)
    cache_rows = _empty_cache_rows(db)
    if not cache_rows or cache_meta is None:
        return PredictedOverview(
            status="cache_unavailable",
            message=CACHE_MISSING_MESSAGE,
            scored_project_count=0,
            avg_significant_delay_probability=None,
            avg_cost_overrun_probability=None,
            avg_final_delay_days_predicted=None,
            avg_final_cost_overrun_pct_predicted=None,
            risk_level_counts={},
            computed_at=None,
        )

    risk_results, _ = compute_portfolio_risk_scores(cache_rows)
    n = len(cache_rows)
    level_counts: dict[str, int] = {}
    for r in risk_results:
        level_counts[r.risk_level] = level_counts.get(r.risk_level, 0) + 1

    computed_at = cache_meta["computed_at"]
    return PredictedOverview(
        status="ok",
        message=None,
        scored_project_count=n,
        avg_significant_delay_probability=sum(r.significant_delay_probability or 0.0 for r in cache_rows) / n,
        avg_cost_overrun_probability=sum(r.cost_overrun_probability or 0.0 for r in cache_rows) / n,
        avg_final_delay_days_predicted=sum(r.final_delay_days_predicted for r in cache_rows) / n,
        avg_final_cost_overrun_pct_predicted=sum(r.final_cost_overrun_pct_predicted for r in cache_rows) / n,
        risk_level_counts=level_counts,
        computed_at=computed_at.isoformat() if hasattr(computed_at, "isoformat") else str(computed_at),
    )


def get_portfolio_overview(db: Session) -> PortfolioOverviewData:
    total_projects = db.execute(select(func.count()).select_from(Project)).scalar_one()
    hist = historical_overview(db)
    predicted = _predicted_overview(db)
    risk_distribution = portfolio_risk_distribution(db)
    top_risks, _, _ = ranked_risk_projects(db, limit=5)
    drivers = portfolio_drivers()

    state_segments = segment_report(db, "state")
    project_type_segments = segment_report(db, "project_type")
    contractor_segments = segment_report(db, "contractor")

    insights = generate_executive_insights(
        historical=hist,
        predicted_risk_level_counts=predicted.risk_level_counts,
        predicted_scored_count=predicted.scored_project_count,
        state_segments=state_segments,
        project_type_segments=project_type_segments,
        contractor_segments=contractor_segments,
        drivers=drivers,
    )

    return PortfolioOverviewData(
        total_projects=total_projects,
        historical=hist,
        predicted=predicted,
        risk_distribution=risk_distribution,
        top_risks=top_risks,
        executive_insights=insights,
    )


def get_risk_projects(
    db: Session,
    *,
    state: str | None = None,
    project_type: str | None = None,
    contractor: str | None = None,
    risk_level: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> RiskProjectsData:
    cache_meta = get_cache_metadata(db)
    if cache_meta is None:
        return RiskProjectsData(
            cache_status="cache_unavailable",
            cache_message=CACHE_MISSING_MESSAGE,
            total=0,
            cohort_metadata=None,
            items=[],
        )

    items, metadata, total = ranked_risk_projects(
        db,
        state=state,
        project_type=project_type,
        contractor=contractor,
        risk_level=risk_level,
        limit=limit,
        offset=offset,
    )
    return RiskProjectsData(
        cache_status="ok",
        cache_message=None,
        total=total,
        cohort_metadata=metadata,
        items=items,
    )


def get_segments(db: Session, dimension: str) -> SegmentsData:
    if dimension not in DIMENSIONS:
        raise InvalidDimensionError(f"Invalid dimension {dimension!r}; expected one of {DIMENSIONS}")
    entries = segment_report(db, dimension)
    return SegmentsData(dimension=dimension, min_sample_threshold=MIN_SAMPLE_THRESHOLDS[dimension], entries=entries)


def get_drivers() -> list[TaskPortfolioDrivers]:
    return portfolio_drivers()


def get_trends(db: Session) -> TrendsData:
    hist_points = historical_trend_by_start_year(db)
    cache_meta = get_cache_metadata(db)
    if cache_meta is None:
        return TrendsData(
            historical=hist_points,
            predicted_status="cache_unavailable",
            predicted_message=CACHE_MISSING_MESSAGE,
            predicted=[],
        )
    predicted_points = predicted_trend_by_reporting_year(db)
    return TrendsData(
        historical=hist_points,
        predicted_status="ok",
        predicted_message=None,
        predicted=predicted_points,
    )
