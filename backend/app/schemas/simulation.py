from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from app.schemas.predictions import (
    CostOverrunResult,
    FinalCostOverrunPctResult,
    FinalDelayDaysResult,
    SignificantDelayResult,
)

SIMULATION_DISCLAIMER = (
    "This is a model re-scoring under a hypothetical assumption, not a prediction of what "
    "will actually happen. It is not a validated causal estimate."
)

TERMINAL_SIMULATION_REJECTION_MESSAGE = (
    "This snapshot is terminal (is_terminal_snapshot=true): it already contains fields "
    "that encode the known final outcome, so simulating a hypothetical override from it "
    "would not isolate the override's effect from the already-known result. Select an "
    "earlier, non-terminal snapshot for this project instead."
)


class OverrideDetailOut(BaseModel):
    field: str
    original_value: Any
    simulated_value: Any
    delta: float | None


class ExtrapolationWarningOut(BaseModel):
    field: str
    simulated_value: float
    training_min: float
    training_max: float
    message: str


class PredictionsBundle(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    significant_delay: SignificantDelayResult
    final_delay_days: FinalDelayDaysResult
    cost_overrun: CostOverrunResult
    final_cost_overrun_pct: FinalCostOverrunPctResult


class SimulationResponse(BaseModel):
    project_id: str
    reporting_month: str
    is_terminal_snapshot: bool
    overrides: list[OverrideDetailOut]
    extrapolation_warnings: list[ExtrapolationWarningOut]
    baseline_predictions: PredictionsBundle
    simulated_predictions: PredictionsBundle
    synthetic_data_disclaimer: str
    simulation_disclaimer: str = SIMULATION_DISCLAIMER
