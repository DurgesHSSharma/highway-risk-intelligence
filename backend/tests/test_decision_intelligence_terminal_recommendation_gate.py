"""Phase 15 bug-fix regression test: a terminal-snapshot REQUEST must
produce ZERO portfolio_context recommendations (master-prompt section 8),
even though `risk_positioning` itself is keyed off the project's own cached
LATEST NON-TERMINAL snapshot and can still be "ok"/HIGH/CRITICAL for a
terminal request. See
app.decision_intelligence.synthesizer.run_decision_intelligence's explicit
`if risk_summary_result.project.is_terminal_snapshot: phase15_recommendations = []`
gate, driven by Phase 11's own `ProjectInfo.is_terminal_snapshot` for the
ACTUAL REQUESTED snapshot -- never inferred from the portfolio cache.

Uses a real project/month pair, not a mocked condition: HRI-0328 is CRITICAL
risk with a genuinely elevated contractor peer group (Rashtriya Builders Pvt
Ltd: 87.5% significant-delay rate / 100% cost-overrun rate vs. the
portfolio-wide 49.25% / 38.25% -- confirmed via a real batch-scoring run) at
its own latest non-terminal reporting month, 2025-08. Its very next month,
2025-09, is that same project's own terminal (project_status="Completed")
row in the real synthetic CSV. Because risk_positioning is keyed off the
project, not the requested month, both requests see the identical CRITICAL
risk_positioning -- so requesting the 2025-09 (terminal) snapshot is a
genuine, non-vacuous exercise of the leak: before the fix,
peer_elevated_risk_recommendations fired for both months identically.
"""

from __future__ import annotations

from app.decision_intelligence.synthesizer import run_decision_intelligence
from app.decision_support.synthesizer import run_risk_summary

CRITICAL_PROJECT_ID = "HRI-0328"
CRITICAL_NON_TERMINAL_MONTH = "2025-08"
CRITICAL_TERMINAL_MONTH = "2025-09"

ORDINARY_TERMINAL_PROJECT_ID = "HRI-0001"
ORDINARY_TERMINAL_MONTH = "2024-03"

PHASE11_BASIS_TYPES = {"model_driver", "documentary_evidence", "potential_inconsistency", "scenario"}


def _url(project_id: str) -> str:
    return f"/projects/{project_id}/decision-intelligence"


# --- HTTP-level: the real request/router/synthesizer path ---


def test_non_terminal_critical_project_still_gets_portfolio_context_recommendation(client, _phase14_batch_scoring):
    """Regression guard: the fix must not suppress the rule for a genuinely
    non-terminal request -- proves the precondition (the rule DOES fire for
    this project) is real, not assumed."""
    resp = client.get(_url(CRITICAL_PROJECT_ID), params={"reporting_month": CRITICAL_NON_TERMINAL_MONTH})
    assert resp.status_code == 200
    body = resp.json()
    assert body["prediction_status"] == "model_prediction"
    assert body["project"]["is_terminal_snapshot"] is False
    basis_types = {r["basis_type"] for r in body["recommended_reviews"]}
    assert "portfolio_context" in basis_types


def test_terminal_request_for_same_critical_project_has_zero_portfolio_context_recommendations(client, _phase14_batch_scoring):
    resp = client.get(_url(CRITICAL_PROJECT_ID), params={"reporting_month": CRITICAL_TERMINAL_MONTH})
    assert resp.status_code == 200
    body = resp.json()

    # Sanity: this IS a genuinely terminal request, and risk_positioning is
    # still "ok" and elevated (from the project's own cache row) -- i.e. the
    # precondition for the leak is genuinely present here, this isn't a
    # vacuous pass because risk_positioning happened to be LOW/unavailable.
    assert body["prediction_status"] == "actual_outcome"
    assert body["project"]["is_terminal_snapshot"] is True
    assert body["risk_positioning"]["status"] == "ok"
    assert body["risk_positioning"]["risk_level"] in ("HIGH", "CRITICAL")

    basis_types = [r["basis_type"] for r in body["recommended_reviews"]]
    assert "portfolio_context" not in basis_types


def test_terminal_request_still_carries_normal_terminal_behavior(client, _phase14_batch_scoring):
    """The fix must not disturb any other part of the terminal response."""
    resp = client.get(_url(CRITICAL_PROJECT_ID), params={"reporting_month": CRITICAL_TERMINAL_MONTH})
    body = resp.json()

    assert body["risk_drivers"] == []
    assert body["shap_skipped_reason"] is not None
    assert body["scenario"] is None
    assert body["scenario_skipped_reason"] is not None
    for a in body["driver_alignment"]:
        assert a["live_top_driver"] is None
        assert a["agreement"] is None
    # Peer context is unaffected by the terminal gate (state/project_type/
    # contractor are project-level static fields, not month-dependent).
    assert set(body["peer_context"].keys()) == {"state", "project_type", "contractor"}


