"""Phase 14 portfolio-level analytics response schemas: GET /analytics/portfolio,
/analytics/risk-projects, /analytics/segments, /analytics/drivers,
/analytics/trends (backend/app/routers/portfolio_analytics.py).

Every schema keeps HISTORICAL/ACTUAL and CURRENT MODEL-PREDICTED data in
separate, explicitly labeled fields -- never one ambiguous blended value
(see docs/ADVANCED_ANALYTICS.md "Historical vs predicted separation").
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.schemas.predictions import SYNTHETIC_DATA_DISCLAIMER_ACTUAL, SYNTHETIC_DATA_DISCLAIMER_MODEL


class HistoricalOverviewOut(BaseModel):
    label: str = "HISTORICAL / ACTUAL"
    completed_project_count: int
    significant_delay_count: int
    significant_delay_rate: float
    cost_overrun_count: int
    cost_overrun_rate: float
    mean_final_delay_days: float
    mean_final_cost_overrun_pct: float
    synthetic_data_disclaimer: str = SYNTHETIC_DATA_DISCLAIMER_ACTUAL


class PredictedOverviewOut(BaseModel):
    label: str = "CURRENT MODEL-PREDICTED"
    status: str
    message: str | None = None
    scored_project_count: int
    avg_significant_delay_probability: float | None
    avg_cost_overrun_probability: float | None
    avg_final_delay_days_predicted: float | None
    avg_final_cost_overrun_pct_predicted: float | None
    risk_level_counts: dict[str, int]
    computed_at: str | None
    synthetic_data_disclaimer: str = SYNTHETIC_DATA_DISCLAIMER_MODEL


class BucketCountOut(BaseModel):
    label: str
    lower: float
    upper: float
    count: int


class TaskDistributionOut(BaseModel):
    task_key: str
    bucket_strategy: str
    buckets: list[BucketCountOut]
    raw_values: list[float]


class RiskProjectOut(BaseModel):
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
    prediction_status: str = "model_prediction"


class PortfolioOverviewResponse(BaseModel):
    total_projects: int
    historical: HistoricalOverviewOut
    predicted: PredictedOverviewOut
    risk_distribution: list[TaskDistributionOut]
    top_risks: list[RiskProjectOut]
    executive_insights: list[str]
    synthetic_data_disclaimer: str = SYNTHETIC_DATA_DISCLAIMER_ACTUAL


class RiskScoreCohortMetadataOut(BaseModel):
    cohort_size: int
    final_delay_days_min: float
    final_delay_days_max: float
    final_cost_overrun_pct_min: float
    final_cost_overrun_pct_max: float
    risk_level_thresholds: dict[str, float]


class RiskProjectsResponse(BaseModel):
    cache_status: str
    cache_message: str | None = None
    total: int
    cohort_metadata: RiskScoreCohortMetadataOut | None
    items: list[RiskProjectOut]
    synthetic_data_disclaimer: str = SYNTHETIC_DATA_DISCLAIMER_MODEL


class HistoricalSegmentStatOut(BaseModel):
    project_count: int
    significant_delay_rate: float
    cost_overrun_rate: float
    mean_final_delay_days: float
    mean_final_cost_overrun_pct: float


class PredictedSegmentStatOut(BaseModel):
    scored_project_count: int
    avg_significant_delay_probability: float
    avg_cost_overrun_probability: float
    avg_final_delay_days_predicted: float
    avg_final_cost_overrun_pct_predicted: float
    avg_composite_risk_score: float
    risk_level_counts: dict[str, int]


class SegmentEntryOut(BaseModel):
    dimension: str
    value: str
    min_sample_threshold: int
    small_sample: bool
    historical: HistoricalSegmentStatOut | None
    predicted: PredictedSegmentStatOut | None


class SegmentsResponse(BaseModel):
    dimension: str
    min_sample_threshold: int
    entries: list[SegmentEntryOut]
    synthetic_data_disclaimer: str = SYNTHETIC_DATA_DISCLAIMER_ACTUAL


class PortfolioDriverOut(BaseModel):
    rank: int
    feature: str
    raw_feature: str
    mean_abs_shap: float


class TaskPortfolioDriversOut(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    task_key: str
    label: str
    model_family_explained: str
    matches_serving_model: bool
    drivers: list[PortfolioDriverOut]


class DriversResponse(BaseModel):
    tasks: list[TaskPortfolioDriversOut]
    methodology_note: str = (
        "These are PORTFOLIO-WIDE, model-family-level SHAP importances reused verbatim "
        "from the Phase 5 saved global SHAP artifact (docs/artifacts/shap_local_examples.json) -- "
        "never recomputed. They are DIFFERENT from the per-project 'Project-specific drivers' shown "
        "on the AI Risk Summary page, which are computed LIVE at request time against the exact "
        "model actually serving that prediction (see app/decision_support/shap_explainer.py). "
        "Where `matches_serving_model` is false, the portfolio-wide ranking explains a different "
        "model family (XGBoost, from Phase 5) than the one currently serving that task's predictions."
    )


class HistoricalTrendPointOut(BaseModel):
    period: str
    project_count: int
    significant_delay_rate: float
    cost_overrun_rate: float
    mean_final_delay_days: float
    mean_final_cost_overrun_pct: float
    small_sample: bool


class PredictedTrendPointOut(BaseModel):
    period: str
    scored_project_count: int
    avg_significant_delay_probability: float
    avg_cost_overrun_probability: float
    avg_composite_risk_score: float
    small_sample: bool


class TrendsResponse(BaseModel):
    historical: list[HistoricalTrendPointOut]
    historical_label: str = "HISTORICAL / ACTUAL (grouped by planned start-date cohort year)"
    predicted_status: str
    predicted_message: str | None = None
    predicted: list[PredictedTrendPointOut]
    predicted_label: str = "CURRENT MODEL-PREDICTED (grouped by latest non-terminal reporting-month year)"
    synthetic_data_disclaimer: str = SYNTHETIC_DATA_DISCLAIMER_ACTUAL
