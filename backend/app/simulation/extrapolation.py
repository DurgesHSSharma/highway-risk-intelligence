"""Phase 10: checks each overridden NUMERIC predictor against the Phase 4
TRAINING-split range loaded by `app.ml.training_ranges` (never validation,
test, the full dataset, or the live snapshot -- see
docs/WHATIF_SIMULATOR.md). This is a WARNING, not a rejection: the
simulation still executes and the response still carries every prediction.

Categorical predictors (`state`, `project_type`, `contractor`) are never
checked here -- the Phase 10 brief scopes extrapolation checks to numeric
features only; an unfamiliar category is instead handled by the saved
pipeline's own `OneHotEncoder(handle_unknown="ignore")`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.ml import training_ranges
from app.simulation.overrides import NUMERIC_PREDICTOR_COLUMNS


@dataclass(frozen=True)
class ExtrapolationWarning:
    field: str
    simulated_value: float
    training_min: float
    training_max: float
    message: str


def check_extrapolation(overrides: dict[str, Any]) -> list[ExtrapolationWarning]:
    warnings: list[ExtrapolationWarning] = []
    for field, value in overrides.items():
        if field not in NUMERIC_PREDICTOR_COLUMNS:
            continue
        bounds = training_ranges.get_range(field)
        if bounds is None:
            continue
        v = float(value)
        if v < bounds["min"] or v > bounds["max"]:
            warnings.append(
                ExtrapolationWarning(
                    field=field,
                    simulated_value=v,
                    training_min=bounds["min"],
                    training_max=bounds["max"],
                    message=(
                        f"The overridden value for '{field}' ({v}) falls outside the range "
                        f"observed in the Phase 4 TRAINING split ({bounds['min']} to "
                        f"{bounds['max']}). Model behavior outside its observed training "
                        "distribution is less reliable."
                    ),
                )
            )
    return warnings
