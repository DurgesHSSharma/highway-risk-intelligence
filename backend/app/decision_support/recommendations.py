"""Phase 11 evidence-first recommendation generator (REPAIRED for live
per-instance SHAP drivers and the auto-derived illustrative scenario).

Every recommendation is produced by a rule that only fires when a concrete
grounding condition is actually true for this request -- a live SHAP driver
that actually ranks top for this project's task models, a documentary
citation that was actually retrieved, a potential inconsistency that Phase
9 actually flagged, or the illustrative scenario that was actually
constructed. No rule fires "by default"; an unsupported recommendation is
never generated (see docs/DECISION_SUPPORT.md "Recommendation generation").

Wording is deliberately hedged and human-in-the-loop: every sentence is
phrased as something to review/verify/investigate, never as a command that
will be executed automatically, and never as a claim that acting on it will
definitely improve the project's outcome. The illustrative-scenario
recommendation is explicitly labeled "illustrative, not a recommendation".
"""

from __future__ import annotations

from app.decision_support.evidence import EvidenceQueryResult
from app.decision_support.scenario import IllustrativeScenario
from app.decision_support.shap_explainer import TaskRiskDrivers, driver_identity
from app.schemas.decision_support import RecommendationOut

MAX_MODEL_DRIVER_RECOMMENDATIONS = 3
MAX_INCONSISTENCY_RECOMMENDATIONS = 3
MAX_TOTAL_RECOMMENDATIONS = 8

_TASK_DISPLAY_NAMES = {
    "significant_delay": "significant-delay",
    "final_delay_days": "delay-duration",
    "cost_overrun": "cost-overrun",
    "final_cost_overrun_pct": "cost-overrun-percentage",
}


def _model_driver_recommendations(risk_drivers: list[TaskRiskDrivers]) -> list[RecommendationOut]:
    seen: dict[str, list[str]] = {}
    for drivers in risk_drivers:
        if not drivers.top_drivers:
            continue
        top = drivers.top_drivers[0]
        identity = driver_identity(top.feature, top.raw_feature)
        seen.setdefault(identity, []).append(_TASK_DISPLAY_NAMES[drivers.task_key])

    out: list[RecommendationOut] = []
    for identity, tasks in seen.items():
        task_list = ", ".join(sorted(set(tasks)))
        out.append(
            RecommendationOut(
                text=(
                    f"Review `{identity}` for this project -- live SHAP analysis of this specific "
                    f"snapshot places top importance on it for the {task_list} prediction(s) "
                    "(model-attributed driver, association only, not a causal claim)."
                ),
                basis_type="model_driver",
                basis_detail=f"Live per-instance top-ranked SHAP feature for: {task_list}.",
            )
        )
        if len(out) >= MAX_MODEL_DRIVER_RECOMMENDATIONS:
            break
    return out


def _documentary_evidence_recommendations(evidence: list[EvidenceQueryResult]) -> list[RecommendationOut]:
    out: list[RecommendationOut] = []
    for item in evidence:
        if item.not_found or not item.results:
            continue
        citations = ", ".join(r.citation() for r in item.results)
        out.append(
            RecommendationOut(
                text=(
                    f"Verify the figures relevant to '{item.query}' against the cited source "
                    f"document(s): {citations}."
                ),
                basis_type="documentary_evidence",
                basis_detail=f"Retrieved documentary evidence for query '{item.query}': {citations}.",
            )
        )
    return out


def _inconsistency_recommendations(inconsistencies: list) -> list[RecommendationOut]:
    """One recommendation per unique (document pair, claim type) -- several
    Phase 9 flags can share the same document/page/claim_type (different
    underlying claim values), which would otherwise produce near-duplicate
    recommendation text. Their flag_ids are merged into one basis_detail."""
    grouped: dict[tuple, list[str]] = {}
    for flag in inconsistencies:
        key = (flag.document_a, flag.page_a, flag.document_b, flag.page_b, flag.claim_type)
        grouped.setdefault(key, []).append(flag.flag_id)

    out: list[RecommendationOut] = []
    for (doc_a, page_a, doc_b, page_b, claim_type), flag_ids in grouped.items():
        out.append(
            RecommendationOut(
                text=(
                    f"Investigate the reporting-period or scope difference between "
                    f"{doc_a} (p. {page_a}) and {doc_b} (p. {page_b}) for the {claim_type} figure -- a "
                    "potential inconsistency requiring verification, not a confirmed issue with either "
                    "source."
                ),
                basis_type="potential_inconsistency",
                basis_detail=f"Phase 9 flag(s): {', '.join(flag_ids)}.",
            )
        )
        if len(out) >= MAX_INCONSISTENCY_RECOMMENDATIONS:
            break
    return out


def _scenario_recommendation(scenario: IllustrativeScenario | None) -> list[RecommendationOut]:
    if scenario is None:
        return []

    baseline_delay = scenario.baseline_predictions["final_delay_days"].predicted_final_delay_days
    simulated_delay = scenario.simulated_predictions["final_delay_days"].predicted_final_delay_days
    baseline_cost_pct = scenario.baseline_predictions["final_cost_overrun_pct"].predicted_final_cost_overrun_pct
    simulated_cost_pct = scenario.simulated_predictions["final_cost_overrun_pct"].predicted_final_cost_overrun_pct

    out = [
        RecommendationOut(
            text=(
                f"Illustrative, not a recommendation: under this hypothetical model re-scoring "
                f"(`{scenario.field}` moved to its Phase 4 training-average value of "
                f"{scenario.reference_value:.3f}), predicted final delay moved from "
                f"{baseline_delay:.1f} to {simulated_delay:.1f} days and predicted final cost overrun "
                f"moved from {baseline_cost_pct:.1f}% to {simulated_cost_pct:.1f}%."
            ),
            basis_type="scenario",
            basis_detail=(
                f"Illustrative what-if scenario derived from the live top significant_delay SHAP "
                f"driver (`{scenario.field}`), reused via Phase 10's simulation service."
            ),
        )
    ]
    for warning in scenario.extrapolation_warnings:
        out.append(
            RecommendationOut(
                text=(
                    f"Treat the illustrative scenario result with added caution: the reference value "
                    f"used for `{warning.field}` ({warning.simulated_value}) falls outside the Phase 4 "
                    f"training range ({warning.training_min} to {warning.training_max})."
                ),
                basis_type="scenario",
                basis_detail=f"Extrapolation warning for `{warning.field}`.",
            )
        )
    return out


def generate_recommendations(
    risk_drivers: list[TaskRiskDrivers],
    evidence: list[EvidenceQueryResult],
    inconsistencies: list,
    scenario: IllustrativeScenario | None,
) -> list[RecommendationOut]:
    recommendations: list[RecommendationOut] = []
    recommendations.extend(_model_driver_recommendations(risk_drivers))
    recommendations.extend(_documentary_evidence_recommendations(evidence))
    recommendations.extend(_inconsistency_recommendations(inconsistencies))
    recommendations.extend(_scenario_recommendation(scenario))
    return recommendations[:MAX_TOTAL_RECOMMENDATIONS]
