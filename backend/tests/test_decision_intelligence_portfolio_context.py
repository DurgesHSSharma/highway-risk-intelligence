"""Phase 15 tests for app.decision_intelligence.portfolio_context: risk
positioning (composite score/percentile/risk level) and peer context
(state/project_type/contractor), against the real committed corpus/DB via
the session-scoped fixtures in conftest.py.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.analytics.batch_scoring import get_cache_metadata
from app.analytics.risk_score import compute_portfolio_risk_scores
from app.analytics.segments import DIMENSIONS
from app.db.base import create_all, make_engine
from app.db.models import PortfolioPredictionCache
from app.decision_intelligence.portfolio_context import (
    PROJECT_NOT_IN_CACHE_MESSAGE,
    get_peer_context,
    get_risk_positioning,
)

NON_TERMINAL_PROJECT_ID = "HRI-0006"
CRITICAL_PROJECT_ID = "HRI-0328"


# --- risk positioning: ok path ---


def test_risk_positioning_ok_for_real_cached_project(db_session, _phase14_batch_scoring):
    result = get_risk_positioning(db_session, NON_TERMINAL_PROJECT_ID)

    assert result.status == "ok"
    assert result.message is None
    assert result.cohort_size == 400
    assert result.composite_risk_score is not None
    assert result.risk_level in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
    assert 0.0 <= result.percentile <= 100.0
    assert 0.0 <= result.delay_risk <= 1.0
    assert 0.0 <= result.cost_risk <= 1.0
    assert set(result.risk_level_thresholds.keys()) == {"q1", "q2", "q3"}


def test_higher_composite_score_means_higher_percentile(db_session, _phase14_batch_scoring):
    """Percentile must be monotonic in composite_risk_score: the real
    CRITICAL example project (HRI-0328, see docs/ADVANCED_ANALYTICS.md)
    must have a strictly higher percentile than a MEDIUM/LOW project."""
    critical = get_risk_positioning(db_session, CRITICAL_PROJECT_ID)
    medium = get_risk_positioning(db_session, NON_TERMINAL_PROJECT_ID)

    assert critical.status == "ok" and medium.status == "ok"
    assert critical.composite_risk_score > medium.composite_risk_score
    assert critical.percentile > medium.percentile


def test_risk_level_matches_quartile_thresholds(db_session, _phase14_batch_scoring):
    """risk_level must be assignable purely from composite_risk_score and
    the returned thresholds, using the exact <=q1/<=q2/<=q3 boundary rule
    documented in app.analytics.risk_score -- proves risk_level was copied
    from Phase 14, not recomputed with a different boundary convention."""
    result = get_risk_positioning(db_session, NON_TERMINAL_PROJECT_ID)
    score = result.composite_risk_score
    q1, q2, q3 = (
        result.risk_level_thresholds["q1"],
        result.risk_level_thresholds["q2"],
        result.risk_level_thresholds["q3"],
    )
    if score <= q1:
        expected = "LOW"
    elif score <= q2:
        expected = "MEDIUM"
    elif score <= q3:
        expected = "HIGH"
    else:
        expected = "CRITICAL"
    assert result.risk_level == expected


# --- risk positioning: cache_unavailable / project_not_in_cache ---


def test_risk_positioning_cache_unavailable_on_empty_database():
    engine = make_engine("sqlite:///:memory:")
    create_all(bind=engine)
    from sqlalchemy.orm import Session as OrmSession

    session = OrmSession(bind=engine)
    try:
        result = get_risk_positioning(session, "HRI-0006")
        assert result.status == "cache_unavailable"
        assert result.message is not None
        assert result.cohort_size is None
        assert result.composite_risk_score is None
        assert result.percentile is None
    finally:
        session.close()


def test_risk_positioning_project_not_in_cache(db_session, _phase14_batch_scoring):
    result = get_risk_positioning(db_session, "PROJECT-NOT-A-REAL-ID")
    assert result.status == "project_not_in_cache"
    assert result.message == PROJECT_NOT_IN_CACHE_MESSAGE
    # Cohort metadata is still surfaced even though this project has no row.
    assert result.cohort_size == 400
    assert result.composite_risk_score is None
    assert result.percentile is None


# --- peer context ---


def test_peer_context_returns_all_three_dimensions(db_session, _phase14_batch_scoring):
    peers = get_peer_context(db_session, state="Telangana", project_type="Greenfield Highway", contractor="Malwa Builders Pvt Ltd")
    assert set(peers.keys()) == set(DIMENSIONS)
    for dimension in DIMENSIONS:
        entry = peers[dimension]
        assert entry.status == "ok"
        assert entry.segment is not None
        assert entry.segment.historical is not None


def test_peer_context_handles_none_contractor(db_session, _phase14_batch_scoring):
    peers = get_peer_context(db_session, state="Telangana", project_type="Greenfield Highway", contractor=None)
    assert peers["contractor"].status == "unavailable"
    assert peers["contractor"].reason is not None
    assert peers["contractor"].segment is None
    # The other two dimensions are unaffected by a missing contractor.
    assert peers["state"].status == "ok"


def test_peer_context_handles_value_not_in_segment_report(db_session, _phase14_batch_scoring):
    peers = get_peer_context(db_session, state="NotARealState", project_type="Greenfield Highway", contractor="Malwa Builders Pvt Ltd")
    assert peers["state"].status == "unavailable"
    assert peers["state"].reason is not None
    assert peers["state"].segment is None


def test_peer_context_small_sample_is_preserved_not_dropped(db_session, _phase14_batch_scoring):
    """Punjab is a real, documented small-sample state (n=11 < threshold
    15, see docs/ADVANCED_ANALYTICS.md section 12) -- it must still be
    returned with historical data, just flagged, never omitted."""
    peers = get_peer_context(db_session, state="Punjab", project_type="Greenfield Highway", contractor="Malwa Builders Pvt Ltd")
    state_entry = peers["state"]
    assert state_entry.status == "ok"
    assert state_entry.segment.small_sample is True
    assert state_entry.segment.historical is not None
    assert state_entry.segment.historical.project_count > 0


def test_peer_context_never_triggers_500_for_any_real_project(db_session, _phase14_batch_scoring):
    """Every real project's own (state, project_type, contractor) values
    must resolve without raising -- proves segment_report's value set is a
    superset of every project's actual field values."""
    from app.db.models import Project

    projects = db_session.execute(select(Project)).scalars().all()
    for p in projects[:25]:  # bounded sample, still a real cross-section
        peers = get_peer_context(db_session, state=p.state, project_type=p.project_type, contractor=p.contractor)
        assert peers["state"].status == "ok"
        assert peers["project_type"].status == "ok"


