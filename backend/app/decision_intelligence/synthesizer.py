"""Phase 15 Decision Intelligence synthesizer for
GET /projects/{project_id}/decision-intelligence?reporting_month=YYYY-MM:

    Phase 11 run_risk_summary (called ONCE, as a black box)
           |
           +-------------------------+
           |                         |
           v                         v
    Phase 14 risk positioning   Phase 14 peer context
    (portfolio_prediction_cache, (segment_report, state/
     compute_portfolio_risk_scores) project_type/contractor)
           |                         |
           +-----------+-------------+
                       |
                       v
              driver alignment
       (live top SHAP driver per task vs.
        Phase 14 portfolio-wide top driver)
                       |
                       v
       Phase 15 portfolio_context recommendations
       (peer-elevated-risk rule + driver-divergence rule)
                       |
                       v
       merge with Phase 11's 4 recommendation families,
       cap at MAX_TOTAL_RECOMMENDATIONS (Phase 11's constant, reused)
                       |
                       v
           Decision Intelligence result

Every step reuses an existing Phase 11/14 service unchanged -- see
docs/DECISION_INTELLIGENCE.md for the full design. This module never
retrains/refits a model, never recomputes RAG/embeddings, never reruns
Phase 9 contradiction detection, and never triggers Phase 14 batch scoring.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.analytics.drivers import ShapArtifactMissingError, portfolio_drivers
from app.analytics.historical import HistoricalOverview, historical_overview
from app.decision_intelligence.driver_alignment import (
    NOT_COMPARABLE_NOTE,
    TaskDriverAlignment,
    compute_driver_alignment,
)
from app.decision_intelligence.portfolio_context import (
    CURRENT_RISK_BASIS_NOTE,
    PERCENTILE_DEFINITION,
    PORTFOLIO_RELATIVE_DISCLAIMER,
    PeerContextEntry,
    RiskPositioning,
    get_peer_context,
    get_risk_positioning,
)
from app.decision_intelligence.recommendations import generate_portfolio_context_recommendations
from app.decision_support.recommendations import MAX_TOTAL_RECOMMENDATIONS
from app.decision_support.synthesizer import (
    ProjectNotFoundError,
    RiskSummaryResult,
    SnapshotNotFoundError,
    run_risk_summary,
)
from app.schemas.decision_intelligence import DecisionIntelligenceRecommendationOut

__all__ = [
    "DecisionIntelligenceResult",
    "ProjectNotFoundError",
    "SnapshotNotFoundError",
    "run_decision_intelligence",
]


@dataclass(frozen=True)
class DecisionIntelligenceResult:
    risk_summary: RiskSummaryResult
    risk_positioning: RiskPositioning
    peer_context: dict[str, PeerContextEntry]
    driver_alignment: list[TaskDriverAlignment]
    recommended_reviews: list[DecisionIntelligenceRecommendationOut]


def _merge_recommendations(
    phase11_recommendations, phase15_recommendations: list[DecisionIntelligenceRecommendationOut]
) -> list[DecisionIntelligenceRecommendationOut]:
    """Preserves Phase 11's recommendation text/basis_type/basis_detail
    UNCHANGED -- the only reason to re-wrap them in
    `DecisionIntelligenceRecommendationOut` is that Phase 15's response
    schema's `basis_type` Literal has a 5th value (`portfolio_context`)
    Phase 11's own schema doesn't carry. Then appends Phase 15's own
    recommendations and applies Phase 11's UNCHANGED
    `MAX_TOTAL_RECOMMENDATIONS` cap to the combined list -- never a second,
    redefined cap."""
    merged = [
        DecisionIntelligenceRecommendationOut(text=r.text, basis_type=r.basis_type, basis_detail=r.basis_detail)
        for r in phase11_recommendations
    ]
    merged.extend(phase15_recommendations)
    return merged[:MAX_TOTAL_RECOMMENDATIONS]


def run_decision_intelligence(db: Session, project_id: str, reporting_month: str) -> DecisionIntelligenceResult:
    # Phase 11, called ONCE as a black box. Raises ProjectNotFoundError /
    # SnapshotNotFoundError / FeatureConstructionError -- never caught here,
    # propagated to the router exactly like Phase 11's own router does.
    risk_summary_result = run_risk_summary(db, project_id, reporting_month)

    risk_positioning = get_risk_positioning(db, project_id)
    peer_context = get_peer_context(
        db,
        state=risk_summary_result.project.state,
        project_type=risk_summary_result.project.project_type,
        contractor=risk_summary_result.project.contractor,
    )

    # Phase 14's saved global SHAP artifact, reused verbatim (see
    # app.analytics.drivers) -- never recomputed. If the committed artifact
    # file is missing, portfolio_drivers() raises ShapArtifactMissingError;
    # degrade the portfolio side of driver alignment gracefully (every
    # task's portfolio_top_driver/matches_serving_model/comparable/agreement
    # come back None/False/None -- the exact same degradation
    # compute_driver_alignment already applies to the LIVE side for a
    # terminal snapshot) rather than letting this 500 the whole endpoint.
    # Phase 14's portfolio_drivers() implementation itself is never touched.
    try:
        portfolio_task_drivers = portfolio_drivers()
    except ShapArtifactMissingError:
        portfolio_task_drivers = []
    alignment = compute_driver_alignment(risk_summary_result.risk_drivers, portfolio_task_drivers)

    # Portfolio-context recommendations (5th family) must never be derived
    # for a terminal-snapshot REQUEST (master-prompt section 8), even though
    # risk_positioning itself is keyed off the project's own cached latest
    # non-terminal snapshot and can still be "ok"/HIGH/CRITICAL here -- gated
    # on the actual requested snapshot's own terminal flag (Phase 11's
    # ProjectInfo.is_terminal_snapshot), never inferred from the portfolio
    # cache. Phase 11's own 4 recommendation families are untouched either
    # way (see _merge_recommendations below).
    if risk_summary_result.project.is_terminal_snapshot:
        phase15_recommendations: list[DecisionIntelligenceRecommendationOut] = []
    else:
        # Phase 14's historical overview never depends on the prediction
        # cache (it reads only terminal snapshot rows), so it is always
        # available for the peer-elevated-risk rule -- that rule itself only
        # ever fires when risk_positioning.risk_level is HIGH/CRITICAL,
        # which is None (so the rule is a no-op) whenever
        # risk_positioning.status != "ok".
        portfolio_hist: HistoricalOverview = historical_overview(db)
        phase15_recommendations = generate_portfolio_context_recommendations(
            risk_level=risk_positioning.risk_level,
            peer_context=peer_context,
            portfolio_hist=portfolio_hist,
            alignment=alignment,
        )

    recommended_reviews = _merge_recommendations(risk_summary_result.recommendations, phase15_recommendations)

    return DecisionIntelligenceResult(
        risk_summary=risk_summary_result,
        risk_positioning=risk_positioning,
        peer_context=peer_context,
        driver_alignment=alignment,
        recommended_reviews=recommended_reviews,
    )


# Re-exported so callers (the router, tests) can attach the fixed
# documentation strings to the response without re-deriving them.
__all__ += [
    "PERCENTILE_DEFINITION",
    "PORTFOLIO_RELATIVE_DISCLAIMER",
    "CURRENT_RISK_BASIS_NOTE",
    "NOT_COMPARABLE_NOTE",
]
