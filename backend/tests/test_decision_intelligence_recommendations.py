"""Phase 15 tests for app.decision_intelligence.recommendations: the fifth
`portfolio_context` recommendation family (peer-elevated-risk rule +
driver-divergence rule), and that it never fires without a concrete
grounding condition.
"""

from __future__ import annotations

from app.analytics.historical import HistoricalOverview
from app.analytics.segments import HistoricalSegmentStat, PredictedSegmentStat, SegmentEntry
from app.decision_intelligence.driver_alignment import TaskDriverAlignment
from app.decision_intelligence.portfolio_context import PeerContextEntry
from app.decision_intelligence.recommendations import (
    MAX_DRIVER_DIVERGENCE_RECOMMENDATIONS,
    MAX_PEER_ELEVATION_RECOMMENDATIONS,
    PEER_ELEVATION_THRESHOLD_PP,
    driver_divergence_recommendations,
    generate_portfolio_context_recommendations,
    peer_elevated_risk_recommendations,
)

PORTFOLIO_HIST = HistoricalOverview(
    completed_project_count=400,
    significant_delay_count=197,
    significant_delay_rate=0.4925,
    cost_overrun_count=153,
    cost_overrun_rate=0.3825,
    mean_final_delay_days=65.0,
    mean_final_cost_overrun_pct=7.5,
)


def _peer_entry(dimension: str, value: str, *, delay_rate: float, cost_rate: float, n: int = 20, small_sample: bool = False) -> PeerContextEntry:
    hist = HistoricalSegmentStat(
        project_count=n,
        significant_delay_rate=delay_rate,
        cost_overrun_rate=cost_rate,
        mean_final_delay_days=70.0,
        mean_final_cost_overrun_pct=8.0,
    )
    seg = SegmentEntry(dimension=dimension, value=value, min_sample_threshold=15, small_sample=small_sample, historical=hist, predicted=None)
    return PeerContextEntry(dimension=dimension, status="ok", reason=None, value=value, segment=seg)


def _unavailable_entry(dimension: str) -> PeerContextEntry:
    return PeerContextEntry(dimension=dimension, status="unavailable", reason="no value", value=None, segment=None)


# --- peer-elevated-risk rule ---


def test_peer_elevation_fires_when_all_conditions_hold():
    peer_context = {
        "state": _peer_entry("state", "Uttarakhand", delay_rate=PORTFOLIO_HIST.significant_delay_rate + 0.20, cost_rate=PORTFOLIO_HIST.cost_overrun_rate),
        "project_type": _unavailable_entry("project_type"),
        "contractor": _unavailable_entry("contractor"),
    }
    recs = peer_elevated_risk_recommendations("HIGH", peer_context, PORTFOLIO_HIST)
    assert len(recs) == 1
    assert recs[0].basis_type == "portfolio_context"
    assert "Uttarakhand" in recs[0].text
    assert "state" in recs[0].basis_detail


def test_peer_elevation_does_not_fire_for_low_or_medium_risk():
    peer_context = {
        "state": _peer_entry("state", "Uttarakhand", delay_rate=PORTFOLIO_HIST.significant_delay_rate + 0.30, cost_rate=PORTFOLIO_HIST.cost_overrun_rate),
        "project_type": _unavailable_entry("project_type"),
        "contractor": _unavailable_entry("contractor"),
    }
    for level in (None, "LOW", "MEDIUM"):
        assert peer_elevated_risk_recommendations(level, peer_context, PORTFOLIO_HIST) == []


def test_peer_elevation_does_not_fire_for_small_sample_segment():
    peer_context = {
        "state": _peer_entry("state", "Punjab", delay_rate=PORTFOLIO_HIST.significant_delay_rate + 0.30, cost_rate=PORTFOLIO_HIST.cost_overrun_rate, small_sample=True),
        "project_type": _unavailable_entry("project_type"),
        "contractor": _unavailable_entry("contractor"),
    }
    assert peer_elevated_risk_recommendations("CRITICAL", peer_context, PORTFOLIO_HIST) == []


def test_peer_elevation_does_not_fire_below_threshold():
    """A spread just under PEER_ELEVATION_THRESHOLD_PP must not fire."""
    below_threshold = PEER_ELEVATION_THRESHOLD_PP - 0.01
    peer_context = {
        "state": _peer_entry(
            "state", "SomeState",
            delay_rate=PORTFOLIO_HIST.significant_delay_rate + below_threshold,
            cost_rate=PORTFOLIO_HIST.cost_overrun_rate + below_threshold,
        ),
        "project_type": _unavailable_entry("project_type"),
        "contractor": _unavailable_entry("contractor"),
    }
    assert peer_elevated_risk_recommendations("CRITICAL", peer_context, PORTFOLIO_HIST) == []


def test_peer_elevation_fires_exactly_at_threshold():
    peer_context = {
        "state": _peer_entry(
            "state", "SomeState",
            delay_rate=PORTFOLIO_HIST.significant_delay_rate + PEER_ELEVATION_THRESHOLD_PP,
            cost_rate=PORTFOLIO_HIST.cost_overrun_rate,
        ),
        "project_type": _unavailable_entry("project_type"),
        "contractor": _unavailable_entry("contractor"),
    }
    assert len(peer_elevated_risk_recommendations("HIGH", peer_context, PORTFOLIO_HIST)) == 1


