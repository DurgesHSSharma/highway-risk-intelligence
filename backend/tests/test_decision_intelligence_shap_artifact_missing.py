"""Phase 15 bug-fix regression test: if Phase 14's saved global SHAP
artifact (docs/artifacts/shap_local_examples.json) is missing/unavailable,
`app.analytics.drivers.portfolio_drivers()` raises `ShapArtifactMissingError`
-- the Decision Intelligence endpoint must degrade gracefully (portfolio-side
driver alignment becomes unavailable) rather than returning HTTP 500. See
app.decision_intelligence.synthesizer.run_decision_intelligence's explicit
try/except around `portfolio_drivers()`.

Genuinely exercises the real, unmodified Phase 14 failure path: monkeypatches
only the module-level `SHAP_ARTIFACT_PATH` constant (data, not behavior) and
clears `_load_artifact`'s lru_cache so `_load_artifact()`'s own
`if not SHAP_ARTIFACT_PATH.exists(): raise ShapArtifactMissingError(...)`
branch actually runs -- never a mocked-away exception, and
`app.analytics.drivers.portfolio_drivers()` itself is never edited. The
cache is restored (and the real artifact re-loaded) in a `finally` block so
no other test in the session is left with a poisoned cache.
"""

from __future__ import annotations

import pytest

import app.analytics.drivers as drivers_module
from app.analytics.drivers import ShapArtifactMissingError
from app.decision_intelligence.synthesizer import run_decision_intelligence

NON_TERMINAL_PROJECT_ID = "HRI-0006"
NON_TERMINAL_MONTH = "2022-12"


@pytest.fixture()
def missing_shap_artifact(tmp_path):
    """Points app.analytics.drivers.SHAP_ARTIFACT_PATH at a nonexistent file
    for the duration of the test, forcing the real _load_artifact() code
    path to genuinely raise ShapArtifactMissingError. Restores the original
    path and re-warms the lru_cache with the real artifact afterward."""
    original_path = drivers_module.SHAP_ARTIFACT_PATH
    fake_path = tmp_path / "shap_local_examples_does_not_exist.json"
    drivers_module.SHAP_ARTIFACT_PATH = fake_path
    drivers_module._load_artifact.cache_clear()
    try:
        yield fake_path
    finally:
        drivers_module.SHAP_ARTIFACT_PATH = original_path
        drivers_module._load_artifact.cache_clear()
        drivers_module.portfolio_drivers()  # re-warm with the real artifact


# --- 1. The dependency genuinely raises ---


def test_portfolio_drivers_genuinely_raises_when_artifact_missing(missing_shap_artifact):
    with pytest.raises(ShapArtifactMissingError):
        drivers_module.portfolio_drivers()


# --- 2-5. Decision Intelligence degrades gracefully, via the real service path ---


def test_decision_intelligence_service_does_not_raise_when_shap_artifact_missing(db_session, _phase14_batch_scoring, missing_shap_artifact):
    # 2. Must not raise (== would 500 at the HTTP layer).
    result = run_decision_intelligence(db_session, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH)

    # 3. Portfolio-side driver information becomes unavailable, using the
    # existing Phase 15 response semantics (None/False/None -- the same
    # degradation already used for a terminal snapshot's LIVE side).
    assert len(result.driver_alignment) == 4
    for a in result.driver_alignment:
        assert a.portfolio_top_driver is None
        assert a.portfolio_top_driver_identity is None
        assert a.matches_serving_model is False
        assert a.comparable is False
        assert a.agreement is None

    # 4. Other valid response sections remain available.
    assert result.risk_positioning.status == "ok"
    assert set(result.peer_context.keys()) == {"state", "project_type", "contractor"}
    assert result.risk_summary.prediction_status == "model_prediction"

    # 5. Phase 11's existing live drivers remain intact.
    assert len(result.risk_summary.risk_drivers) == 4
    for a in result.driver_alignment:
        assert a.live_top_driver is not None


def test_decision_intelligence_endpoint_returns_200_when_shap_artifact_missing(client, _phase14_batch_scoring, missing_shap_artifact):
    resp = client.get(
        f"/projects/{NON_TERMINAL_PROJECT_ID}/decision-intelligence",
        params={"reporting_month": NON_TERMINAL_MONTH},
    )
    assert resp.status_code == 200
    body = resp.json()

    assert body["risk_positioning"]["status"] == "ok"
    assert len(body["risk_drivers"]) == 4
    for a in body["driver_alignment"]:
        assert a["portfolio_top_driver"] is None
        assert a["matches_serving_model"] is False
        assert a["comparable"] is False
        assert a["agreement"] is None
        assert a["live_top_driver"] is not None


def test_driver_divergence_recommendation_never_fires_when_portfolio_side_unavailable(db_session, _phase14_batch_scoring, missing_shap_artifact):
    """comparable=False for every task when the artifact is missing, so the
    driver-divergence sub-rule of the 5th recommendation family must
    structurally produce zero items -- never a fabricated comparison against
    missing data."""
    result = run_decision_intelligence(db_session, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH)
    basis_details = [r.basis_detail for r in result.recommended_reviews if r.basis_type == "portfolio_context"]
    assert all("Driver divergence" not in d for d in basis_details)
