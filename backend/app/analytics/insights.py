"""Phase 14 deterministic executive insights. NO LLM is used anywhere in
this module (section 32 of the brief) -- every sentence is assembled from
already-computed Phase 14 aggregates using an f-string template, never a
fresh computation of its own and never free-text generation. Language is
deliberately hedged throughout: "observed", "model-attributed",
"associated", "indicates" -- never "causes", "guarantees", or "responsible
for".
"""

from __future__ import annotations

from app.analytics.drivers import TaskPortfolioDrivers
from app.analytics.historical import HistoricalOverview
from app.analytics.segments import SegmentEntry


def _top_eligible_by_historical_rate(segments: list[SegmentEntry], rate_attr: str) -> SegmentEntry | None:
    eligible = [s for s in segments if not s.small_sample and s.historical is not None]
    if not eligible:
        return None
    return max(eligible, key=lambda s: getattr(s.historical, rate_attr))


def generate_executive_insights(
    *,
    historical: HistoricalOverview,
    predicted_risk_level_counts: dict[str, int],
    predicted_scored_count: int,
    state_segments: list[SegmentEntry],
    project_type_segments: list[SegmentEntry],
    contractor_segments: list[SegmentEntry],
    drivers: list[TaskPortfolioDrivers],
) -> list[str]:
    insights: list[str] = []

    if historical.completed_project_count:
        insights.append(
            f"Historical significant-delay rate across {historical.completed_project_count} completed "
            f"projects is {historical.significant_delay_rate * 100:.1f}%, with an observed mean final delay "
            f"of {historical.mean_final_delay_days:.0f} days."
        )
        insights.append(
            f"Historical cost-overrun rate across {historical.completed_project_count} completed projects is "
            f"{historical.cost_overrun_rate * 100:.1f}%, with an observed mean final cost overrun of "
            f"{historical.mean_final_cost_overrun_pct:.1f}%."
        )

    if predicted_scored_count:
        high_or_critical = predicted_risk_level_counts.get("HIGH", 0) + predicted_risk_level_counts.get("CRITICAL", 0)
        insights.append(
            f"{high_or_critical} of {predicted_scored_count} currently scored projects "
            f"({high_or_critical / predicted_scored_count * 100:.1f}%) fall in the HIGH or CRITICAL "
            "model-predicted risk band, based on each project's latest available non-terminal snapshot."
        )

    top_state = _top_eligible_by_historical_rate(state_segments, "significant_delay_rate")
    if top_state and top_state.historical:
        insights.append(
            f"Among states meeting the minimum sample threshold (n>={top_state.min_sample_threshold}), "
            f"{top_state.value} shows the highest observed historical significant-delay rate "
            f"({top_state.historical.significant_delay_rate * 100:.1f}%, n={top_state.historical.project_count})."
        )

    top_type = _top_eligible_by_historical_rate(project_type_segments, "cost_overrun_rate")
    if top_type and top_type.historical:
        insights.append(
            f"Among project types meeting the minimum sample threshold (n>={top_type.min_sample_threshold}), "
            f"{top_type.value} shows the highest observed historical cost-overrun rate "
            f"({top_type.historical.cost_overrun_rate * 100:.1f}%, n={top_type.historical.project_count})."
        )

    top_contractor = _top_eligible_by_historical_rate(contractor_segments, "cost_overrun_rate")
    if top_contractor and top_contractor.historical:
        insights.append(
            f"Among contractors meeting the minimum sample threshold (n>={top_contractor.min_sample_threshold}), "
            f"{top_contractor.value} shows the highest observed historical cost-overrun rate "
            f"({top_contractor.historical.cost_overrun_rate * 100:.1f}%, "
            f"n={top_contractor.historical.project_count}) -- an observed pattern, not a causal claim."
        )

    delay_task_drivers = next((d for d in drivers if d.task_key == "significant_delay"), None)
    if delay_task_drivers and delay_task_drivers.drivers:
        top_driver = delay_task_drivers.drivers[0]
        insights.append(
            f"'{top_driver.feature}' is the strongest portfolio-wide model-attributed feature for "
            f"significant-delay classification (mean |SHAP| = {top_driver.mean_abs_shap:.4f}) in the Phase 5 "
            "saved global SHAP ranking -- a model-attributed pattern, not a causal driver."
        )

    return insights
