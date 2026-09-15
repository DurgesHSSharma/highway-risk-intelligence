"""Phase 15 fifth recommendation family: `portfolio_context`.

Two independent sub-rules, each firing ONLY when its own concrete grounding
condition is actually true for this request -- no rule fires "by default"
(same evidence-first convention Phase 11's four existing families already
follow, see app.decision_support.recommendations). This module does NOT
touch Phase 11's recommendation logic; it only produces additional
`DecisionIntelligenceRecommendationOut` items that
app.decision_intelligence.synthesizer merges with Phase 11's unchanged
output.

## PEER_ELEVATION_THRESHOLD_PP -- real-data-derived, not invented

Computed from a real run of `app.analytics.historical.historical_overview`
and `app.analytics.segments.segment_report` against the committed database
(see docs/DECISION_INTELLIGENCE.md "Real observed data used for threshold
selection" for the full reproducible analysis):

Across the 50 state/project_type/contractor segments that clear their
Phase 14 `MIN_SAMPLE_THRESHOLDS` (small_sample=False), the peer-minus-
portfolio HISTORICAL-rate spread observed was:

  - significant-delay rate: min -49.25pp, max +50.75pp, 75th percentile +13.25pp
  - cost-overrun rate:      min -38.25pp, max +61.75pp, 75th percentile +13.72pp

10 percentage points (0.10) is a round, human-interpretable threshold that
sits just below both metrics' 75th percentile -- it flags roughly the most
elevated quartile of qualifying peer segments (14-16 of 50, ~28-32%), not
the broad near-portfolio-average middle, while remaining well inside the
observed range on both sides (never trivially always-true or never-true).
"""

from __future__ import annotations

from app.analytics.historical import HistoricalOverview
from app.decision_intelligence.driver_alignment import TaskDriverAlignment
from app.decision_intelligence.portfolio_context import PeerContextEntry
from app.schemas.decision_intelligence import DecisionIntelligenceRecommendationOut

PEER_ELEVATION_THRESHOLD_PP = 0.10

MAX_PEER_ELEVATION_RECOMMENDATIONS = 2
MAX_DRIVER_DIVERGENCE_RECOMMENDATIONS = 2

_ELEVATED_RISK_LEVELS = ("HIGH", "CRITICAL")

_TASK_DISPLAY_NAMES = {
    "significant_delay": "significant-delay",
    "final_delay_days": "delay-duration",
    "cost_overrun": "cost-overrun",
    "final_cost_overrun_pct": "cost-overrun-percentage",
}

_DIMENSION_LABELS = {"state": "state", "project_type": "project type", "contractor": "contractor"}


def _peer_elevation_candidates(
    peer_context: dict[str, PeerContextEntry], portfolio_hist: HistoricalOverview
) -> list[tuple[str, str, str, float, float, float, int]]:
    """Returns (dimension, value, metric_label, peer_rate, portfolio_rate,
    spread, sample_size) tuples for every peer group that both clears its
    Phase 14 sample threshold (small_sample=False) AND exceeds the
    portfolio-wide historical rate by >= PEER_ELEVATION_THRESHOLD_PP on at
    least one of the two historical metrics. Sorted by spread, largest
    first, so the most elevated candidates are surfaced first under the cap."""
    candidates: list[tuple[str, str, str, float, float, float, int]] = []
    for dimension, entry in peer_context.items():
        if entry.status != "ok" or entry.segment is None:
            continue
        seg = entry.segment
        if seg.small_sample or seg.historical is None:
            continue

        delay_spread = seg.historical.significant_delay_rate - portfolio_hist.significant_delay_rate
        if delay_spread >= PEER_ELEVATION_THRESHOLD_PP:
            candidates.append(
                (
                    dimension,
                    seg.value,
                    "significant-delay rate",
                    seg.historical.significant_delay_rate,
                    portfolio_hist.significant_delay_rate,
                    delay_spread,
                    seg.historical.project_count,
                )
            )

        cost_spread = seg.historical.cost_overrun_rate - portfolio_hist.cost_overrun_rate
        if cost_spread >= PEER_ELEVATION_THRESHOLD_PP:
            candidates.append(
                (
                    dimension,
                    seg.value,
                    "cost-overrun rate",
                    seg.historical.cost_overrun_rate,
                    portfolio_hist.cost_overrun_rate,
                    cost_spread,
                    seg.historical.project_count,
                )
            )

    candidates.sort(key=lambda c: -c[5])
    return candidates


