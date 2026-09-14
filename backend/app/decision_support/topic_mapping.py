"""Phase 11 REPAIR: maps a raw predictor-column identity (never a SHAP
ColumnTransformer-prefixed or one-hot-expanded name) to a short
natural-language topic phrase, used to generate Phase 8 RAG evidence
queries from the LIVE top SHAP drivers of a specific snapshot -- see
`app.decision_support.synthesizer.generate_evidence_queries`.

Every one of the 45 `scripts.prepare_features.PREDICTOR_COLUMNS` is covered
so lookup never falls through silently. A topic phrase is a best-effort,
deterministic guess at what a highway-policy document corpus might call
that concept -- it does NOT guarantee a match: the existing Phase 8
relevance threshold decides that, and "Not found in the available
documents" remains the correct, honest result for a topic the small real
corpus does not cover (see docs/RAG_SYSTEM.md).
"""

from __future__ import annotations

FEATURE_TOPIC_MAP: dict[str, str] = {
    # Raw static numeric
    "project_length_km": "highway project length",
    "original_contract_value_inr_cr": "project contract value outlay",
    "planned_duration_months": "project duration",
    "months_since_start": "project progress duration",
    # Raw categorical (raw column identity, not a specific one-hot level)
    "state": "state highway project",
    "project_type": "highway project type",
    "contractor": "contractor performance",
    # Raw snapshot numeric -- progress
    "planned_physical_progress_pct": "physical progress project delay",
    "actual_physical_progress_pct": "physical progress project delay",
    "physical_progress_variance_pct": "physical progress project delay",
    "planned_financial_progress_pct": "financial progress expenditure",
    "actual_financial_progress_pct": "financial progress expenditure",
    "financial_progress_variance_pct": "financial progress expenditure",
    # Raw snapshot numeric -- cost
    "planned_cost_to_date_inr_cr": "project expenditure cost",
    "actual_expenditure_inr_cr": "project expenditure cost",
    "actual_cost_to_date_inr_cr": "project expenditure cost",
    "material_cost_inr_cr": "project cost material labour equipment",
    "labour_cost_inr_cr": "project cost material labour equipment",
    "equipment_cost_inr_cr": "project cost material labour equipment",
    "variation_cost_inr_cr": "cost variation project",
    "delay_related_cost_inr_cr": "delay related cost overrun",
    "contractor_productivity_factor": "contractor productivity performance",
    # Raw snapshot numeric -- delay factors
    "land_acquisition_delay_days": "land acquisition delay",
    "utility_shifting_delay_days": "utility shifting delay",
    "environment_clearance_delay_days": "environment clearance delay",
    "material_delay_days": "material delay",
    "labour_shortage_days": "labour shortage delay",
    "equipment_unavailability_days": "equipment unavailability delay",
    "weather_disruption_days": "weather disruption delay",
    "traffic_diversion_delay_days": "traffic diversion delay",
    "design_change_delay_days": "design change delay",
    "approval_delay_days": "approval delay clearance",
    # Engineered
    "expenditure_gap_inr_cr": "cost overrun project expenditure",
    "cost_tracking_gap_inr_cr": "cost overrun project expenditure",
    "delay_factor_count": "project delay factors",
    "delay_factor_severity": "project delay factors",
    "project_age_ratio": "project schedule delay",
    "months_to_planned_completion": "project schedule delay",
    "schedule_pressure": "project schedule delay",
    "progress_efficiency": "physical progress project delay",
    "cost_growth_rate": "cost overrun growth",
    "recent_progress_trend_3m": "physical progress project delay",
    "recent_cost_trend_3m": "cost overrun expenditure trend",
    "consecutive_underperforming_months": "project delay underperformance",
    "recent_adverse_events_3m": "project delay factors",
}


def topic_for_raw_predictor_column(raw_predictor_column: str) -> str:
    """Returns the mapped topic phrase, or a humanized fallback (never
    raises) for a column name not in the map -- defensive only, every real
    PREDICTOR_COLUMNS entry is covered above."""
    return FEATURE_TOPIC_MAP.get(raw_predictor_column, raw_predictor_column.replace("_", " "))
