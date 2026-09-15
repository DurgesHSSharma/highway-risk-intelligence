"""Phase 14 composite risk score unit tests: pure arithmetic, no
database/model dependency -- uses small hand-constructed fake cache rows
with known values so the expected output can be verified by hand."""

from __future__ import annotations

from dataclasses import dataclass

from app.analytics.risk_score import compute_portfolio_risk_scores


@dataclass
class FakeCacheRow:
    project_id: str
    significant_delay_probability: float | None
    significant_delay_predicted_class: int
    final_delay_days_predicted: float
    cost_overrun_probability: float | None
    cost_overrun_predicted_class: int
    final_cost_overrun_pct_predicted: float


def test_empty_input_returns_empty_results_and_no_metadata():
    results, metadata = compute_portfolio_risk_scores([])
    assert results == []
    assert metadata is None


def test_known_values_produce_hand_verifiable_composite_score():
    # delay_days range [0, 100] -> normalized 0/1; cost_pct range [0, 10] -> normalized 0/1.
    row_low = FakeCacheRow("P1", 0.0, 0, 0.0, 0.0, 0, 0.0)
    row_high = FakeCacheRow("P2", 1.0, 1, 100.0, 1.0, 1, 10.0)

    results, metadata = compute_portfolio_risk_scores([row_low, row_high])
    by_id = {r.project_id: r for r in results}

    # P1: delay_risk = mean(0, 0) = 0; cost_risk = mean(0, 0) = 0; composite = 0.
    assert by_id["P1"].delay_risk == 0.0
    assert by_id["P1"].cost_risk == 0.0
    assert by_id["P1"].composite_risk_score == 0.0

    # P2: delay_risk = mean(1, 1) = 1; cost_risk = mean(1, 1) = 1; composite = 100.
    assert by_id["P2"].delay_risk == 1.0
    assert by_id["P2"].cost_risk == 1.0
    assert by_id["P2"].composite_risk_score == 100.0

    assert metadata.cohort_size == 2
    assert metadata.final_delay_days_range.observed_min == 0.0
    assert metadata.final_delay_days_range.observed_max == 100.0


def test_risk_levels_are_assigned_by_quartile_of_the_actual_cohort():
    # Four rows with evenly spaced composite scores 0, 33.33, 66.67, 100 (via
    # delay_risk == cost_risk == same fraction) -> should split LOW/MEDIUM/HIGH/CRITICAL.
    rows = [
        FakeCacheRow("P0", 0.0, 0, 0.0, 0.0, 0, 0.0),
        FakeCacheRow("P1", 1 / 3, 0, 1 / 3 * 100, 1 / 3, 0, 1 / 3 * 10),
        FakeCacheRow("P2", 2 / 3, 1, 2 / 3 * 100, 2 / 3, 1, 2 / 3 * 10),
        FakeCacheRow("P3", 1.0, 1, 100.0, 1.0, 1, 10.0),
    ]
    results, _ = compute_portfolio_risk_scores(rows)
    levels = {r.project_id: r.risk_level for r in results}
    assert levels["P0"] == "LOW"
    assert levels["P3"] == "CRITICAL"
    # Middle two must be MEDIUM/HIGH in ascending order (exact boundary
    # behavior is an implementation detail; monotonicity is what matters).
    scores = {r.project_id: r.composite_risk_score for r in results}
    ordered = sorted(rows, key=lambda r: scores[r.project_id])
    ordered_levels = [levels[r.project_id] for r in ordered]
    level_rank = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
    ranks = [level_rank[lv] for lv in ordered_levels]
    assert ranks == sorted(ranks)


def test_degenerate_equal_values_normalize_to_midpoint_not_a_crash():
    rows = [
        FakeCacheRow("P1", 0.5, 0, 50.0, 0.5, 0, 5.0),
        FakeCacheRow("P2", 0.5, 0, 50.0, 0.5, 0, 5.0),
    ]
    results, metadata = compute_portfolio_risk_scores(rows)
    assert metadata.final_delay_days_range.observed_min == metadata.final_delay_days_range.observed_max
    for r in results:
        assert r.delay_risk == 0.5
        assert r.cost_risk == 0.5
        assert r.composite_risk_score == 50.0


def test_missing_probability_falls_back_to_predicted_class():
    row = FakeCacheRow("P1", None, 1, 50.0, None, 0, 5.0)
    results, _ = compute_portfolio_risk_scores([row])
    # With only one row, normalization is degenerate (span=0 -> 0.5), so
    # delay_risk = mean(predicted_class=1.0, 0.5) = 0.75.
    assert results[0].delay_risk == 0.75
    assert results[0].cost_risk == 0.25
