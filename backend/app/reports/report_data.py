"""Phase 13 report-data service for GET /projects/{project_id}/report.pdf.

Combines two things the existing frontend already fetches separately for
the on-screen Reports page (`getProject` + `getRiskSummary`) into one
structure the PDF builder renders:

1. The exact `Project`/`ProjectSnapshot` rows (`app.db.models`) other
   routers already read, for progress/cost/delay fields that the
   risk-summary response doesn't carry.
2. `app.decision_support.synthesizer.run_risk_summary` -- the EXACT same
   function `GET /projects/{id}/risk-summary` calls -- for predictions,
   live SHAP drivers, RAG evidence, potential inconsistencies, and the
   illustrative scenario. No prediction/SHAP/RAG/simulation logic is
   reimplemented here; this module only reads and reshapes.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Project, ProjectSnapshot
from app.decision_support.synthesizer import (
    ProjectNotFoundError,
    RiskSummaryResult,
    SnapshotNotFoundError,
    run_risk_summary,
)

__all__ = [
    "ReportData",
    "ProjectNotFoundError",
    "SnapshotNotFoundError",
    "build_report_data",
]


@dataclass(frozen=True)
class ReportData:
    project: Project
    snapshot: ProjectSnapshot
    risk: RiskSummaryResult


def build_report_data(db: Session, project_id: str, reporting_month: str) -> ReportData:
    """Raises `ProjectNotFoundError`/`SnapshotNotFoundError` (identical to
    the risk-summary endpoint) when the project or snapshot doesn't exist --
    `run_risk_summary` performs that lookup/validation first, so the two
    plain row reads below (same pattern as `app.routers.projects`) never
    hit a missing row."""
    risk = run_risk_summary(db, project_id, reporting_month)

    project = db.get(Project, project_id)
    snapshot = db.execute(
        select(ProjectSnapshot)
        .where(ProjectSnapshot.project_id == project_id)
        .where(ProjectSnapshot.reporting_month == reporting_month)
    ).scalar_one_or_none()

    return ReportData(project=project, snapshot=snapshot, risk=risk)
