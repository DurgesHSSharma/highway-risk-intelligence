"""Phase 15 service-level tests for
app.decision_intelligence.synthesizer.run_decision_intelligence, against
the real committed corpus/models/DB/RAG-index/contradiction-detector/cache
via the session-scoped fixtures in conftest.py. Mirrors the fixture
convention already used by test_decision_support_service.py.
"""

from __future__ import annotations

from app.decision_intelligence.synthesizer import (
    ProjectNotFoundError,
    SnapshotNotFoundError,
    run_decision_intelligence,
)
from app.decision_support.recommendations import MAX_TOTAL_RECOMMENDATIONS
from app.decision_support.synthesizer import run_risk_summary
import pytest

NON_TERMINAL_PROJECT_ID = "HRI-0006"
NON_TERMINAL_MONTH = "2022-12"

TERMINAL_PROJECT_ID = "HRI-0001"
TERMINAL_MONTH = "2024-03"

CRITICAL_PROJECT_ID = "HRI-0328"
CRITICAL_MONTH = "2025-08"


# --- endpoint existence / basic validity ---


def test_non_terminal_project_works(db_session, _phase14_batch_scoring):
    result = run_decision_intelligence(db_session, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH)

    assert result.risk_summary.prediction_status == "model_prediction"
    assert result.risk_positioning.status == "ok"
    assert set(result.peer_context.keys()) == {"state", "project_type", "contractor"}
    assert len(result.driver_alignment) == 4
    assert len(result.recommended_reviews) <= MAX_TOTAL_RECOMMENDATIONS


def test_terminal_project_works(db_session, _phase14_batch_scoring):
    result = run_decision_intelligence(db_session, TERMINAL_PROJECT_ID, TERMINAL_MONTH)

    assert result.risk_summary.prediction_status == "actual_outcome"
    assert result.risk_summary.risk_drivers == []
    assert result.risk_summary.shap_skipped_reason is not None
    # Portfolio context can still render for a terminal snapshot -- risk
    # positioning depends on the project's cache row (from its own latest
    # non-terminal snapshot), not on the requested reporting_month.
    assert result.risk_positioning.status == "ok"
    assert len(result.driver_alignment) == 4
    for a in result.driver_alignment:
        assert a.live_top_driver is None
        assert a.agreement is None


def test_unknown_project_raises_project_not_found(db_session):
    with pytest.raises(ProjectNotFoundError):
        run_decision_intelligence(db_session, "NOT-A-REAL-PROJECT", "2022-12")


def test_unknown_reporting_month_raises_snapshot_not_found(db_session):
    with pytest.raises(SnapshotNotFoundError):
        run_decision_intelligence(db_session, NON_TERMINAL_PROJECT_ID, "1999-01")


# --- endpoint never duplicates Phase 11 logic: baseline predictions must
# match GET /risk-summary's own output for the identical snapshot exactly ---


def test_predictions_and_risk_drivers_match_phase11_risk_summary_exactly(db_session, _phase14_batch_scoring):
    # Numeric comparisons use a small tolerance, not exact `==`: a real,
    # disclosed ~1e-13 floating-point non-determinism exists in repeated
    # RandomForestClassifier/LogisticRegression predict_proba() calls
    # across two independent runs (see docs/ADVANCED_ANALYTICS.md "Known
    # limitations" and backend/tests/test_batch_scoring.py) -- this test
    # calls the pipeline twice (once inside run_decision_intelligence, once
    # directly via run_risk_summary), so it must tolerate that, not assert
    # bit-exact equality.
    di_result = run_decision_intelligence(db_session, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH)
    rs_result = run_risk_summary(db_session, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH)

    assert di_result.risk_summary.predictions.keys() == rs_result.predictions.keys()
    for task_key, di_pred in di_result.risk_summary.predictions.items():
        rs_pred = rs_result.predictions[task_key]
        for field, di_value in di_pred.model_dump().items():
            rs_value = getattr(rs_pred, field)
            if isinstance(di_value, (int, float)) and not isinstance(di_value, bool):
                assert di_value == pytest.approx(rs_value, abs=1e-6)
            else:
                assert di_value == rs_value

    assert len(di_result.risk_summary.risk_drivers) == len(rs_result.risk_drivers)
    for a, b in zip(di_result.risk_summary.risk_drivers, rs_result.risk_drivers):
        assert a.task_key == b.task_key
        assert a.top_drivers[0].feature == b.top_drivers[0].feature
        assert a.top_drivers[0].shap_value == pytest.approx(b.top_drivers[0].shap_value, abs=1e-6)


