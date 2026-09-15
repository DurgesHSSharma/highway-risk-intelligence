"""Phase 14 batch-scoring tests: eligibility selection, cache population,
cache metadata, and determinism. Uses the real committed dataset/models via
the shared `_phase14_batch_scoring` session fixture (backend/tests/conftest.py)
-- never a fabricated fixture dataset.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.analytics.batch_scoring import (
    _latest_eligible_snapshots,
    get_cache_metadata,
    run_batch_scoring,
)
from app.db.base import SessionLocal
from app.db.models import PortfolioPredictionCache, ProjectSnapshot


def test_every_project_is_eligible_in_this_dataset(_phase14_batch_scoring):
    summary = _phase14_batch_scoring
    # Known, disclosed corpus property (see app/analytics/batch_scoring.py
    # module docstring): every one of the 400 synthetic projects is
    # simulated through to completion, so every project also has at least
    # one non-terminal snapshot before that -- all 400 are eligible.
    assert summary.total_projects == 400
    assert summary.eligible_projects == 400
    assert summary.scored_projects == 400
    assert summary.failures == []


def test_eligible_snapshot_is_the_latest_non_terminal_one_not_the_terminal_one():
    """For a real known project (HRI-0006), confirm the batch-scoring
    eligibility query picks the latest NON-terminal snapshot, which must be
    strictly earlier than that project's terminal (Completed) snapshot."""
    session = SessionLocal()
    try:
        eligible = dict(_latest_eligible_snapshots(session))
        assert "HRI-0006" in eligible
        eligible_month = eligible["HRI-0006"]

        terminal_month = session.execute(
            select(ProjectSnapshot.reporting_month)
            .where(ProjectSnapshot.project_id == "HRI-0006")
            .where(ProjectSnapshot.is_terminal_snapshot.is_(True))
        ).scalar_one()

        assert eligible_month < terminal_month

        is_terminal = session.execute(
            select(ProjectSnapshot.is_terminal_snapshot)
            .where(ProjectSnapshot.project_id == "HRI-0006")
            .where(ProjectSnapshot.reporting_month == eligible_month)
        ).scalar_one()
        assert is_terminal is False
    finally:
        session.close()


def test_cache_rows_carry_full_prediction_and_provenance_metadata(_phase14_batch_scoring):
    session = SessionLocal()
    try:
        row = session.execute(
            select(PortfolioPredictionCache).where(PortfolioPredictionCache.project_id == "HRI-0006")
        ).scalar_one()
    finally:
        session.close()

    assert row.reporting_month is not None
    assert row.computed_at is not None
    assert row.significant_delay_model == "random_forest"
    assert row.significant_delay_predicted_class in (0, 1)
    assert 0.0 <= row.significant_delay_probability <= 1.0
    assert row.final_delay_days_model == "xgboost"
    assert isinstance(row.final_delay_days_predicted, float)
    assert row.cost_overrun_model == "logistic_regression_baseline"
    assert row.cost_overrun_predicted_class in (0, 1)
    assert 0.0 <= row.cost_overrun_probability <= 1.0
    assert row.final_cost_overrun_pct_model == "linear_regression_baseline"
    assert isinstance(row.final_cost_overrun_pct_predicted, float)


def test_cache_metadata_reports_computed_at_and_count(_phase14_batch_scoring):
    session = SessionLocal()
    try:
        meta = get_cache_metadata(session)
    finally:
        session.close()
    assert meta is not None
    assert meta["cached_projects"] == 400
    assert meta["computed_at"] is not None


def test_get_cache_metadata_returns_none_for_empty_cache():
    """Uses a throwaway in-memory database, never the shared test DB --
    proves the "no cache yet" path without disturbing other tests."""
    from app.db.base import create_all, make_engine

    engine = make_engine("sqlite:///:memory:")
    create_all(bind=engine)
    session = SessionLocal()
    session.close()
    from sqlalchemy.orm import Session as _Session

    isolated_session = _Session(bind=engine)
    try:
        assert get_cache_metadata(isolated_session) is None
    finally:
        isolated_session.close()


def test_rerunning_batch_scoring_is_deterministic_given_unchanged_data(_phase14_batch_scoring):
    """Re-running scoring twice against the unchanged dataset/models
    reproduces the same project selection, model identities, and predicted
    classes exactly, and the same predicted probabilities/values to within
    a tight numeric tolerance.

    Real finding from running this for real (not assumed): raw probability
    floats from RandomForestClassifier/LogisticRegression.predict_proba
    occasionally differ by ~1e-13 between runs (e.g. 0.9130553665995906 vs
    ...909) -- a known floating-point-summation-order artifact of
    scikit-learn's internal (possibly multi-threaded) tree/probability
    aggregation, not something app.analytics.batch_scoring introduces.
    Regression predictions (XGBoost, LinearRegression) were exactly
    identical across the two runs in this same check. Exact-equality was
    tried first and genuinely failed for this reason before this tolerance
    was added -- disclosed here and in docs/ADVANCED_ANALYTICS.md rather
    than silently loosened."""
    session = SessionLocal()
    try:
        before = {
            r.project_id: (
                r.reporting_month,
                r.significant_delay_predicted_class,
                r.significant_delay_probability,
                r.final_delay_days_predicted,
                r.cost_overrun_predicted_class,
                r.cost_overrun_probability,
                r.final_cost_overrun_pct_predicted,
            )
            for r in session.execute(select(PortfolioPredictionCache)).scalars().all()
        }
    finally:
        session.close()

    run_batch_scoring()

    session = SessionLocal()
    try:
        after = {
            r.project_id: (
                r.reporting_month,
                r.significant_delay_predicted_class,
                r.significant_delay_probability,
                r.final_delay_days_predicted,
                r.cost_overrun_predicted_class,
                r.cost_overrun_probability,
                r.final_cost_overrun_pct_predicted,
            )
            for r in session.execute(select(PortfolioPredictionCache)).scalars().all()
        }
    finally:
        session.close()

    assert set(before) == set(after)
    for project_id, before_row in before.items():
        after_row = after[project_id]
        # reporting_month, both predicted classes: exact match required.
        assert before_row[0] == after_row[0]
        assert before_row[1] == after_row[1]
        assert before_row[4] == after_row[4]
        # probabilities/regression outputs: tight numeric tolerance.
        for i in (2, 3, 5, 6):
            assert before_row[i] == pytest.approx(after_row[i], abs=1e-6), (
                f"{project_id} field index {i} differs beyond tolerance: {before_row[i]} vs {after_row[i]}"
            )
