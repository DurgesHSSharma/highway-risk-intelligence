from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    project_id: str
    data_provenance: str
    project_name: str
    highway_number: str
    state: str
    project_type: str
    contractor: str | None
    project_length_km: float
    original_contract_value_inr_cr: float
    planned_start_date: date
    planned_completion_date: date
    planned_duration_months: int
    current_status: str


class ProjectListResponse(BaseModel):
    items: list[ProjectOut]
    page: int
    page_size: int
    total: int


class SnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    project_id: str
    reporting_month: str
    months_since_start: int
    project_status: str
    is_terminal_snapshot: bool

    planned_physical_progress_pct: float
    actual_physical_progress_pct: float
    physical_progress_variance_pct: float
    planned_financial_progress_pct: float
    actual_financial_progress_pct: float | None
    financial_progress_variance_pct: float | None

    planned_expenditure_inr_cr: float
    actual_expenditure_inr_cr: float | None
    expenditure_variance_pct: float | None
    planned_cost_to_date_inr_cr: float
    actual_cost_to_date_inr_cr: float
    material_cost_inr_cr: float
    labour_cost_inr_cr: float
    equipment_cost_inr_cr: float
    variation_cost_inr_cr: float | None
    delay_related_cost_inr_cr: float

    land_acquisition_delay_days: float
    utility_shifting_delay_days: float
    environment_clearance_delay_days: float
    material_delay_days: float
    labour_shortage_days: float
    equipment_unavailability_days: float | None
    weather_disruption_days: float | None
    contractor_productivity_factor: float
    traffic_diversion_delay_days: float
    design_change_delay_days: float
    approval_delay_days: float

    final_delay_days: int
    significant_delay: int
    final_cost_overrun_pct: float
    cost_overrun: int