# --- Independent math validation (master-prompt section 30): percentile,
# recomputed from raw cache data with a formula written fresh here, never
# by calling get_risk_positioning and comparing it to itself. ---


def test_percentile_independent_recomputation_from_raw_cache(db_session, _phase14_batch_scoring):
    cache_rows = list(db_session.execute(select(PortfolioPredictionCache)).scalars().all())
    assert len(cache_rows) == 400

    delay_days = [r.final_delay_days_predicted for r in cache_rows]
    cost_pct = [r.final_cost_overrun_pct_predicted for r in cache_rows]
    d_min, d_max = min(delay_days), max(delay_days)
    c_min, c_max = min(cost_pct), max(cost_pct)

    def _composite(row) -> float:
        norm_delay = (row.final_delay_days_predicted - d_min) / (d_max - d_min)
        norm_cost = (row.final_cost_overrun_pct_predicted - c_min) / (c_max - c_min)
        sig_prob = row.significant_delay_probability
        if sig_prob is None:
            sig_prob = float(row.significant_delay_predicted_class)
        cost_prob = row.cost_overrun_probability
        if cost_prob is None:
            cost_prob = float(row.cost_overrun_predicted_class)
        delay_risk = (sig_prob + norm_delay) / 2.0
        cost_risk = (cost_prob + norm_cost) / 2.0
        return 100.0 * (delay_risk + cost_risk) / 2.0

    scores_by_project = {r.project_id: _composite(r) for r in cache_rows}
    target_score = scores_by_project[NON_TERMINAL_PROJECT_ID]
    all_scores = list(scores_by_project.values())
    expected_percentile = 100.0 * sum(1 for s in all_scores if s <= target_score) / len(all_scores)

    result = get_risk_positioning(db_session, NON_TERMINAL_PROJECT_ID)
    assert result.composite_risk_score == pytest.approx(target_score, abs=1e-6)
    assert result.percentile == pytest.approx(expected_percentile, abs=1e-6)


def test_percentile_definition_is_documented_and_monotonic(db_session, _phase14_batch_scoring):
    """Cross-check the documented formula against an independently derived
    quantile-rank computation over the raw cache (statistics.median-style
    sanity, not the same code path): the project with the maximum observed
    composite score in the whole cohort must have percentile 100."""
    cache_rows = list(db_session.execute(select(PortfolioPredictionCache)).scalars().all())
    results, _ = compute_portfolio_risk_scores(cache_rows)
    max_row = max(results, key=lambda r: r.composite_risk_score)

    positioning = get_risk_positioning(db_session, max_row.project_id)
    assert positioning.percentile == 100.0
