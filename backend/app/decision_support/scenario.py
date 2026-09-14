"""Phase 11 REPAIR: constructs the single illustrative what-if scenario from
the LIVE top SHAP driver of the `significant_delay` task -- never from
Phase 5 global importance, never from a caller-supplied override (the
public endpoint is a body-less GET; see app.routers.decision_support).

Design choices, both explicit and disclosed (see docs/DECISION_SUPPORT.md):

- **Which feature**: `significant_delay`'s own rank-1 live SHAP driver is
  used as the anchor for the one illustrative scenario. SHAP magnitudes are
  not comparable across tasks (probability-scale vs. days-scale vs.
  log-odds-scale vs. percentage-points-scale -- see
  app.decision_support.shap_explainer's documented output semantics), so
  picking "the single highest SHAP value across all four tasks" would be a
  scale-comparison fallacy. `significant_delay` is the primary risk
  classification this synthesizer leads with, making it a defensible,
  deterministic anchor.
- **Categorical top driver**: if `significant_delay`'s top driver is a
  categorical one-hot feature (e.g. `state_Karnataka`), no numeric
  "illustrative reference value" is well-defined for a what-if override, so
  no scenario is constructed for that request -- explicitly documented, not
  approximated.
- **Reference value**: the real arithmetic MEAN of that raw predictor
  column over the frozen Phase 4 TRAINING partition (never validation/test/
  full-dataset/live-snapshot data -- same rule Phase 10's
  training_feature_ranges.json and this module's own SHAP background
  already follow). This is a real, defensible population-typical value, not
  an invented threshold.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import pandas as pd
from sqlalchemy.orm import Session

from app.decision_support.shap_explainer import (
    BACKGROUND_FEATURES_PATH,
    DriverFeature,
    TaskRiskDrivers,
)
from app.simulation.overrides import NUMERIC_PREDICTOR_COLUMNS
from app.simulation.service import run_simulation

ILLUSTRATIVE_SCENARIO_LABEL = "illustrative, not a recommendation"


@dataclass(frozen=True)
class IllustrativeScenario:
    field: str
    reference_value: float
    label: str
    overrides: list
    extrapolation_warnings: list
    baseline_predictions: dict
    simulated_predictions: dict


@lru_cache(maxsize=None)
def _training_mean(raw_predictor_column: str) -> float:
    """Real arithmetic mean of one numeric predictor column over the frozen
    Phase 4 TRAINING partition (`scripts.data_split.project_level_split`,
    unchanged, same source file as the SHAP background in
    app.decision_support.shap_explainer). Cached per-column, computed at
    most once per process."""
    from scripts.data_split import project_level_split

    df = pd.read_csv(BACKGROUND_FEATURES_PATH)
    split = project_level_split(df)
    return float(pd.to_numeric(split.train[raw_predictor_column], errors="raise").mean())


def pick_illustrative_feature(significant_delay_drivers: TaskRiskDrivers) -> DriverFeature | None:
    """Returns the significant_delay task's rank-1 live SHAP driver if it is
    a NUMERIC raw predictor column (a well-defined illustrative override
    target), else None (categorical top driver -- no scenario constructed)."""
    if not significant_delay_drivers.top_drivers:
        return None
    top = significant_delay_drivers.top_drivers[0]
    if top.feature in NUMERIC_PREDICTOR_COLUMNS:
        return top
    return None


def build_illustrative_scenario(
    db: Session, project_id: str, reporting_month: str, significant_delay_drivers: TaskRiskDrivers
) -> IllustrativeScenario | None:
    """Reuses Phase 10's `run_simulation` directly (never reimplemented) to
    score one illustrative override: the live top `significant_delay` SHAP
    driver, moved to its real Phase 4 TRAINING-partition mean. Returns None
    (no scenario) when the top driver is categorical -- see module
    docstring."""
    driver = pick_illustrative_feature(significant_delay_drivers)
    if driver is None:
        return None

    reference_value = _training_mean(driver.feature)
    sim_result = run_simulation(db, project_id, reporting_month, {driver.feature: reference_value})

    return IllustrativeScenario(
        field=driver.feature,
        reference_value=reference_value,
        label=ILLUSTRATIVE_SCENARIO_LABEL,
        overrides=sim_result.overrides,
        extrapolation_warnings=sim_result.extrapolation_warnings,
        baseline_predictions=sim_result.baseline_predictions,
        simulated_predictions=sim_result.simulated_predictions,
    )
