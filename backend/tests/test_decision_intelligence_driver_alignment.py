"""Phase 15 tests for app.decision_intelligence.driver_alignment.

Uses real live SHAP + portfolio drivers for the "real data" cases, and a
synthetic fixture (constructed directly as dataclasses, never touching the
real corpus) to exercise the categorical-identity path per master-prompt
section 30 ("use synthetic fixture data only when necessary to exercise an
otherwise unreachable edge case such as categorical identity") -- the real
corpus's live top drivers for the two delay tasks are numeric
(`progress_efficiency` / `contractor_productivity_factor`), so the
categorical-reduction branch of `driver_identity` is not naturally
exercised by any single real request.
"""

from __future__ import annotations

from app.analytics.drivers import PortfolioDriver, TaskPortfolioDrivers, portfolio_drivers
from app.decision_intelligence.driver_alignment import TASK_ORDER, compute_driver_alignment
from app.decision_support.shap_explainer import DriverFeature, TaskRiskDrivers, explain_instance
from app.ml.features import build_predictor_row

NON_TERMINAL_PROJECT_ID = "HRI-0006"
NON_TERMINAL_MONTH = "2022-12"


# --- real-data cases ---


def test_alignment_covers_all_four_tasks_in_order(db_session):
    X = build_predictor_row(db_session, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH)
    live_drivers = [explain_instance(t, X) for t in TASK_ORDER]
    alignment = compute_driver_alignment(live_drivers, portfolio_drivers())

    assert [a.task_key for a in alignment] == TASK_ORDER


def test_alignment_matches_serving_model_copied_from_phase14_not_recomputed(db_session):
    X = build_predictor_row(db_session, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH)
    live_drivers = [explain_instance(t, X) for t in TASK_ORDER]
    portfolio = portfolio_drivers()
    alignment = compute_driver_alignment(live_drivers, portfolio)

    portfolio_by_task = {d.task_key: d for d in portfolio}
    for a in alignment:
        assert a.matches_serving_model == portfolio_by_task[a.task_key].matches_serving_model


def test_non_comparable_cost_tasks_have_comparable_false(db_session):
    X = build_predictor_row(db_session, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH)
    live_drivers = [explain_instance(t, X) for t in TASK_ORDER]
    alignment = compute_driver_alignment(live_drivers, portfolio_drivers())
    by_task = {a.task_key: a for a in alignment}

    # Real, disclosed Phase 14 characteristic: the saved global SHAP
    # artifact explains XGBoost for the two cost tasks, but the Phase 4
    # linear baselines actually serve them -- matches_serving_model=False,
    # so comparable must be False for both.
    assert by_task["cost_overrun"].matches_serving_model is False
    assert by_task["cost_overrun"].comparable is False
    assert by_task["final_cost_overrun_pct"].matches_serving_model is False
    assert by_task["final_cost_overrun_pct"].comparable is False


def test_comparable_delay_tasks_have_comparable_true(db_session):
    X = build_predictor_row(db_session, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH)
    live_drivers = [explain_instance(t, X) for t in TASK_ORDER]
    alignment = compute_driver_alignment(live_drivers, portfolio_drivers())
    by_task = {a.task_key: a for a in alignment}

    assert by_task["significant_delay"].matches_serving_model is True
    assert by_task["significant_delay"].comparable is True
    assert by_task["final_delay_days"].matches_serving_model is True
    assert by_task["final_delay_days"].comparable is True


def test_agreement_is_null_when_live_drivers_unavailable_terminal_case():
    """A terminal snapshot's live_risk_drivers is `[]` (Phase 11 skips SHAP
    entirely) -- every task must show live_top_driver=None and
    agreement=None, never a fabricated comparison."""
    alignment = compute_driver_alignment([], portfolio_drivers())
    assert len(alignment) == 4
    for a in alignment:
        assert a.live_top_driver is None
        assert a.live_top_driver_identity is None
        assert a.agreement is None
        # portfolio side is still populated -- only the live side is missing.
        assert a.portfolio_top_driver is not None


# --- synthetic categorical-identity fixture ---


