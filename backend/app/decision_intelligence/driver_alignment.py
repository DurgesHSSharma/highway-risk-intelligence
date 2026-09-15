"""Phase 15: compares Phase 11's LIVE per-instance top SHAP driver (this
specific snapshot, computed at request time against the exact model Phase
6 serves -- app.decision_support.shap_explainer) against Phase 14's
portfolio-wide top SHAP driver (Phase 5's saved static global artifact,
reused verbatim -- app.analytics.drivers) for each of the four supported
tasks.

Reuses `app.decision_support.shap_explainer.driver_identity` /
`clean_feature_name` directly -- NEVER a second feature-identity
implementation. Both `DriverFeature` (live) and `PortfolioDriver`
(portfolio) already carry a cleaned display name (`feature`) and a raw
ColumnTransformer-prefixed name (`raw_feature`), so `driver_identity`
applies uniformly to either side: a categorical one-hot level like
`state_Karnataka` reduces to the raw column identity `state`, so two
DIFFERENT one-hot levels of the same categorical column (e.g. this
project's live top driver is `state_Karnataka` while the portfolio-wide
top driver is `state_Assam`) still count as `agreement=True` at the
identity level -- this is a direct, intended consequence of reusing
`driver_identity` as-is, not a special case invented here.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.analytics.drivers import TaskPortfolioDrivers
from app.decision_support.shap_explainer import TaskRiskDrivers, driver_identity

TASK_ORDER = ["significant_delay", "final_delay_days", "cost_overrun", "final_cost_overrun_pct"]

NOT_COMPARABLE_NOTE = "Not a meaningful comparison -- different model family."


@dataclass(frozen=True)
class TaskDriverAlignment:
    task_key: str
    matches_serving_model: bool
    live_top_driver: str | None  # cleaned display name, e.g. "progress_efficiency" or "state_Karnataka"
    live_top_driver_identity: str | None  # raw predictor-column identity used for `agreement`
    portfolio_top_driver: str | None
    portfolio_top_driver_identity: str | None
    agreement: bool | None
    comparable: bool


def compute_driver_alignment(
    live_risk_drivers: list[TaskRiskDrivers],
    portfolio_task_drivers: list[TaskPortfolioDrivers],
) -> list[TaskDriverAlignment]:
    """`live_risk_drivers` is `[]` for a terminal snapshot (Phase 11 skips
    SHAP entirely -- see app.decision_support.synthesizer) -- every task's
    `live_top_driver*` then comes back `None` and `agreement=None`, exactly
    matching the "either side unavailable -> agreement = null" rule. Always
    returns exactly one entry per `TASK_ORDER` task, regardless of which
    side is available, so the frontend never has to guess a missing task's
    alignment status."""
    live_by_task = {d.task_key: d for d in live_risk_drivers}
    portfolio_by_task = {d.task_key: d for d in portfolio_task_drivers}

    out: list[TaskDriverAlignment] = []
    for task_key in TASK_ORDER:
        live = live_by_task.get(task_key)
        portfolio = portfolio_by_task.get(task_key)

        live_top: str | None = None
        live_identity: str | None = None
        if live is not None and live.top_drivers:
            top = live.top_drivers[0]
            live_top = top.feature
            live_identity = driver_identity(top.feature, top.raw_feature)

        portfolio_top: str | None = None
        portfolio_identity: str | None = None
        if portfolio is not None and portfolio.drivers:
            ptop = portfolio.drivers[0]
            portfolio_top = ptop.feature
            portfolio_identity = driver_identity(ptop.feature, ptop.raw_feature)

        # Copied exactly from Phase 14, never recomputed (master-prompt
        # section 14: "Do NOT recompute matches_serving_model.").
        matches_serving_model = bool(portfolio.matches_serving_model) if portfolio is not None else False

        if live_identity is not None and portfolio_identity is not None:
            agreement = live_identity == portfolio_identity
        else:
            agreement = None

        # matches_serving_model == false -> comparable = false (the two
        # cost tasks: Phase 14's saved global SHAP explains XGBoost, but
        # the Phase 4 linear baselines actually serve those predictions --
        # comparing "top driver agreement" across different model families
        # would not be a meaningful comparison, see
        # docs/DECISION_INTELLIGENCE.md).
        comparable = matches_serving_model

        out.append(
            TaskDriverAlignment(
                task_key=task_key,
                matches_serving_model=matches_serving_model,
                live_top_driver=live_top,
                live_top_driver_identity=live_identity,
                portfolio_top_driver=portfolio_top,
                portfolio_top_driver_identity=portfolio_identity,
                agreement=agreement,
                comparable=comparable,
            )
        )

    return out
