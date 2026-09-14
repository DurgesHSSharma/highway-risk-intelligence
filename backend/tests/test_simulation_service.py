"""Phase 10 service-layer tests that need direct access to the 45-column
feature row (not exposed by the HTTP response) -- see
backend/tests/test_simulation_api.py for the endpoint-level tests."""

from __future__ import annotations

import pandas as pd
import pytest

from app.ml.features import build_predictor_row
from app.simulation.overrides import (
    CATEGORICAL_PREDICTOR_COLUMNS,
    NUMERIC_PREDICTOR_COLUMNS,
    apply_overrides,
    classify_invalid_field,
    validate_override_fields,
)
from scripts.prepare_features import PREDICTOR_COLUMNS

NON_TERMINAL_PROJECT_ID = "HRI-0006"
NON_TERMINAL_MONTH = "2022-12"


def test_permitted_predictor_columns_cover_exactly_the_45_phase3_columns():
    assert len(PREDICTOR_COLUMNS) == 45
    assert len(NUMERIC_PREDICTOR_COLUMNS) + len(CATEGORICAL_PREDICTOR_COLUMNS) == 45
    assert set(NUMERIC_PREDICTOR_COLUMNS) | set(CATEGORICAL_PREDICTOR_COLUMNS) == set(PREDICTOR_COLUMNS)


# --- TEST 5: non-overridden feature preservation ---


def test_non_overridden_features_are_byte_identical(db_session):
    baseline = build_predictor_row(db_session, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH)
    simulated, _ = apply_overrides(baseline, {"land_acquisition_delay_days": 999.0})

    assert simulated.iloc[0]["land_acquisition_delay_days"] == 999.0
    for col in PREDICTOR_COLUMNS:
        if col == "land_acquisition_delay_days":
            continue
        b = baseline.iloc[0][col]
        s = simulated.iloc[0][col]
        if pd.isna(b) and pd.isna(s):
            continue
        assert b == s, f"unexpected change in non-overridden column {col!r}: {b!r} -> {s!r}"


def test_baseline_row_is_never_mutated_by_apply_overrides(db_session):
    baseline = build_predictor_row(db_session, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH)
    original_value = baseline.iloc[0]["contractor_productivity_factor"]
    apply_overrides(baseline, {"contractor_productivity_factor": 0.05})
    assert baseline.iloc[0]["contractor_productivity_factor"] == original_value


def test_multiple_overrides_leave_every_other_column_untouched(db_session):
    baseline = build_predictor_row(db_session, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH)
    overridden_fields = {"land_acquisition_delay_days": 45.0, "contractor_productivity_factor": 0.6}
    simulated, _ = apply_overrides(baseline, overridden_fields)

    for col in PREDICTOR_COLUMNS:
        if col in overridden_fields:
            continue
        b = baseline.iloc[0][col]
        s = simulated.iloc[0][col]
        if pd.isna(b) and pd.isna(s):
            continue
        assert b == s, f"unexpected change in non-overridden column {col!r}"


# --- override-field classification (used by the invalid-field 422 response) ---


@pytest.mark.parametrize(
    "field,expected_reason",
    [
        ("project_id", "identifier"),
        ("reporting_month", "identifier"),
        ("final_delay_days", "target_column"),
        ("significant_delay", "target_column"),
        ("cost_overrun", "target_column"),
        ("final_cost_overrun_pct", "target_column"),
        ("is_terminal_snapshot", "terminal_flag"),
        ("project_status", "excluded_from_model"),
        ("planned_expenditure_inr_cr", "excluded_from_model_exact_duplicate"),
        ("expenditure_variance_pct", "excluded_from_model_exact_duplicate"),
        ("made_up_field_xyz", "unknown_field"),
    ],
)
def test_classify_invalid_field_reasons(field, expected_reason):
    assert classify_invalid_field(field) == expected_reason


def test_validate_override_fields_accepts_every_permitted_predictor_with_a_type_appropriate_value():
    overrides = {col: ("SomeCategory" if col in CATEGORICAL_PREDICTOR_COLUMNS else 1.0) for col in PREDICTOR_COLUMNS}
    assert validate_override_fields(overrides) == []


def test_validate_override_fields_rejects_delta_style_string_for_a_numeric_field():
    """'+20' / 'increase by 20' arrive as a JSON string; a numeric predictor
    requires a real number, so these are structurally rejected -- no
    special-casing of delta syntax is needed."""
    invalid = validate_override_fields({"land_acquisition_delay_days": "+20"})
    assert len(invalid) == 1
    assert invalid[0].field == "land_acquisition_delay_days"
    assert invalid[0].reason == "wrong_type_expected_number"


def test_validate_override_fields_rejects_bool_for_a_numeric_field():
    invalid = validate_override_fields({"land_acquisition_delay_days": True})
    assert len(invalid) == 1
    assert invalid[0].reason == "wrong_type_expected_number"


def test_validate_override_fields_rejects_number_for_a_categorical_field():
    invalid = validate_override_fields({"state": 5})
    assert len(invalid) == 1
    assert invalid[0].field == "state"
    assert invalid[0].reason == "wrong_type_expected_string"
