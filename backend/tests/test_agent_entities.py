"""Phase 17C entity extraction tests (app.agent.entities)."""

from __future__ import annotations

import pytest

from app.agent.entities import (
    extract_project_id,
    extract_reporting_month,
    extract_risk_level,
    extract_segment_dimension,
    parse_whatif_intent,
)
from scripts.prepare_features import PREDICTOR_COLUMNS


def test_extract_project_id_finds_and_normalizes_case():
    assert extract_project_id("show me hri-0006") == "HRI-0006"
    assert extract_project_id("Why is HRI-0328 high risk?") == "HRI-0328"


def test_extract_project_id_returns_none_when_absent():
    assert extract_project_id("show me information about a project") is None


def test_extract_reporting_month_finds_valid_month():
    assert extract_reporting_month("what about 2022-12 for HRI-0006") == "2022-12"


def test_extract_reporting_month_rejects_out_of_range_month():
    assert extract_reporting_month("what about 2025-13") is None


def test_extract_reporting_month_returns_none_when_absent():
    assert extract_reporting_month("why is HRI-0006 high risk") is None


def test_extract_risk_level_prefers_matched_word():
    assert extract_risk_level("which projects are at critical risk") == "CRITICAL"
    assert extract_risk_level("show me high risk projects") == "HIGH"
    assert extract_risk_level("no risk level mentioned here") is None


def test_extract_segment_dimension():
    assert extract_segment_dimension("risk distribution by state") == "state"
    assert extract_segment_dimension("break it down by contractor") == "contractor"
    assert extract_segment_dimension("show me by project type") == "project_type"
    assert extract_segment_dimension("show me the portfolio overview") is None


# --- what-if parsing -------------------------------------------------


def test_parse_whatif_progress_improves():
    result = parse_whatif_intent("what happens if progress improves by 10%")
    assert result is not None
    assert result.field == "actual_physical_progress_pct"
    assert result.direction == "up"
    assert result.magnitude_pct == 10.0
    assert result.mode == "additive_pct_point"


def test_parse_whatif_progress_worsens():
    result = parse_whatif_intent("what if progress drops by 15%")
    assert result is not None
    assert result.direction == "down"
    assert result.magnitude_pct == 15.0


def test_parse_whatif_cost_increases():
    result = parse_whatif_intent("what happens if cost increases by 5%")
    assert result is not None
    assert result.field == "actual_cost_to_date_inr_cr"
    assert result.mode == "multiplicative_pct"
    assert result.direction == "up"


def test_parse_whatif_financial_progress_is_distinguished_from_physical():
    result = parse_whatif_intent("what if financial progress improves by 8%")
    assert result is not None
    assert result.field == "actual_financial_progress_pct"


def test_parse_whatif_productivity():
    result = parse_whatif_intent("what happens if contractor productivity improves by 20%")
    assert result is not None
    assert result.field == "contractor_productivity_factor"
    assert result.mode == "multiplicative_pct"


def test_parse_whatif_returns_none_without_a_percentage():
    assert parse_whatif_intent("what happens if progress improves") is None


def test_parse_whatif_returns_none_without_a_recognized_concept():
    assert parse_whatif_intent("what happens if the moon turns blue by 10%") is None


def test_parse_whatif_returns_none_without_a_direction():
    assert parse_whatif_intent("progress by 10% for HRI-0006") is None


def test_every_whatif_field_is_a_permitted_predictor_column():
    """Never invents a feature name outside the audited whitelist."""
    from app.agent.entities import _CONCEPTS

    for _, field, _mode in _CONCEPTS:
        assert field in PREDICTOR_COLUMNS


def test_apply_additive_clips_to_0_100_range():
    result = parse_whatif_intent("what if progress improves by 50%")
    assert result.apply(80.0) == 100.0  # clipped, not 130
    result_down = parse_whatif_intent("what if progress drops by 50%")
    assert result_down.apply(20.0) == 0.0  # clipped, not -30


def test_apply_multiplicative_scales_correctly():
    result = parse_whatif_intent("what if cost increases by 10%")
    assert result.apply(100.0) == pytest.approx(110.0)
    result_down = parse_whatif_intent("what if cost decreases by 10%")
    assert result_down.apply(100.0) == pytest.approx(90.0)
