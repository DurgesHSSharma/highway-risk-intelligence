"""Phase 17B request schemas for the project lifecycle write endpoints
(create / edit / archive / reactivate / monthly snapshot) -- the first
WRITE surface this app has ever had.

Field names and types reuse the existing `Project` / `ProjectSnapshot`
columns (app/db/models.py) exactly -- no duplicate field names invented.
Responses reuse the existing `ProjectOut` / `SnapshotOut` schemas
(app/schemas/projects.py) unchanged; this module only defines the request
bodies. See app/projects/lifecycle.py for the validation/business rules
these feed into.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.validation import MONTH_DESCRIPTION, MONTH_PATTERN

# Same convention scripts/generate_dataset.py uses for the synthetic corpus
# (HRI-0001..HRI-0400) -- a caller-supplied ID must match it too, so every
# project_id in the system (SYNTHETIC or USER_ENTERED) stays in one
# recognizable family. 4+ digits (not exactly 4) so IDs can keep growing
# past HRI-9999 without ever colliding with a 4-digit one.
PROJECT_ID_PATTERN = r"^HRI-\d{4,}$"


class ProjectCreate(BaseModel):
    project_id: str | None = Field(
        default=None,
        description="Optional caller-supplied ID matching HRI-NNNN. Omit to auto-generate the next available one.",
    )
    project_name: str = Field(min_length=1, max_length=200)
    highway_number: str = Field(min_length=1, max_length=50)
    state: str = Field(min_length=1, max_length=100)
    project_type: str = Field(min_length=1, max_length=100)
    contractor: str | None = Field(default=None, max_length=200)
    project_length_km: float = Field(gt=0)
    original_contract_value_inr_cr: float = Field(gt=0)
    planned_start_date: date
    planned_completion_date: date
    planned_duration_months: int = Field(gt=0)

    @field_validator("project_id")
    @classmethod
    def _validate_project_id(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(PROJECT_ID_PATTERN, value):
            raise ValueError("project_id must match HRI-NNNN (e.g. HRI-0401).")
        return value


class ProjectUpdate(BaseModel):
    """Partial update -- every field is optional; only fields actually
    present in the request body are changed (see
    app/projects/lifecycle.py::update_project, which reads this via
    `model_dump(exclude_unset=True)`). `project_id` and `data_provenance`
    are never editable here: identity and data lineage are not
    project-information fields."""

    project_name: str | None = Field(default=None, min_length=1, max_length=200)
    highway_number: str | None = Field(default=None, min_length=1, max_length=50)
    state: str | None = Field(default=None, min_length=1, max_length=100)
    project_type: str | None = Field(default=None, min_length=1, max_length=100)
    contractor: str | None = Field(default=None, max_length=200)
    project_length_km: float | None = Field(default=None, gt=0)
    original_contract_value_inr_cr: float | None = Field(default=None, gt=0)
    planned_start_date: date | None = None
    planned_completion_date: date | None = None
    planned_duration_months: int | None = Field(default=None, gt=0)


class SnapshotCreate(BaseModel):
    """One monthly progress update for a project. Feeds the same 45-column
    predictor pipeline every other endpoint already uses
    (app.ml.features.build_predictor_row) -- never a second feature
    definition.

    Terminal outcome fields (final_delay_days / significant_delay /
    final_cost_overrun_pct / cost_overrun) are accepted ONLY when
    `project_status="Completed"`, and are REQUIRED in that case -- an
    ordinary "Ongoing" monthly update must never carry them (see
    app/projects/lifecycle.py::add_monthly_snapshot, which enforces this;
    it cannot be expressed as a pure Pydantic constraint since it depends
    on another field's value).
    """

    reporting_month: str = Field(pattern=MONTH_PATTERN, description=MONTH_DESCRIPTION)
    project_status: Literal["Ongoing", "Completed"] = "Ongoing"

    planned_physical_progress_pct: float = Field(ge=0, le=100)
    actual_physical_progress_pct: float = Field(ge=0, le=100)
    planned_financial_progress_pct: float = Field(ge=0, le=100)
    actual_financial_progress_pct: float | None = Field(default=None, ge=0, le=100)

    planned_cost_to_date_inr_cr: float = Field(
        ge=0,
        description=(
            "Cumulative planned cost to date per the government-approved schedule. "
            "Also stored as planned_expenditure_inr_cr -- an exact duplicate in the "
            "existing schema (see app/db/models.py docstring), so it is asked for once here."
        ),
    )
    actual_expenditure_inr_cr: float | None = Field(default=None, ge=0)
    actual_cost_to_date_inr_cr: float = Field(ge=0)
    material_cost_inr_cr: float = Field(ge=0)
    labour_cost_inr_cr: float = Field(ge=0)
    equipment_cost_inr_cr: float = Field(ge=0)
    variation_cost_inr_cr: float | None = Field(default=None, ge=0)
    delay_related_cost_inr_cr: float = Field(ge=0)

    land_acquisition_delay_days: float = Field(ge=0)
    utility_shifting_delay_days: float = Field(ge=0)
    environment_clearance_delay_days: float = Field(ge=0)
    material_delay_days: float = Field(ge=0)
    labour_shortage_days: float = Field(ge=0)
    equipment_unavailability_days: float | None = Field(default=None, ge=0)
    weather_disruption_days: float | None = Field(default=None, ge=0)
    contractor_productivity_factor: float = Field(gt=0)
    traffic_diversion_delay_days: float = Field(ge=0)
    design_change_delay_days: float = Field(ge=0)
    approval_delay_days: float = Field(ge=0)

    # Actual outcome -- see class docstring. Only meaningful/accepted when
    # project_status="Completed".
    final_delay_days: int | None = Field(default=None, ge=0)
    significant_delay: Literal[0, 1] | None = None
    final_cost_overrun_pct: float | None = None
    cost_overrun: Literal[0, 1] | None = None
