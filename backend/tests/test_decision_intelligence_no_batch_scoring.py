"""Phase 15 proof (master-prompt section 29): a normal Decision
Intelligence request NEVER triggers Phase 14 batch scoring
(`run_batch_scoring`) or a per-project live-inference call outside Phase
11's own single `predict_all_tasks` invocation for the requested snapshot.

Monkeypatches `app.analytics.batch_scoring.run_batch_scoring` to raise if
called, then exercises the real endpoint through the real `client` fixture
(mirrors the exact pattern already used by
backend/tests/test_cache_behavior.py for the Phase 14 /analytics/*
endpoints).
"""

from __future__ import annotations

NON_TERMINAL_PROJECT_ID = "HRI-0006"
NON_TERMINAL_MONTH = "2022-12"

TERMINAL_PROJECT_ID = "HRI-0001"
TERMINAL_MONTH = "2024-03"


def test_decision_intelligence_never_calls_run_batch_scoring(client, _phase14_batch_scoring, monkeypatch):
    def _boom(*args, **kwargs):
        raise AssertionError("run_batch_scoring was called during a Decision Intelligence request!")

    monkeypatch.setattr("app.analytics.batch_scoring.run_batch_scoring", _boom)

    resp = client.get(
        f"/projects/{NON_TERMINAL_PROJECT_ID}/decision-intelligence",
        params={"reporting_month": NON_TERMINAL_MONTH},
    )
    assert resp.status_code == 200
    assert resp.json()["risk_positioning"]["status"] == "ok"


def test_decision_intelligence_never_calls_run_batch_scoring_for_terminal_snapshot(client, _phase14_batch_scoring, monkeypatch):
    def _boom(*args, **kwargs):
        raise AssertionError("run_batch_scoring was called during a Decision Intelligence request!")

    monkeypatch.setattr("app.analytics.batch_scoring.run_batch_scoring", _boom)

    resp = client.get(
        f"/projects/{TERMINAL_PROJECT_ID}/decision-intelligence",
        params={"reporting_month": TERMINAL_MONTH},
    )
    assert resp.status_code == 200


def test_decision_intelligence_calls_predict_all_tasks_at_most_once_per_task(client, _phase14_batch_scoring, monkeypatch):
    """Proves the endpoint reuses Phase 11's single run_risk_summary call
    (which itself calls predict_all_tasks exactly once for the requested
    snapshot) rather than re-predicting per portfolio-context section --
    counts real invocations rather than merely asserting "not called"."""
    import app.ml.predict as predict_module

    call_count = {"n": 0}
    original = predict_module.predict_all_tasks

    def _counting_wrapper(X):
        call_count["n"] += 1
        return original(X)

    monkeypatch.setattr(predict_module, "predict_all_tasks", _counting_wrapper)
    # app.decision_support.synthesizer imported predict_all_tasks directly
    # into its own module namespace, so that reference must be patched too.
    monkeypatch.setattr("app.decision_support.synthesizer.predict_all_tasks", _counting_wrapper)

    resp = client.get(
        f"/projects/{NON_TERMINAL_PROJECT_ID}/decision-intelligence",
        params={"reporting_month": NON_TERMINAL_MONTH},
    )
    assert resp.status_code == 200
    assert call_count["n"] == 1


def test_cache_unavailable_state_never_falls_back_to_live_batch_scoring():
    """On a completely empty, isolated database (never the shared test
    DB), the endpoint must report an explicit cache_unavailable state --
    never silently run batch scoring or crash."""
    from sqlalchemy.orm import Session as OrmSession

    from app.db.base import create_all, make_engine
    from app.decision_intelligence.portfolio_context import get_risk_positioning

    engine = make_engine("sqlite:///:memory:")
    create_all(bind=engine)
    session = OrmSession(bind=engine)
    try:
        result = get_risk_positioning(session, "HRI-0006")
        assert result.status == "cache_unavailable"
    finally:
        session.close()
