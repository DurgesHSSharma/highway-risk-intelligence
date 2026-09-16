"""Phase 17C deterministic response-text templates for "Ask HRI".

Every function here builds a sentence or two from ALREADY-COMPUTED tool
output (app.agent.tools) -- no free-form generation, no LLM. Mirrors the
exact style/hedging conventions app.decision_support.risk_summary already
established: a classification result is always phrased as a model
probability attached to a named class, a regression result as a model
ESTIMATE, and a hypothetical result is always explicitly labeled as such.
"""

from __future__ import annotations

from app.agent.entities import WhatIfIntent
from app.agent.tools import ProjectLookupResult
from app.decision_support.synthesizer import RiskSummaryResult
from app.rag.config import NOT_FOUND_MESSAGE
from app.schemas.predictions import SYNTHETIC_DATA_DISCLAIMER_ACTUAL, SYNTHETIC_DATA_DISCLAIMER_MODEL
from app.schemas.simulation import SIMULATION_DISCLAIMER
from app.simulation.service import SimulationResult


def render_project_answer(result: ProjectLookupResult) -> str:
    p = result.project
    lines = [
        f"{p.project_id} — {p.project_name} ({p.highway_number}, {p.state}, {p.project_type}).",
        f"Contractor: {p.contractor or 'not recorded'}. Length: {p.project_length_km:.1f} km. "
        f"Original contract value: {p.original_contract_value_inr_cr:.1f} Cr.",
        f"Planned {p.planned_start_date} to {p.planned_completion_date} ({p.planned_duration_months} months). "
        f"Current recorded status: {result.current_status}.",
        f"Data source: {p.data_provenance}. Archived: {'yes' if p.is_archived else 'no'}.",
    ]
    if result.snapshot_count == 0:
        lines.append("No monthly progress has been recorded for this project yet.")
    return " ".join(lines)


def render_risk_answer(result: RiskSummaryResult) -> str:
    if result.prediction_status == "actual_outcome":
        parts = [
            f"{result.project.project_id} ({result.project.reporting_month}) is a completed (terminal) snapshot, "
            "so this is the recorded ACTUAL outcome, not a model prediction:",
            result.risk_summary.significant_delay_summary,
            result.risk_summary.final_delay_days_summary,
            result.risk_summary.cost_overrun_summary,
            result.risk_summary.final_cost_overrun_pct_summary,
        ]
        return " ".join(parts)

    parts = [
        f"{result.project.project_id} ({result.project.reporting_month}) — model-based risk assessment:",
        result.risk_summary.significant_delay_summary,
        result.risk_summary.final_delay_days_summary,
    ]
    sig_drivers = next((d for d in result.risk_drivers if d.task_key == "significant_delay"), None)
    if sig_drivers and sig_drivers.top_drivers:
        top = sig_drivers.top_drivers[0]
        parts.append(
            f"The top model-attributed driver for the significant-delay prediction is `{top.feature}` "
            f"({top.direction} risk; association only, not a causal claim)."
        )
    if result.evidence and any(not e.not_found for e in result.evidence):
        parts.append("Related documentary evidence was also found (see citations).")
    return " ".join(parts)


def render_portfolio_answer(shape: str, data) -> str:
    if shape == "overview":
        hist = data.historical
        pred = data.predicted
        parts = [
            f"Portfolio: {data.total_projects} projects.",
            f"Historical (actual, completed projects): {hist.significant_delay_rate:.1%} experienced a "
            f"significant delay, {hist.cost_overrun_rate:.1%} experienced a cost overrun "
            f"(n={hist.completed_project_count}).",
        ]
        if pred.status == "ok":
            level_summary = ", ".join(f"{level}: {count}" for level, count in sorted(pred.risk_level_counts.items()))
            parts.append(
                f"Model-predicted current risk (from the batch-scored portfolio cache, n={pred.scored_project_count}): "
                f"{level_summary}."
            )
        else:
            parts.append("Model-predicted current risk is not available yet (the portfolio scoring cache hasn't been generated).")
        return " ".join(parts)

    if shape == "risk_projects":
        if data.cache_status != "ok":
            return "Model-predicted risk data is not available yet (the portfolio scoring cache hasn't been generated)."
        if not data.items:
            return "No projects currently match that risk level."
        names = ", ".join(f"{r.project_id} ({r.risk_level}, score {r.risk_score:.0f})" for r in data.items[:10])
        return f"{data.total} project(s) match (model-predicted risk, not a certainty): {names}."

    if shape == "segments":
        if not data.entries:
            return f"No segment data available for dimension '{data.dimension}'."
        lines = []
        for e in data.entries[:10]:
            hist_txt = (
                f"historical significant-delay rate {e.historical.significant_delay_rate:.1%} (n={e.historical.project_count})"
                if e.historical
                else "no historical data"
            )
            small = " [small sample]" if e.small_sample else ""
            lines.append(f"{e.value}{small}: {hist_txt}")
        return f"Risk distribution by {data.dimension.replace('_', ' ')}: " + "; ".join(lines) + "."

    return "No portfolio data available for that query."


def render_whatif_answer(result: SimulationResult, whatif: WhatIfIntent) -> str:
    override = result.overrides[0] if result.overrides else None
    baseline = result.baseline_predictions
    simulated = result.simulated_predictions
    override_text = (
        f"`{override.field}` moved from {override.original_value:.2f} to {override.simulated_value:.2f}"
        if override
        else f"`{whatif.field}` was adjusted"
    )
    return (
        f"Hypothetical, illustrative only — {override_text}. Under this hypothetical model re-scoring, predicted "
        f"final delay moved from {baseline['final_delay_days'].predicted_final_delay_days:.1f} to "
        f"{simulated['final_delay_days'].predicted_final_delay_days:.1f} days, and predicted final cost overrun "
        f"moved from {baseline['final_cost_overrun_pct'].predicted_final_cost_overrun_pct:.1f}% to "
        f"{simulated['final_cost_overrun_pct'].predicted_final_cost_overrun_pct:.1f}%. {SIMULATION_DISCLAIMER}"
    )


def render_document_answer(extractive_answer: str) -> str:
    return extractive_answer


__all__ = [
    "render_project_answer",
    "render_risk_answer",
    "render_portfolio_answer",
    "render_whatif_answer",
    "render_document_answer",
    "NOT_FOUND_MESSAGE",
    "SYNTHETIC_DATA_DISCLAIMER_MODEL",
    "SYNTHETIC_DATA_DISCLAIMER_ACTUAL",
]
