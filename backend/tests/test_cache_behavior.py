"""Phase 14 cache-behavior tests (brief sections 10/11/35):

1. Behaviorally proves `/analytics/*` endpoints read the batch cache and
   never call `app.ml.predict.predict_all_tasks` per request -- achieved by
   monkeypatching that exact function to raise, then hitting the real
   endpoints through the real `client` fixture. This is NOT a test that
   mocks the endpoint itself; it proves the underlying inference function
   is never invoked while still exercising the real HTTP route.
2. Verifies the documented "cache not yet generated" behavior on a
   completely empty, isolated database (never the shared test DB) -- every
   affected function must return a predictable `cache_unavailable` /
   empty-list response, never crash, and never silently fall back to live
   inference.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session as OrmSession

from app.analytics import portfolio_service
from app.db.base import create_all, make_engine


def test_endpoints_never_call_predict_all_tasks_when_cache_is_populated(client, _phase14_batch_scoring, monkeypatch):
    def _boom(*args, **kwargs):
        raise AssertionError("predict_all_tasks was called during an analytics request -- cache was bypassed!")

    monkeypatch.setattr("app.ml.predict.predict_all_tasks", _boom)

    resp1 = client.get("/analytics/portfolio")
    assert resp1.status_code == 200
    assert resp1.json()["predicted"]["status"] == "ok"

    resp2 = client.get("/analytics/risk-projects", params={"limit": 20})
    assert resp2.status_code == 200
    assert resp2.json()["cache_status"] == "ok"

    resp3 = client.get("/analytics/segments", params={"dimension": "state"})
    assert resp3.status_code == 200

    resp4 = client.get("/analytics/trends")
    assert resp4.status_code == 200


@pytest.fixture
def empty_db_session():
    """A fresh, isolated in-memory SQLite database with the schema created
    but zero projects/snapshots/cache rows -- never the shared test DB."""
    engine = make_engine("sqlite:///:memory:")
    create_all(bind=engine)
    session = OrmSession(bind=engine)
    try:
        yield session
    finally:
        session.close()


def test_portfolio_overview_reports_cache_unavailable_on_empty_dataset(empty_db_session):
    data = portfolio_service.get_portfolio_overview(empty_db_session)
    assert data.total_projects == 0
    assert data.historical.completed_project_count == 0
    assert data.predicted.status == "cache_unavailable"
    assert data.predicted.message is not None
    assert data.risk_distribution == []
    assert data.top_risks == []


def test_risk_projects_reports_cache_unavailable_on_empty_dataset(empty_db_session):
    data = portfolio_service.get_risk_projects(empty_db_session)
    assert data.cache_status == "cache_unavailable"
    assert data.total == 0
    assert data.items == []


def test_segments_handle_empty_dataset_without_crashing(empty_db_session):
    data = portfolio_service.get_segments(empty_db_session, "state")
    assert data.entries == []


def test_trends_handle_empty_dataset_without_crashing(empty_db_session):
    data = portfolio_service.get_trends(empty_db_session)
    assert data.historical == []
    assert data.predicted_status == "cache_unavailable"
    assert data.predicted == []


def test_invalid_segment_dimension_raises_value_error(empty_db_session):
    with pytest.raises(portfolio_service.InvalidDimensionError):
        portfolio_service.get_segments(empty_db_session, "not_a_real_dimension")
