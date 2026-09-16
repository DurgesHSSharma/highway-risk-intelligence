"""Phase 6 data loader: CSV -> SQLite, reusable by both `scripts/load_db.py`
and the test suite.

Strategy: **deterministic clear-and-reload**, not upsert. On every run, all
existing SYNTHETIC `project_snapshots` then `projects` rows are deleted
inside a single transaction and freshly reinserted from the source CSV.
This is idempotent by construction (running it twice yields byte-identical
row counts and content) and, for a prototype of this size (400 projects /
8,740 snapshots), avoids the extra complexity and failure modes of a
column-by-column upsert diff. See docs/API_AND_DATABASE.md "Loading
process" for the full rationale.

Phase 17B: this CSV only ever contains `data_provenance == "SYNTHETIC"`
rows, but the database itself may also hold `USER_ENTERED` projects
created through the project lifecycle API. Every clear-and-reload in this
module is scoped to SYNTHETIC rows only -- a USER_ENTERED project, its
snapshots, and its cached predictions are never deleted by this function,
no matter how many times it's rerun. This closes what was previously a
landmine: re-running this loader (something routine after any dataset/
schema change) would otherwise silently destroy every manually-added
project. See tests/test_loader_preserves_user_projects.py for the
regression proof.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import delete, func, insert, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.db.base import create_all, engine as default_engine
from app.db.models import (
    DATA_PROVENANCE_SYNTHETIC,
    Project,
    ProjectSnapshot,
    PortfolioPredictionCache,
)

# The only provenance value this CSV-backed loader ever writes or clears.
# A `USER_ENTERED` project (Phase 17B) is never touched by this module.
SYNTHETIC_PROVENANCE = DATA_PROVENANCE_SYNTHETIC

# Columns that are constant per project_id -- see app/db/models.py docstring
# for the inspection this is based on and the two deliberate deviations
# from the Phase 6 brief's example field list.
PROJECT_LEVEL_COLUMNS = [
    "data_provenance",
    "project_name",
    "highway_number",
    "state",
    "project_type",
    "contractor",
    "project_length_km",
    "original_contract_value_inr_cr",
    "planned_start_date",
    "planned_completion_date",
    "planned_duration_months",
]

SNAPSHOT_LEVEL_COLUMNS = [
    "reporting_month",
    "months_since_start",
    "project_status",
    "planned_physical_progress_pct",
    "actual_physical_progress_pct",
    "physical_progress_variance_pct",
    "planned_financial_progress_pct",
    "actual_financial_progress_pct",
    "financial_progress_variance_pct",
    "planned_expenditure_inr_cr",
    "actual_expenditure_inr_cr",
    "expenditure_variance_pct",
    "planned_cost_to_date_inr_cr",
    "actual_cost_to_date_inr_cr",
    "material_cost_inr_cr",
    "labour_cost_inr_cr",
    "equipment_cost_inr_cr",
    "variation_cost_inr_cr",
    "delay_related_cost_inr_cr",
    "land_acquisition_delay_days",
    "utility_shifting_delay_days",
    "environment_clearance_delay_days",
    "material_delay_days",
    "labour_shortage_days",
    "equipment_unavailability_days",
    "weather_disruption_days",
    "contractor_productivity_factor",
    "traffic_diversion_delay_days",
    "design_change_delay_days",
    "approval_delay_days",
    "final_delay_days",
    "significant_delay",
    "final_cost_overrun_pct",
    "cost_overrun",
]

REQUIRED_RAW_COLUMNS = ["project_id"] + PROJECT_LEVEL_COLUMNS + SNAPSHOT_LEVEL_COLUMNS


@dataclass(frozen=True)
class LoadSummary:
    source_csv_path: Path
    source_row_count: int
    source_unique_projects: int
    source_unique_project_month_pairs: int
    projects_loaded: int
    snapshots_loaded: int
    excluded_rows: int
    excluded_reason: str | None
    # Phase 17B: USER_ENTERED rows this reload found and left untouched.
    # Always 0 on a fresh/synthetic-only database.
    preserved_user_projects: int = 0
    preserved_user_snapshots: int = 0

    @property
    def reconciled(self) -> bool:
        return (
            self.excluded_rows == 0
            and self.projects_loaded == self.source_unique_projects
            and self.snapshots_loaded == self.source_row_count
            and self.snapshots_loaded == self.source_unique_project_month_pairs
        )


def _none_if_nan(value):
    if value is None:
        return None
    if isinstance(value, float) and np.isnan(value):
        return None
    if isinstance(value, str):
        return value
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _load_raw_dataframe(csv_path: Path) -> pd.DataFrame:
    if not csv_path.exists():
        raise FileNotFoundError(
            f"Phase 2 dataset not found at {csv_path}. Run scripts/generate_dataset.py "
            "first (see data/README.md)."
        )
    df = pd.read_csv(csv_path)
    missing = [c for c in REQUIRED_RAW_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Source CSV is missing required columns: {missing}")
    return df.sort_values(["project_id", "reporting_month"]).reset_index(drop=True)


def _build_project_rows(df: pd.DataFrame) -> list[dict]:
    per_project = df.groupby("project_id", sort=False).first().reset_index()
    rows = []
    for _, r in per_project.iterrows():
        rows.append(
            {
                "project_id": r["project_id"],
                "data_provenance": r["data_provenance"],
                "project_name": r["project_name"],
                "highway_number": r["highway_number"],
                "state": r["state"],
                "project_type": r["project_type"],
                "contractor": _none_if_nan(r["contractor"]),
                "project_length_km": float(r["project_length_km"]),
                "original_contract_value_inr_cr": float(r["original_contract_value_inr_cr"]),
                "planned_start_date": pd.to_datetime(r["planned_start_date"]).date(),
                "planned_completion_date": pd.to_datetime(r["planned_completion_date"]).date(),
                "planned_duration_months": int(r["planned_duration_months"]),
            }
        )
    return rows


def _build_snapshot_rows(df: pd.DataFrame) -> list[dict]:
    rows = []
    for _, r in df.iterrows():
        is_terminal = bool(r["project_status"] == "Completed")
        rows.append(
            {
                "project_id": r["project_id"],
                "reporting_month": r["reporting_month"],
                "months_since_start": int(r["months_since_start"]),
                "project_status": r["project_status"],
                "planned_physical_progress_pct": float(r["planned_physical_progress_pct"]),
                "actual_physical_progress_pct": float(r["actual_physical_progress_pct"]),
                "physical_progress_variance_pct": float(r["physical_progress_variance_pct"]),
                "planned_financial_progress_pct": float(r["planned_financial_progress_pct"]),
                "actual_financial_progress_pct": _none_if_nan(r["actual_financial_progress_pct"]),
                "financial_progress_variance_pct": _none_if_nan(r["financial_progress_variance_pct"]),
                "planned_expenditure_inr_cr": float(r["planned_expenditure_inr_cr"]),
                "actual_expenditure_inr_cr": _none_if_nan(r["actual_expenditure_inr_cr"]),
                "expenditure_variance_pct": _none_if_nan(r["expenditure_variance_pct"]),
                "planned_cost_to_date_inr_cr": float(r["planned_cost_to_date_inr_cr"]),
                "actual_cost_to_date_inr_cr": float(r["actual_cost_to_date_inr_cr"]),
                "material_cost_inr_cr": float(r["material_cost_inr_cr"]),
                "labour_cost_inr_cr": float(r["labour_cost_inr_cr"]),
                "equipment_cost_inr_cr": float(r["equipment_cost_inr_cr"]),
                "variation_cost_inr_cr": _none_if_nan(r["variation_cost_inr_cr"]),
                "delay_related_cost_inr_cr": float(r["delay_related_cost_inr_cr"]),
                "land_acquisition_delay_days": float(r["land_acquisition_delay_days"]),
                "utility_shifting_delay_days": float(r["utility_shifting_delay_days"]),
                "environment_clearance_delay_days": float(r["environment_clearance_delay_days"]),
                "material_delay_days": float(r["material_delay_days"]),
                "labour_shortage_days": float(r["labour_shortage_days"]),
                "equipment_unavailability_days": _none_if_nan(r["equipment_unavailability_days"]),
                "weather_disruption_days": _none_if_nan(r["weather_disruption_days"]),
                "contractor_productivity_factor": float(r["contractor_productivity_factor"]),
                "traffic_diversion_delay_days": float(r["traffic_diversion_delay_days"]),
                "design_change_delay_days": float(r["design_change_delay_days"]),
                "approval_delay_days": float(r["approval_delay_days"]),
                "is_terminal_snapshot": is_terminal,
                "final_delay_days": int(r["final_delay_days"]),
                "significant_delay": int(r["significant_delay"]),
                "final_cost_overrun_pct": float(r["final_cost_overrun_pct"]),
                "cost_overrun": int(r["cost_overrun"]),
            }
        )
    return rows


def load_database(
    csv_path: Path,
    bind: Engine | None = None,
) -> LoadSummary:
    """Clear and reload SYNTHETIC `projects` + `project_snapshots` from `csv_path`.

    Idempotent: calling this twice in a row against the same CSV produces
    identical row counts and content both times.

    Phase 17B: scoped to `data_provenance == "SYNTHETIC"` throughout. Any
    USER_ENTERED project (and its snapshots/cache rows) already in the
    database is preserved exactly as-is -- counted and reported via
    `LoadSummary.preserved_user_projects` / `preserved_user_snapshots`,
    never deleted or reinserted.
    """
    bind = bind or default_engine
    create_all(bind=bind)

    df = _load_raw_dataframe(csv_path)
    source_row_count = len(df)
    source_unique_projects = df["project_id"].nunique()
    source_unique_pairs = df.groupby(["project_id", "reporting_month"]).ngroups

    project_rows = _build_project_rows(df)
    snapshot_rows = _build_snapshot_rows(df)

    synthetic_project_ids = select(Project.project_id).where(
        Project.data_provenance == SYNTHETIC_PROVENANCE
    )

    session = Session(bind=bind)
    try:
        # Phase 14 added `portfolio_prediction_cache`, FK'd to
        # `projects.project_id` with FK enforcement ON (see app/db/base.py).
        # It must be cleared before `projects` on every reload, exactly like
        # `project_snapshots` below -- it is fully derived, reproducible
        # data (scripts/batch_score_portfolio.py), never hand-authored, so
        # clearing it here is consistent with this function's existing
        # clear-and-reload philosophy. Callers are expected to re-run batch
        # scoring after reloading the database.
        #
        # Phase 17B: every delete below is scoped to SYNTHETIC projects only
        # (the subquery above, evaluated against `projects` rows that still
        # exist at this point in the transaction). A USER_ENTERED project,
        # its snapshots, and any cached prediction for it are never reached
        # by this function, however many times it's rerun.
        session.execute(
            delete(PortfolioPredictionCache).where(
                PortfolioPredictionCache.project_id.in_(synthetic_project_ids)
            )
        )
        session.execute(
            delete(ProjectSnapshot).where(ProjectSnapshot.project_id.in_(synthetic_project_ids))
        )
        session.execute(delete(Project).where(Project.data_provenance == SYNTHETIC_PROVENANCE))
        session.flush()

        session.execute(insert(Project), project_rows)
        session.execute(insert(ProjectSnapshot), snapshot_rows)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    verify = Session(bind=bind)
    try:
        n_projects = verify.execute(
            select(func.count())
            .select_from(Project)
            .where(Project.data_provenance == SYNTHETIC_PROVENANCE)
        ).scalar_one()
        n_snapshots = verify.execute(
            select(func.count())
            .select_from(ProjectSnapshot)
            .join(Project, ProjectSnapshot.project_id == Project.project_id)
            .where(Project.data_provenance == SYNTHETIC_PROVENANCE)
        ).scalar_one()
        n_user_projects = verify.execute(
            select(func.count())
            .select_from(Project)
            .where(Project.data_provenance != SYNTHETIC_PROVENANCE)
        ).scalar_one()
        n_user_snapshots = verify.execute(
            select(func.count())
            .select_from(ProjectSnapshot)
            .join(Project, ProjectSnapshot.project_id == Project.project_id)
            .where(Project.data_provenance != SYNTHETIC_PROVENANCE)
        ).scalar_one()
    finally:
        verify.close()

    excluded = source_row_count - len(snapshot_rows)

    return LoadSummary(
        source_csv_path=csv_path,
        source_row_count=source_row_count,
        source_unique_projects=source_unique_projects,
        source_unique_project_month_pairs=source_unique_pairs,
        projects_loaded=n_projects,
        snapshots_loaded=n_snapshots,
        excluded_rows=excluded,
        excluded_reason=None if excluded == 0 else "unspecified row exclusion -- investigate",
        preserved_user_projects=n_user_projects,
        preserved_user_snapshots=n_user_snapshots,
    )


def count_orphan_snapshots(bind: Engine | None = None) -> int:
    """Snapshots whose project_id has no matching row in `projects`."""
    bind = bind or default_engine
    session = Session(bind=bind)
    try:
        stmt = (
            select(func.count())
            .select_from(ProjectSnapshot)
            .outerjoin(Project, ProjectSnapshot.project_id == Project.project_id)
            .where(Project.project_id.is_(None))
        )
        return session.execute(stmt).scalar_one()
    finally:
        session.close()


def count_duplicate_project_months(bind: Engine | None = None) -> int:
    """(project_id, reporting_month) pairs that appear more than once --
    should always be 0 given the UNIQUE constraint, checked independently
    here as a data-integrity assertion."""
    bind = bind or default_engine
    session = Session(bind=bind)
    try:
        stmt = (
            select(ProjectSnapshot.project_id, ProjectSnapshot.reporting_month, func.count())
            .group_by(ProjectSnapshot.project_id, ProjectSnapshot.reporting_month)
            .having(func.count() > 1)
        )
        return len(session.execute(stmt).all())
    finally:
        session.close()