def _fake_live_drivers(task_key: str, raw_feature: str, feature: str) -> TaskRiskDrivers:
    return TaskRiskDrivers(
        task_key=task_key,
        label="synthetic fixture",
        model_used="synthetic_model",
        explainer_type="TreeExplainer",
        shap_output_semantics="synthetic fixture -- not a real model output",
        top_drivers=[
            DriverFeature(
                rank=1,
                feature=feature,
                raw_feature=raw_feature,
                shap_value=0.5,
                direction="increases",
                explanation="synthetic fixture",
            )
        ],
    )


def _fake_portfolio_drivers(task_key: str, raw_feature: str, feature: str, matches: bool) -> TaskPortfolioDrivers:
    return TaskPortfolioDrivers(
        task_key=task_key,
        label="synthetic fixture",
        model_family_explained="synthetic_model" if matches else "some_other_model",
        matches_serving_model=matches,
        drivers=[PortfolioDriver(rank=1, feature=feature, raw_feature=raw_feature, mean_abs_shap=0.1)],
    )


def test_categorical_identity_reduction_same_column_different_level_agrees():
    """Live top driver is one one-hot level of `state`
    (`categorical__state_Karnataka`), portfolio top driver is a DIFFERENT
    one-hot level of the SAME raw column (`categorical__state_Assam`).
    `driver_identity` reduces both to the raw column identity 'state', so
    agreement must be True -- a direct, intended consequence of reusing
    driver_identity as-is (see module docstring), not something special
    -cased in this package."""
    live = [
        _fake_live_drivers("significant_delay", "categorical__state_Karnataka", "state_Karnataka"),
    ]
    portfolio = [
        _fake_portfolio_drivers("significant_delay", "categorical__state_Assam", "state_Assam", matches=True),
        _fake_portfolio_drivers("final_delay_days", "numeric__progress_efficiency", "progress_efficiency", matches=True),
        _fake_portfolio_drivers("cost_overrun", "numeric__project_age_ratio", "project_age_ratio", matches=False),
        _fake_portfolio_drivers(
            "final_cost_overrun_pct", "numeric__project_age_ratio", "project_age_ratio", matches=False
        ),
    ]
    alignment = compute_driver_alignment(live, portfolio)
    sig = next(a for a in alignment if a.task_key == "significant_delay")

    assert sig.live_top_driver == "state_Karnataka"
    assert sig.portfolio_top_driver == "state_Assam"
    assert sig.live_top_driver_identity == "state"
    assert sig.portfolio_top_driver_identity == "state"
    assert sig.agreement is True


def test_categorical_identity_reduction_different_column_disagrees():
    live = [
        _fake_live_drivers("significant_delay", "categorical__state_Karnataka", "state_Karnataka"),
    ]
    portfolio = [
        _fake_portfolio_drivers(
            "significant_delay", "categorical__project_type_Greenfield Highway", "project_type_Greenfield Highway", matches=True
        ),
    ]
    alignment = compute_driver_alignment(live, portfolio)
    sig = next(a for a in alignment if a.task_key == "significant_delay")

    assert sig.live_top_driver_identity == "state"
    assert sig.portfolio_top_driver_identity == "project_type"
    assert sig.agreement is False


def test_numeric_feature_never_reduced_to_a_same_named_categorical_column():
    """A numeric feature like `contractor_productivity_factor` must never
    be identity-reduced to the categorical `contractor` column just
    because its cleaned name shares a prefix -- driver_identity only
    reduces a feature carrying the 'categorical__' ColumnTransformer
    prefix (see app.decision_support.shap_explainer.driver_identity)."""
    live = [
        _fake_live_drivers(
            "final_delay_days", "numeric__contractor_productivity_factor", "contractor_productivity_factor"
        ),
    ]
    portfolio = [
        _fake_portfolio_drivers("final_delay_days", "categorical__contractor_Malwa Builders Pvt Ltd", "contractor_Malwa Builders Pvt Ltd", matches=True),
    ]
    alignment = compute_driver_alignment(live, portfolio)
    fd = next(a for a in alignment if a.task_key == "final_delay_days")

    assert fd.live_top_driver_identity == "contractor_productivity_factor"
    assert fd.portfolio_top_driver_identity == "contractor"
    assert fd.agreement is False
