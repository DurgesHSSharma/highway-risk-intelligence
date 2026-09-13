"""Builds the exact 45-column permitted predictor feature row (see
scripts.prepare_features.PREDICTOR_COLUMNS) for one (project_id,
reporting_month) snapshot, straight from the database.

The engineered features (rolling trends, ratios, etc.) are computed by
calling `scripts.prepare_features.add_engineered_features` directly on the
project's own snapshot history up to and including the target month --
never reimplemented here. This is safe because every engineered feature in
that function is a per-project rolling/diff/ratio computation that only
looks at the current row and earlier rows of the same project (Phase 3's
own design principle, restated in that module's docstring); truncating a
project's history to a prefix therefore reproduces the exact same value at
the target row as running it over the full CSV (verified in
tests/test_prediction_consistency.py against data/processed/*_features.csv).
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Project, ProjectSnapshot
from scripts.prepare_features import (
    DUPLICATE_COLUMNS_DROPPED,
    PREDICTOR_COLUMNS,
    add_engineered_features,
)


class ProjectNotFoundError(LookupError):
    pass


class SnapshotNotFoundError(LookupError):
    pass


class FeatureConstructionError(ValueError):
    pass


def _snapshot_to_raw_row(project: Project, snap: ProjectSnapshot) -> dict:
    return {
        "project_id": project.project_id,
        "data_provenance": project.data_provenance,
        "project_name": project.project_name,
        "highway_number": project.highway_number,
        "state": project.state,
        "project_type": project.project_type,
        "contractor": project.contractor,
        "project_length_km": project.project_length_km,
        "original_contract_value_inr_cr": project.original_contract_value_inr_cr,
        "planned_duration_months": project.planned_duration_months,
        "reporting_month": snap.reporting_month,
        "months_since_start": snap.months_since_start,
        "project_status": snap.project_status,
        "planned_physical_progress_pct": snap.planned_physical_progress_pct,
        "actual_physical_progress_pct": snap.actual_physical_progress_pct,
        "physical_progress_variance_pct": snap.physical_progress_variance_pct,
        "planned_financial_progress_pct": snap.planned_financial_progress_pct,
        "actual_financial_progress_pct": snap.actual_financial_progress_pct,
        "financial_progress_variance_pct": snap.financial_progress_variance_pct,
        "planned_expenditure_inr_cr": snap.planned_expenditure_inr_cr,
        "actual_expenditure_inr_cr": snap.actual_expenditure_inr_cr,
        "expenditure_variance_pct": snap.expenditure_variance_pct,
        "planned_cost_to_date_inr_cr": snap.planned_cost_to_date_inr_cr,
        "actual_cost_to_date_inr_cr": snap.actual_cost_to_date_inr_cr,
        "material_cost_inr_cr": snap.material_cost_inr_cr,
        "labour_cost_inr_cr": snap.labour_cost_inr_cr,
        "equipment_cost_inr_cr": snap.equipment_cost_inr_cr,
        "variation_cost_inr_cr": snap.variation_cost_inr_cr,
        "delay_related_cost_inr_cr": snap.delay_related_cost_inr_cr,
        "land_acquisition_delay_days": snap.land_acquisition_delay_days,
        "utility_shifting_delay_days": snap.utility_shifting_delay_days,
        "environment_clearance_delay_days": snap.environment_clearance_delay_days,
        "material_delay_days": snap.material_delay_days,
        "labour_shortage_days": snap.labour_shortage_days,
        "equipment_unavailability_days": snap.equipment_unavailability_days,
        "weather_disruption_days": snap.weather_disruption_days,
        "contractor_productivity_factor": snap.contractor_productivity_factor,
        "traffic_diversion_delay_days": snap.traffic_diversion_delay_days,
        "design_change_delay_days": snap.design_change_delay_days,
        "approval_delay_days": snap.approval_delay_days,
        "final_delay_days": snap.final_delay_days,
        "significant_delay": snap.significant_delay,
        "final_cost_overrun_pct": snap.final_cost_overrun_pct,
        "cost_overrun": snap.cost_overrun,
    }


def _project_history_dataframe(db: Session, project_id: str, up_to_month: str) -> pd.DataFrame:
    project = db.get(Project, project_id)
    if project is None:
        raise ProjectNotFoundError(f"No project with project_id={project_id!r}")

    stmt = (
        select(ProjectSnapshot)
        .where(ProjectSnapshot.project_id == project_id)
        .where(ProjectSnapshot.reporting_month <= up_to_month)
        .order_by(ProjectSnapshot.reporting_month.asc())
    )
    snapshots = list(db.execute(stmt).scalars().all())
    if not snapshots or snapshots[-1].reporting_month != up_to_month:
        raise SnapshotNotFoundError(
            f"No snapshot for project_id={project_id!r} at reporting_month={up_to_month!r}"
        )

    return pd.DataFrame([_snapshot_to_raw_row(project, s) for s in snapshots])


def build_predictor_row(db: Session, project_id: str, reporting_month: str) -> pd.DataFrame:
    """Returns a 1-row DataFrame with exactly `PREDICTOR_COLUMNS`, ready to
    pass straight into a loaded model Pipeline's `.predict`/`.predict_proba`.

    Raises ProjectNotFoundError / SnapshotNotFoundError (-> HTTP 404 in the
    router) or FeatureConstructionError (-> HTTP 422) if a valid feature row
    cannot be built.
    """
    df = _project_history_dataframe(db, project_id, reporting_month)
    try:
        df = df.drop(columns=[c for c in DUPLICATE_COLUMNS_DROPPED if c in df.columns])
        featured = add_engineered_features(df)
        target_row = featured[featured["reporting_month"] == reporting_month]
        if len(target_row) != 1:
            raise FeatureConstructionError(
                f"Expected exactly one row for project_id={project_id!r} "
                f"reporting_month={reporting_month!r}, found {len(target_row)}."
            )
        row = target_row[PREDICTOR_COLUMNS].reset_index(drop=True)
    except FeatureConstructionError:
        raise
    except KeyError as exc:
        raise FeatureConstructionError(
            f"Could not construct the predictor feature row for project_id={project_id!r} "
            f"reporting_month={reporting_month!r}: missing required field {exc}."
        ) from exc
    except (ZeroDivisionError, ValueError, TypeError) as exc:
        raise FeatureConstructionError(
            f"Could not construct the predictor feature row for project_id={project_id!r} "
            f"reporting_month={reporting_month!r}: {exc}."
        ) from exc
    return row
