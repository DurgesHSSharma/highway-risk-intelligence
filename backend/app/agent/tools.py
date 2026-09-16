"""Phase 17C tool wrappers for "Ask HRI" -- THIN wrappers only, around
already-existing, already-tested HRI services. No prediction, RAG, SHAP,
analytics, contradiction, or simulation logic is reimplemented here; every
function below is a direct call into the exact same module the rest of
this app already uses for that capability:

    project lookup   -> app.db.models (same query app.routers.projects uses)
    risk             -> app.decision_support.synthesizer.run_risk_summary
    portfolio        -> app.analytics.portfolio_service.*
    documents/RAG    -> app.rag.retrieval.get_retrieval_service().retrieve()
    what-if          -> app.simulation.service.run_simulation

Each tool raises the SAME typed exceptions its underlying service already
raises (ProjectNotFoundError, SnapshotNotFoundError, etc.) -- never a new,
parallel exception hierarchy -- so app.agent.router handles them exactly
like every other HRI endpoint already does.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.entities import WhatIfIntent
from app.analytics import portfolio_service
from app.db.models import Project, ProjectSnapshot
from app.decision_support.synthesizer import RiskSummaryResult, run_risk_summary
from app.ml.features import build_predictor_row
from app.rag.answer import build_extractive_answer
from app.rag.retrieval import RetrievalResponse, get_retrieval_service
from app.simulation.service import (
    ProjectNotFoundError,
    SimulationResult,
    SnapshotNotFoundError,
    TerminalSnapshotError,
    run_simulation,
)

__all__ = [
    "ProjectNotFoundError",
    "SnapshotNotFoundError",
    "TerminalSnapshotError",
    "NoNonTerminalSnapshotError",
    "ProjectLookupResult",
    "lookup_project",
    "latest_snapshot_month",
    "get_risk_answer",
    "get_portfolio_answer",
    "search_documents",
    "run_whatif",
]


class NoNonTerminalSnapshotError(ValueError):
    pass


@dataclass(frozen=True)
class ProjectLookupResult:
    project: Project
    current_status: str
    snapshot_count: int
    has_terminal_snapshot: bool


def latest_snapshot_month(db: Session, project_id: str, *, non_terminal_only: bool = False) -> str | None:
    """Same latest-snapshot lookup pattern app.routers.projects.get_project
    already uses -- reused here, not reimplemented, just parameterized with
    an optional non-terminal-only filter (needed so what-if queries default
    to a snapshot run_simulation will actually accept)."""
    stmt = select(ProjectSnapshot.reporting_month).where(ProjectSnapshot.project_id == project_id)
    if non_terminal_only:
        stmt = stmt.where(ProjectSnapshot.is_terminal_snapshot.is_(False))
    stmt = stmt.order_by(ProjectSnapshot.reporting_month.desc()).limit(1)
    return db.execute(stmt).scalar_one_or_none()


def lookup_project(db: Session, project_id: str) -> ProjectLookupResult:
    project = db.get(Project, project_id)
    if project is None:
        raise ProjectNotFoundError(f"Project '{project_id}' not found.")

    snapshots = db.execute(
        select(ProjectSnapshot.project_status, ProjectSnapshot.is_terminal_snapshot)
        .where(ProjectSnapshot.project_id == project_id)
        .order_by(ProjectSnapshot.reporting_month.desc())
    ).all()
    current_status = snapshots[0].project_status if snapshots else "Unknown"
    has_terminal = any(s.is_terminal_snapshot for s in snapshots)
    return ProjectLookupResult(
        project=project, current_status=current_status, snapshot_count=len(snapshots), has_terminal_snapshot=has_terminal
    )


def get_risk_answer(db: Session, project_id: str, reporting_month: str | None) -> RiskSummaryResult:
    """Defaults to the project's own latest snapshot (terminal or not --
    run_risk_summary already handles both) when no month is given."""
    month = reporting_month or latest_snapshot_month(db, project_id)
    if month is None:
        raise SnapshotNotFoundError(f"Project '{project_id}' has no recorded snapshots yet.")
    return run_risk_summary(db, project_id, month)


def get_portfolio_answer(db: Session, *, dimension: str | None, risk_level: str | None):
    """Routes to the one Phase 14 portfolio_service call that matches the
    parsed query shape -- never live-scores, always reads the existing
    batch-scored cache like every other portfolio_service caller."""
    if dimension is not None:
        return ("segments", portfolio_service.get_segments(db, dimension))
    if risk_level is not None:
        return ("risk_projects", portfolio_service.get_risk_projects(db, risk_level=risk_level, limit=10))
    return ("overview", portfolio_service.get_portfolio_overview(db))


def search_documents(query: str, top_k: int = 5) -> tuple[RetrievalResponse, str]:
    service = get_retrieval_service()
    response = service.retrieve(query, top_k=top_k)
    return response, build_extractive_answer(response)


def run_whatif(db: Session, project_id: str, whatif: WhatIfIntent, reporting_month: str | None) -> SimulationResult:
    month = reporting_month or latest_snapshot_month(db, project_id, non_terminal_only=True)
    if month is None:
        raise NoNonTerminalSnapshotError(
            f"Project '{project_id}' has no non-terminal snapshot to simulate from (either no snapshots yet, "
            "or the project is already completed)."
        )
    baseline_row = build_predictor_row(db, project_id, month)
    baseline_value = float(baseline_row.iloc[0][whatif.field])
    simulated_value = whatif.apply(baseline_value)
    return run_simulation(db, project_id, month, {whatif.field: simulated_value})
