"""Phase 15: project-specific portfolio context, built entirely from
existing Phase 14 data/services -- never a second risk-scoring or
segmentation implementation.

Two independent concerns, returned separately (mirrors the master-prompt's
own section split):

1. `get_risk_positioning` -- this project's composite risk score,
   portfolio-relative risk level, and percentile within the current scored
   cohort. Requires the project to have a row in
   `portfolio_prediction_cache` (app.analytics.batch_scoring); NEVER
   triggers batch scoring itself (see the module docstring in
   app.analytics.batch_scoring and docs/ADVANCED_ANALYTICS.md "Batch
   scoring architecture").
2. `get_peer_context` -- state / project_type / contractor peer-group
   context, reusing `app.analytics.segments.segment_report` directly. This
   does NOT require the prediction cache: `segment_report`'s HISTORICAL
   component is computed purely from terminal snapshot rows, so a peer
   entry's `historical` field is populated even when
   `risk_positioning.status != "ok"` (its `predicted` field degrades to
   `None` exactly as Phase 14's own `segment_report` already does when the
   cache is empty -- never reimplemented here).

Percentile definition (mandatory, exact -- see docs/DECISION_INTELLIGENCE.md
"Portfolio percentile exact definition"):

    percentile = 100 * count(projects in the current scored cohort with
    composite_risk_score <= this project's score) / cohort_size

A HIGHER percentile means HIGHER modeled risk relative to the current
cohort. This is the ONLY percentile methodology used anywhere in this
package.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.batch_scoring import get_cache_metadata
from app.analytics.portfolio_service import CACHE_MISSING_MESSAGE
from app.analytics.risk_score import RiskScoreCohortMetadata, compute_portfolio_risk_scores
from app.analytics.segments import DIMENSIONS, SegmentEntry, segment_report
from app.db.models import PortfolioPredictionCache

PROJECT_NOT_IN_CACHE_MESSAGE = (
    "This project does not have a row in the current portfolio prediction cache. This "
    "can happen if scripts/batch_score_portfolio.py was run before this project existed "
    "in the loaded database, or if this project has zero eligible non-terminal snapshots. "
    "Portfolio-relative risk positioning is unavailable for it until the cache is "
    "regenerated -- see docs/ADVANCED_ANALYTICS.md 'Refresh process'. Peer-group context "
    "below is unaffected (it does not depend on this project's own cache row)."
)

PERCENTILE_DEFINITION = (
    "percentile = 100 * count(projects in the current scored cohort with "
    "composite_risk_score <= this project's score) / cohort_size. A HIGHER percentile "
    "means HIGHER modeled risk relative to the current cohort. This is the only "
    "percentile methodology used in this response."
)

PORTFOLIO_RELATIVE_DISCLAIMER = (
    "This risk level/band is PORTFOLIO-RELATIVE: it is assigned by this project's "
    "composite-risk-score quartile position within the currently scored synthetic cohort "
    "(see docs/ADVANCED_ANALYTICS.md 'Risk score formula, weights, thresholds, "
    "limitations'). It is NOT an official NHAI threshold, NOT an industry threshold, NOT "
    "a validated operational threshold, NOT a safety threshold, and NOT an intervention "
    "threshold."
)

CURRENT_RISK_BASIS_NOTE = (
    "This project's composite risk score and percentile are computed from its latest "
    "PRE-COMPLETION (non-terminal) reporting-month snapshot, cached by "
    "scripts/batch_score_portfolio.py -- not a live 'as of today' snapshot. Every project "
    "in this synthetic corpus is simulated through to completion, so there is no "
    "genuinely 'still ongoing' project in this dataset: current ongoing-project risk is "
    "unavailable in the synthetic corpus. See docs/ADVANCED_ANALYTICS.md 'Current "
    "predicted risk' for the full definition, reused unchanged from Phase 14."
)

UNAVAILABLE_NO_VALUE_REASON = "This project has no recorded value for this dimension."
UNAVAILABLE_NOT_IN_SEGMENT_REPORT_REASON = (
    "This value does not appear in the current segment report (zero historical or "
    "predicted rows for it in the currently loaded cohort)."
)


@dataclass(frozen=True)
class RiskPositioning:
    status: str  # "ok" | "cache_unavailable" | "project_not_in_cache"
    message: str | None
    cache_computed_at: str | None
    cohort_size: int | None
    composite_risk_score: float | None
    risk_level: str | None
    percentile: float | None
    delay_risk: float | None
    cost_risk: float | None
    risk_level_thresholds: dict[str, float] | None


@dataclass(frozen=True)
class PeerContextEntry:
    dimension: str
    status: str  # "ok" | "unavailable"
    reason: str | None
    value: str | None
    segment: SegmentEntry | None


def _computed_at_str(computed_at) -> str:
    return computed_at.isoformat() if hasattr(computed_at, "isoformat") else str(computed_at)


def _empty_risk_positioning(status: str, message: str, **overrides) -> RiskPositioning:
    base = dict(
        status=status,
        message=message,
        cache_computed_at=None,
        cohort_size=None,
        composite_risk_score=None,
        risk_level=None,
        percentile=None,
        delay_risk=None,
        cost_risk=None,
        risk_level_thresholds=None,
    )
    base.update(overrides)
    return RiskPositioning(**base)


def get_risk_positioning(db: Session, project_id: str) -> RiskPositioning:
    """Reuses `app.analytics.batch_scoring.get_cache_metadata` and
    `app.analytics.risk_score.compute_portfolio_risk_scores` directly --
    never a second risk-scoring implementation, and never a fallback to
    live per-project inference. Reads the FULL cache cohort once (bounded
    at the ~400-project scale this project operates at -- see
    docs/ADVANCED_ANALYTICS.md 'Performance considerations'), never a
    per-project query loop."""
    cache_meta = get_cache_metadata(db)
    if cache_meta is None:
        return _empty_risk_positioning("cache_unavailable", CACHE_MISSING_MESSAGE)

    cache_rows = list(db.execute(select(PortfolioPredictionCache)).scalars().all())
    risk_results, metadata = compute_portfolio_risk_scores(cache_rows)
    this_result = next((r for r in risk_results if r.project_id == project_id), None)

    if this_result is None:
        return _empty_risk_positioning(
            "project_not_in_cache",
            PROJECT_NOT_IN_CACHE_MESSAGE,
            cache_computed_at=_computed_at_str(cache_meta["computed_at"]),
            cohort_size=len(cache_rows),
        )

    scores = [r.composite_risk_score for r in risk_results]
    count_le = sum(1 for s in scores if s <= this_result.composite_risk_score)
    percentile = 100.0 * count_le / len(scores)

    assert metadata is not None  # non-empty cache_rows guarantees metadata (see risk_score.py)
    return RiskPositioning(
        status="ok",
        message=None,
        cache_computed_at=_computed_at_str(cache_meta["computed_at"]),
        cohort_size=metadata.cohort_size,
        composite_risk_score=this_result.composite_risk_score,
        risk_level=this_result.risk_level,
        percentile=percentile,
        delay_risk=this_result.delay_risk,
        cost_risk=this_result.cost_risk,
        risk_level_thresholds=dict(metadata.level_thresholds),
    )


def get_peer_context(
    db: Session, *, state: str, project_type: str, contractor: str | None
) -> dict[str, PeerContextEntry]:
    """Reuses `app.analytics.segments.segment_report` directly, once per
    dimension (same 3-calls-per-request pattern Phase 14's own
    `portfolio_service.get_portfolio_overview` already uses) -- never a
    per-peer-project query loop, never a reimplementation of segment
    math."""
    values: dict[str, str | None] = {"state": state, "project_type": project_type, "contractor": contractor}

    out: dict[str, PeerContextEntry] = {}
    for dimension in DIMENSIONS:
        value = values[dimension]
        if value is None:
            out[dimension] = PeerContextEntry(
                dimension=dimension, status="unavailable", reason=UNAVAILABLE_NO_VALUE_REASON, value=None, segment=None
            )
            continue

        entries = segment_report(db, dimension)
        match = next((e for e in entries if e.value == value), None)
        if match is None:
            out[dimension] = PeerContextEntry(
                dimension=dimension,
                status="unavailable",
                reason=UNAVAILABLE_NOT_IN_SEGMENT_REPORT_REASON,
                value=value,
                segment=None,
            )
            continue

        out[dimension] = PeerContextEntry(dimension=dimension, status="ok", reason=None, value=value, segment=match)

    return out
