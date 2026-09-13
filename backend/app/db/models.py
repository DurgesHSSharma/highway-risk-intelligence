"""SQLAlchemy ORM models for the Phase 6 SQLite data layer.

Column-to-table assignment was decided by inspecting which raw columns of
`data/synthetic/highway_project_snapshots.csv` are constant within a
`project_id` (-> `projects`) versus vary by `reporting_month` (->
`project_snapshots`) -- see docs/API_AND_DATABASE.md section "Schema
decisions" for the full inspection table. Two deliberate deviations from
the Phase 6 brief's example field list, both because the actual schema
differs from the example:

- `project_status` is NOT constant per project (every project starts
  "Ongoing" and has exactly one terminal "Completed" row), so it lives on
  `ProjectSnapshot`, not `Project`.
- `final_delay_days`, `significant_delay`, `final_cost_overrun_pct`,
  `cost_overrun` ARE constant per project, but are kept on
  `ProjectSnapshot` (repeated on every row, mirroring the source CSV
  exactly) per the brief's explicit instruction to preserve "target/outcome
  fields where they are actually part of the source schema" on the
  snapshots table -- this is also what the terminal-snapshot prediction
  endpoint reads directly off the matched row.

The two exact-duplicate column pairs identified during Phase 3 EDA
(`planned_expenditure_inr_cr` == `planned_cost_to_date_inr_cr`,
`expenditure_variance_pct` == `financial_progress_variance_pct`) are kept
here (unlike the Phase 3 processed features, which drop them) because this
table's job is a faithful, reconcilable mirror of the source CSV, not a
leakage-audited model input.
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Date,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Project(Base):
    __tablename__ = "projects"

    project_id: Mapped[str] = mapped_column(String, primary_key=True)
    data_provenance: Mapped[str] = mapped_column(String, nullable=False)
    project_name: Mapped[str] = mapped_column(String, nullable=False)
    highway_number: Mapped[str] = mapped_column(String, nullable=False)
    state: Mapped[str] = mapped_column(String, nullable=False, index=True)
    project_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    contractor: Mapped[str | None] = mapped_column(String, nullable=True)
    project_length_km: Mapped[float] = mapped_column(Float, nullable=False)
    original_contract_value_inr_cr: Mapped[float] = mapped_column(Float, nullable=False)
    planned_start_date: Mapped[str] = mapped_column(Date, nullable=False)
    planned_completion_date: Mapped[str] = mapped_column(Date, nullable=False)
    planned_duration_months: Mapped[int] = mapped_column(Integer, nullable=False)

    snapshots: Mapped[list["ProjectSnapshot"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class ProjectSnapshot(Base):
    __tablename__ = "project_snapshots"
    __table_args__ = (
        UniqueConstraint("project_id", "reporting_month", name="uq_project_reporting_month"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        String, ForeignKey("projects.project_id"), nullable=False, index=True
    )
    reporting_month: Mapped[str] = mapped_column(String(7), nullable=False, index=True)
    months_since_start: Mapped[int] = mapped_column(Integer, nullable=False)
    project_status: Mapped[str] = mapped_column(String, nullable=False, index=True)

    planned_physical_progress_pct: Mapped[float] = mapped_column(Float, nullable=False)
    actual_physical_progress_pct: Mapped[float] = mapped_column(Float, nullable=False)
    physical_progress_variance_pct: Mapped[float] = mapped_column(Float, nullable=False)
    planned_financial_progress_pct: Mapped[float] = mapped_column(Float, nullable=False)
    actual_financial_progress_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    financial_progress_variance_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    planned_expenditure_inr_cr: Mapped[float] = mapped_column(Float, nullable=False)
    actual_expenditure_inr_cr: Mapped[float | None] = mapped_column(Float, nullable=True)
    expenditure_variance_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    planned_cost_to_date_inr_cr: Mapped[float] = mapped_column(Float, nullable=False)
    actual_cost_to_date_inr_cr: Mapped[float] = mapped_column(Float, nullable=False)
    material_cost_inr_cr: Mapped[float] = mapped_column(Float, nullable=False)
    labour_cost_inr_cr: Mapped[float] = mapped_column(Float, nullable=False)
    equipment_cost_inr_cr: Mapped[float] = mapped_column(Float, nullable=False)
    variation_cost_inr_cr: Mapped[float | None] = mapped_column(Float, nullable=True)
    delay_related_cost_inr_cr: Mapped[float] = mapped_column(Float, nullable=False)

    land_acquisition_delay_days: Mapped[float] = mapped_column(Float, nullable=False)
    utility_shifting_delay_days: Mapped[float] = mapped_column(Float, nullable=False)
    environment_clearance_delay_days: Mapped[float] = mapped_column(Float, nullable=False)
    material_delay_days: Mapped[float] = mapped_column(Float, nullable=False)
    labour_shortage_days: Mapped[float] = mapped_column(Float, nullable=False)
    equipment_unavailability_days: Mapped[float | None] = mapped_column(Float, nullable=True)
    weather_disruption_days: Mapped[float | None] = mapped_column(Float, nullable=True)
    contractor_productivity_factor: Mapped[float] = mapped_column(Float, nullable=False)
    traffic_diversion_delay_days: Mapped[float] = mapped_column(Float, nullable=False)
    design_change_delay_days: Mapped[float] = mapped_column(Float, nullable=False)
    approval_delay_days: Mapped[float] = mapped_column(Float, nullable=False)

    is_terminal_snapshot: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True)
    final_delay_days: Mapped[int] = mapped_column(Integer, nullable=False)
    significant_delay: Mapped[int] = mapped_column(Integer, nullable=False)
    final_cost_overrun_pct: Mapped[float] = mapped_column(Float, nullable=False)
    cost_overrun: Mapped[int] = mapped_column(Integer, nullable=False)

    project: Mapped["Project"] = relationship(back_populates="snapshots")
