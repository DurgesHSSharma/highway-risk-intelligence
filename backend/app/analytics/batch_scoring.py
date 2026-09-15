"""Phase 14 batch-scoring core: computes the Phase 6
`TASK_MODEL_REGISTRY` predictions for every eligible project's latest
non-terminal snapshot, ONCE, and writes them to the
`portfolio_prediction_cache` table (see app/db/models.py).

This module is the only place that runs live ML inference for portfolio
analytics. `/analytics/*` endpoints read the resulting cache table -- they
never call `predict_all_tasks` per request (see
app/analytics/portfolio_service.py and docs/ADVANCED_ANALYTICS.md).

"Eligible" project == has at least one snapshot with
is_terminal_snapshot=False. In this synthetic corpus every one of the 400
projects is simulated through to completion, so every project's absolute
latest snapshot is terminal (Completed) -- there is no "still in progress"
project by the naive "latest snapshot" definition. "Current predicted
risk" is therefore deliberately defined as: the prediction from each
project's own latest PRE-COMPLETION (non-terminal) reporting month. This
mirrors exactly how the existing Phase 10/11 endpoints already treat an
arbitrary non-terminal `reporting_month` as a valid "current" snapshot to
score -- batch scoring simply automates picking that month per project
instead of requiring a caller-supplied one. Disclosed explicitly in
docs/ADVANCED_ANALYTICS.md, not hidden.

Reuses, never reimplements:
- app.ml.features.build_predictor_row (exact same 45-column feature
  construction as GET /predict and POST /simulate)
- app.ml.predict.predict_all_tasks (exact same model invocation)
- app.ml.registry.TASK_MODEL_REGISTRY (model identity/provenance strings)

No model is retrained, refit, or reloaded here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import delete, func, insert, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.db.base import create_all, engine as default_engine
from app.db.models import Project, ProjectSnapshot, PortfolioPredictionCache
from app.ml.features import FeatureConstructionError, build_predictor_row
from app.ml.predict import predict_all_tasks
from app.ml.registry import TASK_MODEL_REGISTRY


@dataclass(frozen=True)
class ScoringFailure:
    project_id: str
    reporting_month: str | None
    reason: str


@dataclass(frozen=True)
class BatchScoringSummary:
    computed_at: datetime
    total_projects: int
    eligible_projects: int
    scored_projects: int
    failures: list[ScoringFailure] = field(default_factory=list)


def _latest_eligible_snapshots(db: Session) -> list[tuple[str, str]]:
    """For every project, its latest snapshot with is_terminal_snapshot is
    False -- i.e. the last reporting_month BEFORE that project reached its
    terminal (Completed) row. A project with zero non-terminal snapshots
    (not expected in the current dataset, but not assumed away) is simply
    absent from this list -- never fabricated."""
    latest = (
        select(
            ProjectSnapshot.project_id.label("project_id"),
            func.max(ProjectSnapshot.reporting_month).label("latest_month"),
        )
        .where(ProjectSnapshot.is_terminal_snapshot.is_(False))
        .group_by(ProjectSnapshot.project_id)
        .subquery()
    )
    rows = db.execute(select(latest.c.project_id, latest.c.latest_month)).all()
    return [(r.project_id, r.latest_month) for r in rows]


def run_batch_scoring(bind: Engine | None = None) -> BatchScoringSummary:
    """Deterministic clear-and-reload batch scoring, mirroring
    app/db/loader.py::load_database's own clear-and-reload convention.
    Re-running this against unchanged data/models produces the same
    predictions (the same eligible snapshot per project, scored through the
    same deterministic pipelines) -- only `computed_at` changes between
    runs."""
    bind = bind or default_engine
    create_all(bind=bind)

    session = Session(bind=bind)
    try:
        total_projects = session.execute(select(func.count()).select_from(Project)).scalar_one()
        eligible = _latest_eligible_snapshots(session)
        computed_at = datetime.now(timezone.utc).replace(tzinfo=None)

        rows: list[dict] = []
        failures: list[ScoringFailure] = []

        for project_id, reporting_month in eligible:
            try:
                X = build_predictor_row(session, project_id, reporting_month)
                predictions = predict_all_tasks(X)
            except FeatureConstructionError as exc:
                failures.append(ScoringFailure(project_id, reporting_month, str(exc)))
                continue
            except (LookupError, ValueError, KeyError) as exc:
                failures.append(ScoringFailure(project_id, reporting_month, str(exc)))
                continue

            sig = predictions["significant_delay"]
            delay_days = predictions["final_delay_days"]
            cost = predictions["cost_overrun"]
            cost_pct = predictions["final_cost_overrun_pct"]

            rows.append(
                {
                    "project_id": project_id,
                    "reporting_month": reporting_month,
                    "computed_at": computed_at,
                    "significant_delay_model": sig.model_used or TASK_MODEL_REGISTRY["significant_delay"].model_name,
                    "significant_delay_predicted_class": sig.predicted_class,
                    "significant_delay_probability": sig.probability_of_significant_delay,
                    "final_delay_days_model": delay_days.model_used or TASK_MODEL_REGISTRY["final_delay_days"].model_name,
                    "final_delay_days_predicted": delay_days.predicted_final_delay_days,
                    "cost_overrun_model": cost.model_used or TASK_MODEL_REGISTRY["cost_overrun"].model_name,
                    "cost_overrun_predicted_class": cost.predicted_class,
                    "cost_overrun_probability": cost.probability_of_cost_overrun,
                    "final_cost_overrun_pct_model": cost_pct.model_used
                    or TASK_MODEL_REGISTRY["final_cost_overrun_pct"].model_name,
                    "final_cost_overrun_pct_predicted": cost_pct.predicted_final_cost_overrun_pct,
                }
            )

        session.execute(delete(PortfolioPredictionCache))
        session.flush()
        if rows:
            session.execute(insert(PortfolioPredictionCache), rows)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    return BatchScoringSummary(
        computed_at=computed_at,
        total_projects=total_projects,
        eligible_projects=len(eligible),
        scored_projects=len(rows),
        failures=failures,
    )


def get_cache_metadata(db: Session) -> dict | None:
    """Returns {"computed_at": ..., "cached_projects": N} or None if the
    cache has never been populated (or was cleared and never refilled) --
    callers must treat None as "run scripts/batch_score_portfolio.py",
    never silently fall back to live per-project inference."""
    row = db.execute(
        select(func.max(PortfolioPredictionCache.computed_at), func.count())
        .select_from(PortfolioPredictionCache)
    ).one()
    computed_at, count = row
    if computed_at is None or count == 0:
        return None
    return {"computed_at": computed_at, "cached_projects": count}
