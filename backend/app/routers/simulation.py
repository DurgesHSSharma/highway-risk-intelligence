"""Phase 10 what-if scenario simulator:
POST /projects/{project_id}/simulate?reporting_month=YYYY-MM.

Re-scores a real, non-terminal project snapshot twice -- once unmodified
(baseline) and once with one or more caller-supplied ABSOLUTE overrides
applied to permitted predictor fields (simulated) -- through the exact same
Phase 6 model registry (`app.ml.registry.TASK_MODEL_REGISTRY`) and
preprocessing pipelines used by `GET /projects/{project_id}/predict`. No
model is retrained, refit, or reloaded here. See docs/WHATIF_SIMULATOR.md
for the full design and the mandatory disclaimer text.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.ml.features import FeatureConstructionError
from app.schemas.predictions import SYNTHETIC_DATA_DISCLAIMER_MODEL
from app.schemas.simulation import (
    TERMINAL_SIMULATION_REJECTION_MESSAGE,
    ExtrapolationWarningOut,
    OverrideDetailOut,
    PredictionsBundle,
    SimulationResponse,
)
from app.simulation.service import (
    InvalidOverrideFieldsError,
    ProjectNotFoundError,
    SnapshotNotFoundError,
    TerminalSnapshotError,
    run_simulation,
)

router = APIRouter(prefix="/projects", tags=["simulation"])


@router.post("/{project_id}/simulate", response_model=SimulationResponse)
def simulate(
    project_id: str,
    reporting_month: str = Query(..., description="YYYY-MM"),
    overrides: dict[str, Any] = Body(
        default_factory=dict,
        description=(
            "One or more permitted predictor fields mapped to their new ABSOLUTE "
            "hypothetical values (never a delta like '+20' or 'increase by 20')."
        ),
    ),
    db: Session = Depends(get_db),
) -> SimulationResponse:
    try:
        result = run_simulation(db, project_id, reporting_month, overrides)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SnapshotNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TerminalSnapshotError as exc:
        raise HTTPException(status_code=422, detail=TERMINAL_SIMULATION_REJECTION_MESSAGE) from exc
    except InvalidOverrideFieldsError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "One or more override fields are not permitted predictor fields.",
                "invalid_fields": [{"field": f.field, "reason": f.reason} for f in exc.invalid_fields],
            },
        ) from exc
    except FeatureConstructionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return SimulationResponse(
        project_id=result.project_id,
        reporting_month=result.reporting_month,
        is_terminal_snapshot=False,
        overrides=[OverrideDetailOut(**vars(o)) for o in result.overrides],
        extrapolation_warnings=[ExtrapolationWarningOut(**vars(w)) for w in result.extrapolation_warnings],
        baseline_predictions=PredictionsBundle(**result.baseline_predictions),
        simulated_predictions=PredictionsBundle(**result.simulated_predictions),
        synthetic_data_disclaimer=SYNTHETIC_DATA_DISCLAIMER_MODEL,
    )