def test_peer_elevation_capped_at_max():
    peer_context = {
        "state": _peer_entry("state", "S1", delay_rate=PORTFOLIO_HIST.significant_delay_rate + 0.30, cost_rate=PORTFOLIO_HIST.cost_overrun_rate + 0.30),
        "project_type": _peer_entry("project_type", "T1", delay_rate=PORTFOLIO_HIST.significant_delay_rate + 0.25, cost_rate=PORTFOLIO_HIST.cost_overrun_rate + 0.25),
        "contractor": _peer_entry("contractor", "C1", delay_rate=PORTFOLIO_HIST.significant_delay_rate + 0.20, cost_rate=PORTFOLIO_HIST.cost_overrun_rate + 0.20, n=10),
    }
    recs = peer_elevated_risk_recommendations("CRITICAL", peer_context, PORTFOLIO_HIST)
    assert len(recs) == MAX_PEER_ELEVATION_RECOMMENDATIONS
    assert len(recs) <= MAX_PEER_ELEVATION_RECOMMENDATIONS


def test_peer_elevation_never_uses_prohibited_absolute_language():
    peer_context = {
        "state": _peer_entry("state", "Uttarakhand", delay_rate=PORTFOLIO_HIST.significant_delay_rate + 0.30, cost_rate=PORTFOLIO_HIST.cost_overrun_rate),
        "project_type": _unavailable_entry("project_type"),
        "contractor": _unavailable_entry("contractor"),
    }
    recs = peer_elevated_risk_recommendations("CRITICAL", peer_context, PORTFOLIO_HIST)
    for r in recs:
        lowered = r.text.lower()
        assert "will fail" not in lowered
        assert "will reduce" not in lowered
        assert "this segment looks risky" not in lowered
        assert any(word in lowered for word in ("may be worth", "consider", "review", "verify"))


# --- driver-divergence rule ---


def _alignment(task_key, live, portfolio, agreement, comparable) -> TaskDriverAlignment:
    return TaskDriverAlignment(
        task_key=task_key,
        matches_serving_model=comparable,
        live_top_driver=live,
        live_top_driver_identity=live,
        portfolio_top_driver=portfolio,
        portfolio_top_driver_identity=portfolio,
        agreement=agreement,
        comparable=comparable,
    )


def test_driver_divergence_fires_when_comparable_and_disagreeing():
    alignment = [_alignment("significant_delay", "progress_efficiency", "contractor_productivity_factor", False, True)]
    recs = driver_divergence_recommendations(alignment)
    assert len(recs) == 1
    assert "significant-delay" in recs[0].text
    assert "progress_efficiency" in recs[0].text
    assert "contractor_productivity_factor" in recs[0].text
    assert recs[0].basis_type == "portfolio_context"


def test_driver_divergence_does_not_fire_when_agreeing():
    alignment = [_alignment("significant_delay", "progress_efficiency", "progress_efficiency", True, True)]
    assert driver_divergence_recommendations(alignment) == []


def test_driver_divergence_does_not_fire_for_non_comparable_cost_tasks():
    """comparable=False (matches_serving_model=False) must suppress the
    rule even when agreement happens to be False -- this is the exact
    non-comparable-cost-task exclusion required by master-prompt
    section 18."""
    alignment = [
        _alignment("cost_overrun", "project_age_ratio", "cost_tracking_gap_inr_cr", False, False),
        _alignment("final_cost_overrun_pct", "actual_physical_progress_pct", "cost_tracking_gap_inr_cr", False, False),
    ]
    assert driver_divergence_recommendations(alignment) == []


def test_driver_divergence_does_not_fire_when_either_side_unavailable():
    alignment = [_alignment("significant_delay", None, None, None, True)]
    assert driver_divergence_recommendations(alignment) == []


def test_driver_divergence_capped_at_max():
    alignment = [
        _alignment("significant_delay", "a", "b", False, True),
        _alignment("final_delay_days", "c", "d", False, True),
    ]
    recs = driver_divergence_recommendations(alignment)
    assert len(recs) <= MAX_DRIVER_DIVERGENCE_RECOMMENDATIONS


# --- combined generator ---


def test_generate_portfolio_context_recommendations_combines_both_rules():
    peer_context = {
        "state": _peer_entry("state", "Uttarakhand", delay_rate=PORTFOLIO_HIST.significant_delay_rate + 0.30, cost_rate=PORTFOLIO_HIST.cost_overrun_rate),
        "project_type": _unavailable_entry("project_type"),
        "contractor": _unavailable_entry("contractor"),
    }
    alignment = [_alignment("significant_delay", "progress_efficiency", "contractor_productivity_factor", False, True)]
    recs = generate_portfolio_context_recommendations("CRITICAL", peer_context, PORTFOLIO_HIST, alignment)
    basis_types = {r.basis_type for r in recs}
    assert basis_types == {"portfolio_context"}
    assert len(recs) == 2


def test_generate_portfolio_context_recommendations_empty_when_no_condition_holds():
    peer_context = {
        "state": _unavailable_entry("state"),
        "project_type": _unavailable_entry("project_type"),
        "contractor": _unavailable_entry("contractor"),
    }
    alignment = [_alignment("significant_delay", "x", "x", True, True)]
    assert generate_portfolio_context_recommendations("LOW", peer_context, PORTFOLIO_HIST, alignment) == []
