"""Phase 14: portfolio-level analytics with historical/predicted
separation. Purely additive -- does not modify the Phase 12
GET /analytics/summary endpoint (app/routers/analytics.py), which is left
untouched and still registered separately.

Five endpoints, one per genuinely distinct query shape (a scalar overview,
a filterable/paginated ranked list, a dimension-parameterized segment
breakdown, a static SHAP artifact, and a grouped time series) rather than
one large or eight tiny endpoints:

    GET /analytics/portfolio       -- overview: historical + predicted + risk
                                       distribution + top risks + executive insights
    GET /analytics/risk-projects   -- ranked, filterable, paginated risk list
                                       (also backs the Risk Matrix)
    GET /analytics/segments        -- state / project_type / contractor analytics
    GET /analytics/drivers         -- portfolio-wide model-attributed SHAP drivers
    GET /analytics/trends          -- historical (actual) + predicted (model) trends

All predicted-side data is read from the `portfolio_prediction_cache`
table (app/analytics/batch_scoring.py) -- these endpoints never run
per-project live ML inference. When the cache has not been populated yet,
each affected endpoint returns HTTP 200 with an explicit
`cache_status="cache_unavailable"` field and a message explaining how to
generate it (see app/analytics/portfolio_service.py), rather than silently
falling back to live inference or a bare error with no remediation.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.analytics import portfolio_service
from app.analytics.drivers import ShapArtifactMissingError
from app.analytics.risk_projects import InvalidFilterError
from app.analytics.segments import DIMENSIONS
from app.config import settings
from app.db.base import get_db
from app.schemas.portfolio_analytics import (
    BucketCountOut,
    DriversResponse,
    HistoricalOverviewOut,
    HistoricalSegmentStatOut,
    HistoricalTrendPointOut,
    PortfolioDriverOut,
    PortfolioOverviewResponse,
    PredictedOverviewOut,
    PredictedSegmentStatOut,
    PredictedTrendPointOut,
    RiskProjectOut,
    RiskProjectsResponse,
    RiskScoreCohortMetadataOut,
    SegmentEntryOut,
    SegmentsResponse,
    TaskDistributionOut,
    TaskPortfolioDriversOut,
    TrendsResponse,
)

router = APIRouter(prefix="/analytics", tags=["portfolio-analytics"])


def _risk_project_out(row) -> RiskProjectOut:
    return RiskProjectOut(
        project_id=row.project_id,
        project_name=row.project_name,
        state=row.state,
        project_type=row.project_type,
        contractor=row.contractor,
        reporting_month=row.reporting_month,
        risk_score=row.risk_score,
        risk_level=row.risk_level,
        delay_risk=row.delay_risk,
        cost_risk=row.cost_risk,
        significant_delay_probability=row.significant_delay_probability,
        final_delay_days_predicted=row.final_delay_days_predicted,
        cost_overrun_probability=row.cost_overrun_probability,
        final_cost_overrun_pct_predicted=row.final_cost_overrun_pct_predicted,
    )


def _cohort_metadata_out(metadata) -> RiskScoreCohortMetadataOut | None:
    if metadata is None:
        return None
    return RiskScoreCohortMetadataOut(
        cohort_size=metadata.cohort_size,
        final_delay_days_min=metadata.final_delay_days_range.observed_min,
        final_delay_days_max=metadata.final_delay_days_range.observed_max,
        final_cost_overrun_pct_min=metadata.final_cost_overrun_pct_range.observed_min,
        final_cost_overrun_pct_max=metadata.final_cost_overrun_pct_range.observed_max,
        risk_level_thresholds=metadata.level_thresholds,
    )


@router.get("/portfolio", response_model=PortfolioOverviewResponse)
def portfolio_overview(db: Session = Depends(get_db)) -> PortfolioOverviewResponse:
    data = portfolio_service.get_portfolio_overview(db)
    return PortfolioOverviewResponse(
        total_projects=data.total_projects,
        historical=HistoricalOverviewOut(
            completed_project_count=data.historical.completed_project_count,
            significant_delay_count=data.historical.significant_delay_count,
            significant_delay_rate=data.historical.significant_delay_rate,
            cost_overrun_count=data.historical.cost_overrun_count,
            cost_overrun_rate=data.historical.cost_overrun_rate,
            mean_final_delay_days=data.historical.mean_final_delay_days,
            mean_final_cost_overrun_pct=data.historical.mean_final_cost_overrun_pct,
        ),
        predicted=PredictedOverviewOut(
            status=data.predicted.status,
            message=data.predicted.message,
            scored_project_count=data.predicted.scored_project_count,
            avg_significant_delay_probability=data.predicted.avg_significant_delay_probability,
            avg_cost_overrun_probability=data.predicted.avg_cost_overrun_probability,
            avg_final_delay_days_predicted=data.predicted.avg_final_delay_days_predicted,
            avg_final_cost_overrun_pct_predicted=data.predicted.avg_final_cost_overrun_pct_predicted,
            risk_level_counts=data.predicted.risk_level_counts,
            computed_at=data.predicted.computed_at,
        ),
        risk_distribution=[
            TaskDistributionOut(
                task_key=td.task_key,
                bucket_strategy=td.bucket_strategy,
                buckets=[BucketCountOut(label=b.label, lower=b.lower, upper=b.upper, count=b.count) for b in td.buckets],
                raw_values=td.raw_values,
            )
            for td in data.risk_distribution
        ],
        top_risks=[_risk_project_out(r) for r in data.top_risks],
        executive_insights=data.executive_insights,
    )


@router.get("/risk-projects", response_model=RiskProjectsResponse)
def risk_projects(
    state: str | None = Query(None),
    project_type: str | None = Query(None),
    contractor: str | None = Query(None),
    risk_level: str | None = Query(None, description="One of LOW, MEDIUM, HIGH, CRITICAL."),
    limit: int = Query(settings.default_page_size, ge=1, le=settings.max_page_size),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> RiskProjectsResponse:
    try:
        data = portfolio_service.get_risk_projects(
            db,
            state=state,
            project_type=project_type,
            contractor=contractor,
            risk_level=risk_level,
            limit=limit,
            offset=offset,
        )
    except InvalidFilterError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return RiskProjectsResponse(
        cache_status=data.cache_status,
        cache_message=data.cache_message,
        total=data.total,
        cohort_metadata=_cohort_metadata_out(data.cohort_metadata),
        items=[_risk_project_out(r) for r in data.items],
    )


@router.get("/segments", response_model=SegmentsResponse)
def segments(
    dimension: str = Query(..., description=f"One of {', '.join(DIMENSIONS)}."),
    db: Session = Depends(get_db),
) -> SegmentsResponse:
    try:
        data = portfolio_service.get_segments(db, dimension)
    except portfolio_service.InvalidDimensionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return SegmentsResponse(
        dimension=data.dimension,
        min_sample_threshold=data.min_sample_threshold,
        entries=[
            SegmentEntryOut(
                dimension=e.dimension,
                value=e.value,
                min_sample_threshold=e.min_sample_threshold,
                small_sample=e.small_sample,
                historical=(
                    HistoricalSegmentStatOut(
                        project_count=e.historical.project_count,
                        significant_delay_rate=e.historical.significant_delay_rate,
                        cost_overrun_rate=e.historical.cost_overrun_rate,
                        mean_final_delay_days=e.historical.mean_final_delay_days,
                        mean_final_cost_overrun_pct=e.historical.mean_final_cost_overrun_pct,
                    )
                    if e.historical
                    else None
                ),
                predicted=(
                    PredictedSegmentStatOut(
                        scored_project_count=e.predicted.scored_project_count,
                        avg_significant_delay_probability=e.predicted.avg_significant_delay_probability,
                        avg_cost_overrun_probability=e.predicted.avg_cost_overrun_probability,
                        avg_final_delay_days_predicted=e.predicted.avg_final_delay_days_predicted,
                        avg_final_cost_overrun_pct_predicted=e.predicted.avg_final_cost_overrun_pct_predicted,
                        avg_composite_risk_score=e.predicted.avg_composite_risk_score,
                        risk_level_counts=e.predicted.risk_level_counts,
                    )
                    if e.predicted
                    else None
                ),
            )
            for e in data.entries
        ],
    )


@router.get("/drivers", response_model=DriversResponse)
def drivers() -> DriversResponse:
    try:
        task_drivers = portfolio_service.get_drivers()
    except ShapArtifactMissingError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return DriversResponse(
        tasks=[
            TaskPortfolioDriversOut(
                task_key=td.task_key,
                label=td.label,
                model_family_explained=td.model_family_explained,
                matches_serving_model=td.matches_serving_model,
                drivers=[
                    PortfolioDriverOut(rank=d.rank, feature=d.feature, raw_feature=d.raw_feature, mean_abs_shap=d.mean_abs_shap)
                    for d in td.drivers
                ],
            )
            for td in task_drivers
        ]
    )


@router.get("/trends", response_model=TrendsResponse)
def trends(db: Session = Depends(get_db)) -> TrendsResponse:
    data = portfolio_service.get_trends(db)
    return TrendsResponse(
        historical=[
            HistoricalTrendPointOut(
                period=p.period,
                project_count=p.project_count,
                significant_delay_rate=p.significant_delay_rate,
                cost_overrun_rate=p.cost_overrun_rate,
                mean_final_delay_days=p.mean_final_delay_days,
                mean_final_cost_overrun_pct=p.mean_final_cost_overrun_pct,
                small_sample=p.small_sample,
            )
            for p in data.historical
        ],
        predicted_status=data.predicted_status,
        predicted_message=data.predicted_message,
        predicted=[
            PredictedTrendPointOut(
                period=p.period,
                scored_project_count=p.scored_project_count,
                avg_significant_delay_probability=p.avg_significant_delay_probability,
                avg_cost_overrun_probability=p.avg_cost_overrun_probability,
                avg_composite_risk_score=p.avg_composite_risk_score,
                small_sample=p.small_sample,
            )
            for p in data.predicted
        ],
    )
