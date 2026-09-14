"""Phase 10: validates what-if override fields against the Phase 3-audited
permitted predictor list (`scripts.prepare_features.PREDICTOR_COLUMNS`) and
applies valid overrides to a baseline feature row to build the simulated
row -- see docs/WHATIF_SIMULATOR.md.

An override field is permitted if and only if it is one of the 45
`PREDICTOR_COLUMNS`. Everything else -- `project_id`, `reporting_month`,
the four target columns, the `is_terminal_snapshot` flag, the two
EDA-confirmed exact-duplicate columns, any other `EXCLUDE_FROM_MODEL`
column (see docs/FEATURE_ENGINEERING.md section 2), or an unrecognized
field name -- is rejected, never silently dropped.

Only ABSOLUTE values are accepted: a numeric predictor's override must be a
real Python `int`/`float` (not a `bool`, which JSON also decodes as `int`
in some ecosystems but never here), and a categorical predictor's override
must be a `str`. This structurally rejects delta-style payloads like
`"+20"` or `"increase by 20"` -- both arrive as a `str` where a number is
required and are therefore flagged invalid, with no special-casing needed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from scripts.prepare_features import PREDICTOR_COLUMNS, RAW_CATEGORICAL

NUMERIC_PREDICTOR_COLUMNS: list[str] = [c for c in PREDICTOR_COLUMNS if c not in RAW_CATEGORICAL]
CATEGORICAL_PREDICTOR_COLUMNS: list[str] = list(RAW_CATEGORICAL)

# Reasons shown to the caller for the most common non-permitted fields (see
# docs/FEATURE_ENGINEERING.md section 2's classification table). Any field
# not listed here that is also not a permitted predictor is "unknown_field".
_KNOWN_NON_PREDICTOR_REASONS: dict[str, str] = {
    "project_id": "identifier",
    "reporting_month": "identifier",
    "final_delay_days": "target_column",
    "significant_delay": "target_column",
    "final_cost_overrun_pct": "target_column",
    "cost_overrun": "target_column",
    "is_terminal_snapshot": "terminal_flag",
    "project_status": "excluded_from_model",
    "data_provenance": "excluded_from_model",
    "project_name": "excluded_from_model",
    "highway_number": "excluded_from_model",
    "planned_start_date": "excluded_from_model",
    "planned_completion_date": "excluded_from_model",
    "planned_expenditure_inr_cr": "excluded_from_model_exact_duplicate",
    "expenditure_variance_pct": "excluded_from_model_exact_duplicate",
}


@dataclass(frozen=True)
class InvalidOverrideField:
    field: str
    reason: str


@dataclass(frozen=True)
class OverrideDetail:
    field: str
    original_value: Any
    simulated_value: Any
    delta: float | None


def classify_invalid_field(field: str) -> str:
    return _KNOWN_NON_PREDICTOR_REASONS.get(field, "unknown_field")


def validate_override_fields(overrides: dict[str, Any]) -> list[InvalidOverrideField]:
    """Returns every invalid field with a reason; an empty list means every
    field is a permitted predictor of the correct type. Never silently
    drops an invalid field -- the caller must reject the whole request."""
    invalid: list[InvalidOverrideField] = []
    for field, value in overrides.items():
        if field not in PREDICTOR_COLUMNS:
            invalid.append(InvalidOverrideField(field=field, reason=classify_invalid_field(field)))
            continue
        if field in CATEGORICAL_PREDICTOR_COLUMNS:
            if not isinstance(value, str):
                invalid.append(InvalidOverrideField(field=field, reason="wrong_type_expected_string"))
        else:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                invalid.append(InvalidOverrideField(field=field, reason="wrong_type_expected_number"))
    return invalid


def _to_jsonable(field: str, value: Any) -> Any:
    if pd.isna(value):
        return None
    return float(value) if field in NUMERIC_PREDICTOR_COLUMNS else str(value)


def apply_overrides(
    baseline_row: pd.DataFrame, overrides: dict[str, Any]
) -> tuple[pd.DataFrame, list[OverrideDetail]]:
    """Returns `(simulated_row, details)`. `baseline_row` is never mutated;
    every column not named in `overrides` is left byte-identical on the
    returned simulated row (see backend/tests/test_simulation_service.py::
    test_non_overridden_features_are_byte_identical)."""
    simulated_row = baseline_row.copy(deep=True)
    details: list[OverrideDetail] = []
    for field, new_value in overrides.items():
        original_value = _to_jsonable(field, baseline_row.iloc[0][field])
        coerced_new = float(new_value) if field in NUMERIC_PREDICTOR_COLUMNS else str(new_value)
        simulated_row.at[0, field] = coerced_new

        delta = (coerced_new - original_value) if (field in NUMERIC_PREDICTOR_COLUMNS and original_value is not None) else None
        details.append(
            OverrideDetail(field=field, original_value=original_value, simulated_value=coerced_new, delta=delta)
        )
    return simulated_row, details