def peer_elevated_risk_recommendations(
    risk_level: str | None,
    peer_context: dict[str, PeerContextEntry],
    portfolio_hist: HistoricalOverview,
) -> list[DecisionIntelligenceRecommendationOut]:
    """Fires only when ALL of: (1) this project's portfolio-relative
    risk_level is HIGH or CRITICAL, (2) at least one peer group clears its
    sample threshold, (3) that peer group's historical significant-delay
    OR cost-overrun rate exceeds the portfolio-wide rate by
    >= PEER_ELEVATION_THRESHOLD_PP -- see module docstring for the real
    -data threshold derivation."""
    if risk_level not in _ELEVATED_RISK_LEVELS:
        return []

    candidates = _peer_elevation_candidates(peer_context, portfolio_hist)

    out: list[DecisionIntelligenceRecommendationOut] = []
    for dimension, value, metric, peer_rate, portfolio_rate, spread, n in candidates[:MAX_PEER_ELEVATION_RECOMMENDATIONS]:
        dim_label = _DIMENSION_LABELS[dimension]
        out.append(
            DecisionIntelligenceRecommendationOut(
                text=(
                    f"This project's portfolio-relative risk level is {risk_level}. Its {dim_label} peer "
                    f"group ('{value}', n={n}) has a historical {metric} of {peer_rate * 100:.1f}%, "
                    f"{spread * 100:+.1f} percentage points above the portfolio-wide rate of "
                    f"{portfolio_rate * 100:.1f}% -- it may be worth reviewing whether factors common to "
                    f"this {dim_label} group are relevant here, or verifying this project's own figures "
                    "against that pattern."
                ),
                basis_type="portfolio_context",
                basis_detail=(
                    f"Peer-elevated-risk: {dimension}='{value}' historical {metric} {peer_rate * 100:.1f}% "
                    f"vs. portfolio-wide {portfolio_rate * 100:.1f}% (n={n}, threshold="
                    f"{PEER_ELEVATION_THRESHOLD_PP * 100:.0f}pp)."
                ),
            )
        )
    return out


def driver_divergence_recommendations(
    alignment: list[TaskDriverAlignment],
) -> list[DecisionIntelligenceRecommendationOut]:
    """Fires only when comparable=true AND agreement=false AND both
    drivers are available. `comparable` is already false for
    `cost_overrun`/`final_cost_overrun_pct` whenever
    `matches_serving_model=false` (see
    app.decision_intelligence.driver_alignment), so this rule structurally
    cannot fire for those two tasks under that condition -- no separate
    task-key exclusion is needed."""
    out: list[DecisionIntelligenceRecommendationOut] = []
    for a in alignment:
        if not a.comparable or a.agreement is not False:
            continue
        if a.live_top_driver_identity is None or a.portfolio_top_driver_identity is None:
            continue

        task_display = _TASK_DISPLAY_NAMES[a.task_key]
        out.append(
            DecisionIntelligenceRecommendationOut(
                text=(
                    f"For the {task_display} prediction, this project's live top model-attributed driver "
                    f"(`{a.live_top_driver}`) differs from the portfolio-wide top driver "
                    f"(`{a.portfolio_top_driver}`) -- consider investigating why this project's own risk "
                    "driver diverges from the broader portfolio pattern for this task (association only, "
                    "not a causal claim)."
                ),
                basis_type="portfolio_context",
                basis_detail=(
                    f"Driver divergence for {a.task_key}: live driver identity="
                    f"'{a.live_top_driver_identity}', portfolio-wide driver identity="
                    f"'{a.portfolio_top_driver_identity}'."
                ),
            )
        )
        if len(out) >= MAX_DRIVER_DIVERGENCE_RECOMMENDATIONS:
            break
    return out


def generate_portfolio_context_recommendations(
    risk_level: str | None,
    peer_context: dict[str, PeerContextEntry],
    portfolio_hist: HistoricalOverview,
    alignment: list[TaskDriverAlignment],
) -> list[DecisionIntelligenceRecommendationOut]:
    out: list[DecisionIntelligenceRecommendationOut] = []
    out.extend(peer_elevated_risk_recommendations(risk_level, peer_context, portfolio_hist))
    out.extend(driver_divergence_recommendations(alignment))
    return out