def test_terminal_request_recommendations_are_only_phase11_basis_types(client, _phase14_batch_scoring):
    resp = client.get(_url(CRITICAL_PROJECT_ID), params={"reporting_month": CRITICAL_TERMINAL_MONTH})
    body = resp.json()
    basis_types = {r["basis_type"] for r in body["recommended_reviews"]}
    assert basis_types <= PHASE11_BASIS_TYPES


def test_ordinary_terminal_project_unaffected_by_the_gate(client, _phase14_batch_scoring):
    """Baseline sanity using the pre-existing terminal fixture project (not
    CRITICAL/elevated) -- confirms the gate doesn't need an elevated project
    to behave correctly."""
    resp = client.get(_url(ORDINARY_TERMINAL_PROJECT_ID), params={"reporting_month": ORDINARY_TERMINAL_MONTH})
    assert resp.status_code == 200
    body = resp.json()
    basis_types = {r["basis_type"] for r in body["recommended_reviews"]}
    assert "portfolio_context" not in basis_types


# --- service-level: exact-text proof that Phase 11's families are untouched,
# and that the gate reads the real requested-snapshot terminal flag ---


def test_terminal_request_phase11_recommendations_pass_through_unchanged(db_session, _phase14_batch_scoring):
    """Independently calls Phase 11's own run_risk_summary for the identical
    real terminal snapshot and confirms every one of its recommendations
    (text/basis_type/basis_detail, in order) appears unchanged in
    run_decision_intelligence's merged recommended_reviews -- proves the
    terminal gate drops only the 5th (portfolio_context) family and never
    touches Phase 11's own 4."""
    rs_result = run_risk_summary(db_session, CRITICAL_PROJECT_ID, CRITICAL_TERMINAL_MONTH)
    di_result = run_decision_intelligence(db_session, CRITICAL_PROJECT_ID, CRITICAL_TERMINAL_MONTH)

    expected = [(r.text, r.basis_type, r.basis_detail) for r in rs_result.recommendations]
    actual = [(r.text, r.basis_type, r.basis_detail) for r in di_result.recommended_reviews]

    assert expected == actual
    assert all(bt != "portfolio_context" for _, bt, _ in actual)


def test_terminal_gate_is_driven_by_the_requested_snapshots_own_terminal_flag(db_session, _phase14_batch_scoring):
    """Direct proof the gate reads the REQUESTED snapshot's own terminal
    flag (Phase 11's ProjectInfo.is_terminal_snapshot), not inferred from
    the portfolio cache: the same project is genuinely CRITICAL/elevated at
    its non-terminal month and genuinely terminal one month later, with
    risk_positioning identical (cache-derived, month-independent) either
    way."""
    non_terminal = run_decision_intelligence(db_session, CRITICAL_PROJECT_ID, CRITICAL_NON_TERMINAL_MONTH)
    terminal = run_decision_intelligence(db_session, CRITICAL_PROJECT_ID, CRITICAL_TERMINAL_MONTH)

    assert non_terminal.risk_summary.project.is_terminal_snapshot is False
    assert terminal.risk_summary.project.is_terminal_snapshot is True

    # Same cached risk positioning either way -- proves the precondition for
    # the historical leak was genuinely present for the terminal request too.
    assert non_terminal.risk_positioning.status == terminal.risk_positioning.status == "ok"
    assert non_terminal.risk_positioning.risk_level == terminal.risk_positioning.risk_level == "CRITICAL"
    assert non_terminal.risk_positioning.composite_risk_score == terminal.risk_positioning.composite_risk_score

    non_terminal_basis_types = {r.basis_type for r in non_terminal.recommended_reviews}
    terminal_basis_types = {r.basis_type for r in terminal.recommended_reviews}
    assert "portfolio_context" in non_terminal_basis_types
    assert "portfolio_context" not in terminal_basis_types


def test_recommendation_cap_still_applies_once_for_non_terminal_request(db_session, _phase14_batch_scoring):
    """Regression guard for the existing cap behavior around the new
    conditional branch."""
    from app.decision_support.recommendations import MAX_TOTAL_RECOMMENDATIONS

    result = run_decision_intelligence(db_session, CRITICAL_PROJECT_ID, CRITICAL_NON_TERMINAL_MONTH)
    assert len(result.recommended_reviews) <= MAX_TOTAL_RECOMMENDATIONS