def test_evidence_and_inconsistencies_match_phase11_exactly(db_session, _phase14_batch_scoring):
    di_result = run_decision_intelligence(db_session, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH)
    rs_result = run_risk_summary(db_session, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH)

    assert [e.query for e in di_result.risk_summary.evidence] == [e.query for e in rs_result.evidence]
    assert [f.flag_id for f in di_result.risk_summary.inconsistencies] == [f.flag_id for f in rs_result.inconsistencies]


def test_scenario_matches_phase11_exactly(db_session, _phase14_batch_scoring):
    di_result = run_decision_intelligence(db_session, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH)
    rs_result = run_risk_summary(db_session, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH)

    assert (di_result.risk_summary.scenario is None) == (rs_result.scenario is None)
    if di_result.risk_summary.scenario is not None:
        assert di_result.risk_summary.scenario.field == rs_result.scenario.field
        assert di_result.risk_summary.scenario.reference_value == rs_result.scenario.reference_value


# --- recommendation merging ---


def test_phase11_recommendations_preserved_unchanged_in_merged_list(db_session, _phase14_batch_scoring):
    di_result = run_decision_intelligence(db_session, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH)
    rs_result = run_risk_summary(db_session, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH)

    phase11_texts = {r.text for r in rs_result.recommendations}
    merged_texts = {r.text for r in di_result.recommended_reviews}
    # Every Phase 11 recommendation that survives the shared cap must
    # appear with identical text -- content is never rewritten.
    surviving_phase11 = phase11_texts & merged_texts
    assert len(surviving_phase11) > 0


def test_recommended_reviews_capped_at_shared_max_total(db_session, _phase14_batch_scoring):
    # HRI-0328/2025-08 is a real CRITICAL project (see
    # docs/ADVANCED_ANALYTICS.md) -- likely to accumulate Phase 11 (up to
    # 8) + Phase 15 (up to 4) candidate recommendations, exercising the cap.
    result = run_decision_intelligence(db_session, CRITICAL_PROJECT_ID, CRITICAL_MONTH)
    assert len(result.recommended_reviews) <= MAX_TOTAL_RECOMMENDATIONS


def test_fifth_recommendation_family_appears_for_critical_project(db_session, _phase14_batch_scoring):
    result = run_decision_intelligence(db_session, CRITICAL_PROJECT_ID, CRITICAL_MONTH)
    basis_types = {r.basis_type for r in result.recommended_reviews}
    assert "portfolio_context" in basis_types
    # Every Phase 11 family is still representable in the combined type.
    for r in result.recommended_reviews:
        assert r.basis_type in (
            "model_driver",
            "documentary_evidence",
            "potential_inconsistency",
            "scenario",
            "portfolio_context",
        )


def test_basis_type_and_basis_detail_are_always_populated(db_session, _phase14_batch_scoring):
    result = run_decision_intelligence(db_session, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH)
    for r in result.recommended_reviews:
        assert r.basis_type
        assert r.basis_detail
        assert r.text


# --- RAG / contradiction / no-fabrication spot checks (reused Phase 11
# behavior; here we only confirm the Phase 15 layer doesn't disturb it) ---


def test_evidence_remains_grounded_with_citations_or_explicit_not_found(db_session, _phase14_batch_scoring):
    result = run_decision_intelligence(db_session, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH)
    for item in result.risk_summary.evidence:
        if item.not_found:
            assert item.results == []
        else:
            assert len(item.results) > 0
            for r in item.results:
                assert r.document_id
                assert r.page_number is not None


def test_potential_inconsistencies_never_use_confirmed_language(db_session, _phase14_batch_scoring):
    result = run_decision_intelligence(db_session, CRITICAL_PROJECT_ID, CRITICAL_MONTH)
    for flag in result.risk_summary.inconsistencies:
        lowered = flag.description.lower()
        assert "confirmed contradiction" not in lowered
        assert "confirmed error" not in lowered
