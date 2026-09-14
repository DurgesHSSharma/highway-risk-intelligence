"""Phase 11 deterministic, template-based risk-summary sentences.

Built entirely from the existing Phase 6 `predict_all_tasks` output (no new
computation) using the hedged phrasing the brief mandates: a classification
probability is always labeled as a MODEL probability/score attached to a
named class, never as a statement that the outcome will happen; a
regression output is always labeled as a model ESTIMATE, never as a
statement of what will actually occur.
"""

from __future__ import annotations

from app.schemas.decision_support import RiskSummaryOut
from app.schemas.predictions import (
    CostOverrunResult,
    FinalCostOverrunPctResult,
    FinalDelayDaysResult,
    SignificantDelayResult,
)


def _classification_sentence(
    proba: float | None, predicted_class: int | None, positive_label: str, negative_label: str
) -> str:
    if proba is None or predicted_class is None:
        return "Model probability unavailable for this class."
    label = positive_label if predicted_class == 1 else negative_label
    return f"The model assigns a probability of {proba:.1%} to the {positive_label} class (predicted class: {label})."


def build_risk_summary(
    significant_delay: SignificantDelayResult,
    final_delay_days: FinalDelayDaysResult,
    cost_overrun: CostOverrunResult,
    final_cost_overrun_pct: FinalCostOverrunPctResult,
) -> RiskSummaryOut:
    significant_delay_summary = _classification_sentence(
        significant_delay.probability_of_significant_delay,
        significant_delay.predicted_class,
        positive_label="significant-delay",
        negative_label="no significant delay",
    )

    if final_delay_days.predicted_final_delay_days is None:
        final_delay_days_summary = "Model-estimated final delay unavailable."
    else:
        final_delay_days_summary = (
            f"Model-estimated final delay: {final_delay_days.predicted_final_delay_days:.1f} days "
            "(total modeled project delay at completion, not days remaining)."
        )

    cost_overrun_summary = _classification_sentence(
        cost_overrun.probability_of_cost_overrun,
        cost_overrun.predicted_class,
        positive_label="cost-overrun",
        negative_label="no cost overrun",
    )

    if final_cost_overrun_pct.predicted_final_cost_overrun_pct is None:
        final_cost_overrun_pct_summary = "Model-estimated final cost overrun unavailable."
    else:
        final_cost_overrun_pct_summary = (
            "Model-estimated final cost overrun: "
            f"{final_cost_overrun_pct.predicted_final_cost_overrun_pct:.1f}% relative to the original "
            "contract value."
        )

    return RiskSummaryOut(
        significant_delay_summary=significant_delay_summary,
        final_delay_days_summary=final_delay_days_summary,
        cost_overrun_summary=cost_overrun_summary,
        final_cost_overrun_pct_summary=final_cost_overrun_pct_summary,
    )
