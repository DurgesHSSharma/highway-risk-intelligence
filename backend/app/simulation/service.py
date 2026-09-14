"""Phase 10: orchestrates one what-if simulation request -- look up the
snapshot, reject terminal snapshots and invalid override fields, build the
baseline/simulated feature rows, and run both through the exact same Phase
6 model registry (`app.ml.predict.predict_all_tasks`). See
docs/WHATIF_SIMULATOR.md for the full design and
`app.routers.simulation` for how these exceptions become HTTP responses.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Project, ProjectSnapshot
from app.ml.features import build_predictor_row
from app.ml.predict import predict_all_tasks
from app.simulation.extrapolation import ExtrapolationWarning, check_extrapolation
from app.simulation.overrides import InvalidOverrideField, OverrideDetail, apply_overrides, validate_override_fields


class ProjectNotFoundError(LookupError):
    pass


class SnapshotNotFoundError(LookupError):
    pass


class TerminalSnapshotError(ValueError):
    pass


class InvalidOverrideFieldsError(ValueError):
    def __init__(self, invalid_fields: list[InvalidOverrideField]):
        self.invalid_fields = invalid_fields
        super().__init__(f"Invalid override field(s): {[f.field for f in invalid_fields]}")


@dataclass(frozen=True)
class SimulationResult:
    project_id: str
    reporting_month: str
    overrides: list[OverrideDetail]
    extrapolation_warnings: list[ExtrapolationWarning]
    baseline_predictions: dict
    simulated_predictions: dict


def run_simulation(
    db: Session, project_id: str, reporting_month: str, requested_overrides: dict[str, Any]
) -> SimulationResult:
    project = db.get(Project, project_id)
    if project is None:
        raise ProjectNotFoundError(f"Project '{project_id}' not found.")

    snapshot = db.execute(
        select(ProjectSnapshot)
        .where(ProjectSnapshot.project_id == project_id)
        .where(ProjectSnapshot.reporting_month == reporting_month)
    ).scalar_one_or_none()
    if snapshot is None:
        raise SnapshotNotFoundError(
            f"No snapshot for project '{project_id}' at reporting_month '{reporting_month}'."
        )

    if snapshot.is_terminal_snapshot:
        raise TerminalSnapshotError(
            f"Snapshot for project '{project_id}' at reporting_month '{reporting_month}' is terminal."
        )

    invalid_fields = validate_override_fields(requested_overrides)
    if invalid_fields:
        raise InvalidOverrideFieldsError(invalid_fields)

    # Same computation GET /predict uses for this snapshot -- never
    # reimplemented (raises FeatureConstructionError -> HTTP 422, handled by
    # the router exactly like the Phase 6 predict endpoint).
    baseline_row = build_predictor_row(db, project_id, reporting_month)
    simulated_row, override_details = apply_overrides(baseline_row, requested_overrides)
    extrapolation_warnings = check_extrapolation(requested_overrides)

    baseline_predictions = predict_all_tasks(baseline_row)
    simulated_predictions = predict_all_tasks(simulated_row)

    return SimulationResult(
        project_id=project_id,
        reporting_month=reporting_month,
        overrides=override_details,
        extrapolation_warnings=extrapolation_warnings,
        baseline_predictions=baseline_predictions,
        simulated_predictions=simulated_predictions,
    )
