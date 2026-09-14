"""Phase 11 (REPAIRED) service-level tests for
`app.decision_support.synthesizer.run_risk_summary`.

Runs against the real committed corpus/models/DB (via the session-scoped
fixtures in conftest.py) rather than mocks. `HRI-0006`/`2022-12` and
`HRI-0001`/`2024-03` mirror the exact fixtures already used by
test_predictions_api.py / test_simulation_api.py.
"""

from __future__ import annotations

import re

from app.decision_support.synthesizer import run_risk_summary
from app.rag.retrieval import get_retrieval_service
from app.schemas.simulation import SIMULATION_DISCLAIMER

NON_TERMINAL_PROJECT_ID = "HRI-0006"
NON_TERMINAL_MONTH = "2022-12"

TERMINAL_PROJECT_ID = "HRI-0001"
TERMINAL_MONTH = "2024-03"

_PROHIBITED_SUBSTRINGS = ("confirmed contradiction", "confirmed error", "will definitely")
_PROHIBITED_WORDS = ("false", "wrong", "incorrect", "guaranteed", "causes")


def _assert_no_prohibited_language(text: str) -> None:
    lowered = text.lower()
    for phrase in _PROHIBITED_SUBSTRINGS:
        assert phrase not in lowered, f"prohibited phrase {phrase!r} found in: {text!r}"
    for word in _PROHIBITED_WORDS:
        assert not re.search(rf"\b{word}\b", lowered), f"prohibited word {word!r} found in: {text!r}"


def _collect_generated_text(result) -> list[str]:
    texts = [
        result.risk_summary.significant_delay_summary,
        result.risk_summary.final_delay_days_summary,
        result.risk_summary.cost_overrun_summary,
        result.risk_summary.final_cost_overrun_pct_summary,
        result.evidence_strength_basis,
    ]
    for d in result.risk_drivers:
        for f in d.top_drivers:
            texts.append(f.explanation)
    for r in result.recommendations:
        texts.append(r.text)
        texts.append(r.basis_detail)
    return texts


# --- valid non-terminal response: predictions, SHAP drivers, model-estimate labeling ---


def test_non_terminal_valid_response(db_session):
    result = run_risk_summary(db_session, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH)

    assert result.prediction_status == "model_prediction"
    assert result.project.is_terminal_snapshot is False
    assert result.shap_skipped_reason is None

    assert result.predictions["significant_delay"].probability_of_significant_delay is not None
    assert result.predictions["final_delay_days"].predicted_final_delay_days is not None
    assert result.predictions["cost_overrun"].probability_of_cost_overrun is not None
    assert result.predictions["final_cost_overrun_pct"].predicted_final_cost_overrun_pct is not None

    assert "probability" in result.risk_summary.significant_delay_summary.lower()
    assert "model" in result.risk_summary.final_delay_days_summary.lower()


def test_non_terminal_has_live_shap_drivers_for_all_four_tasks(db_session):
    result = run_risk_summary(db_session, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH)
    assert len(result.risk_drivers) == 4
    by_task = {d.task_key: d for d in result.risk_drivers}

    assert by_task["significant_delay"].explainer_type == "TreeExplainer"
    assert by_task["final_delay_days"].explainer_type == "TreeExplainer"
    assert by_task["cost_overrun"].explainer_type == "LinearExplainer"
    assert by_task["final_cost_overrun_pct"].explainer_type == "LinearExplainer"

    for d in result.risk_drivers:
        assert len(d.top_drivers) == 5


def test_no_causal_or_prohibited_absolute_wording(db_session):
    result = run_risk_summary(db_session, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH)
    for text in _collect_generated_text(result):
        _assert_no_prohibited_language(text)


# --- RAG evidence: derived from live SHAP drivers, reuses the exact retrieval service ---


def test_evidence_queries_derived_from_live_shap_drivers(db_session):
    result = run_risk_summary(db_session, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH)
    sig_delay_top = result.risk_drivers[0].top_drivers[0]

    from app.decision_support.topic_mapping import topic_for_raw_predictor_column

    expected_first_query = topic_for_raw_predictor_column(sig_delay_top.feature)
    assert result.evidence[0].query == expected_first_query


def test_evidence_reuses_the_exact_retrieval_service_results(db_session):
    """Proves the decision-support response uses the same direct
    retrieval-service results for the generated SHAP-driven query --
    not a reimplemented retrieval algorithm."""
    result = run_risk_summary(db_session, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH)
    query = result.evidence[0].query

    service = get_retrieval_service()
    direct = service.retrieve(query, top_k=3)

    assert result.evidence[0].not_found == direct.not_found
    assert [r.chunk_id for r in result.evidence[0].results] == [r.chunk_id for r in direct.results]
    assert [r.similarity_score for r in result.evidence[0].results] == [
        r.similarity_score for r in direct.results
    ]


def test_evidence_citations_valid_and_no_fabrication_when_not_found(db_session):
    result = run_risk_summary(db_session, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH)
    for item in result.evidence:
        if item.not_found:
            assert item.results == []
            assert item.answer == "Not found in the available documents."
        else:
            for r in item.results:
                assert re.match(r"^\[DOC-\d+, p\. \d+\]$", r.citation())


# --- Phase 9 potential inconsistencies ---


def test_potential_inconsistencies_hedged_or_empty(db_session):
    result = run_risk_summary(db_session, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH)
    # Empty is a valid, explicit result -- not manufactured.
    for flag in result.inconsistencies:
        lowered = flag.description.lower()
        assert "potential inconsistency" in lowered
        assert "requiring verification" in lowered
        _assert_no_prohibited_language(flag.description)


# --- illustrative scenario: auto-derived from live top SHAP driver, Phase 10 reused ---


def test_scenario_is_auto_derived_from_live_top_significant_delay_driver(db_session):
    result = run_risk_summary(db_session, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH)
    sig_top = result.risk_drivers[0].top_drivers[0]

    assert result.scenario is not None
    assert result.scenario.field == sig_top.feature
    assert "illustrative" in result.scenario.label.lower()
    assert "not a recommendation" in result.scenario.label.lower()


def test_scenario_baseline_matches_phase6_prediction(db_session):
    result = run_risk_summary(db_session, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH)
    baseline_delay = result.scenario.baseline_predictions["final_delay_days"].predicted_final_delay_days
    direct_delay = result.predictions["final_delay_days"].predicted_final_delay_days
    assert baseline_delay == direct_delay


def test_scenario_disclaimer_preserved():
    from app.schemas.decision_support import ScenarioOut

    assert ScenarioOut.model_fields["disclaimer"].default == SIMULATION_DISCLAIMER


def test_scenario_recommendation_labeled_illustrative_not_a_recommendation(db_session):
    result = run_risk_summary(db_session, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH)
    scenario_recs = [r for r in result.recommendations if r.basis_type == "scenario"]
    assert len(scenario_recs) >= 1
    assert "illustrative, not a recommendation" in scenario_recs[0].text.lower()


# --- terminal snapshot: prediction/SHAP/simulation skipped, evidence/inconsistencies still run ---


def test_terminal_snapshot_skips_prediction_shap_and_simulation(db_session):
    result = run_risk_summary(db_session, TERMINAL_PROJECT_ID, TERMINAL_MONTH)

    assert result.project.is_terminal_snapshot is True
    assert result.prediction_status == "actual_outcome"

    # No model prediction: actual_value populated, predicted fields None.
    assert result.predictions["significant_delay"].actual_value is not None
    assert result.predictions["significant_delay"].predicted_class is None
    assert result.predictions["significant_delay"].probability_of_significant_delay is None

    # SHAP explicitly skipped, not silently empty.
    assert result.risk_drivers == []
    assert result.shap_skipped_reason is not None
    assert "terminal" in result.shap_skipped_reason.lower()

    # Simulation explicitly skipped.
    assert result.scenario is None
    assert result.scenario_skipped_reason is not None
    assert "terminal" in result.scenario_skipped_reason.lower()


def test_terminal_snapshot_still_runs_evidence_and_inconsistencies(db_session):
    result = run_risk_summary(db_session, TERMINAL_PROJECT_ID, TERMINAL_MONTH)
    assert len(result.evidence) > 0
    # inconsistencies may legitimately be empty -- just confirm the section
    # ran (didn't raise / isn't None).
    assert result.inconsistencies is not None


def test_terminal_snapshot_risk_summary_states_recorded_outcome_not_model_estimate(db_session):
    result = run_risk_summary(db_session, TERMINAL_PROJECT_ID, TERMINAL_MONTH)
    for text in [
        result.risk_summary.significant_delay_summary,
        result.risk_summary.final_delay_days_summary,
        result.risk_summary.cost_overrun_summary,
        result.risk_summary.final_cost_overrun_pct_summary,
    ]:
        assert "recorded actual outcome" in text.lower()
        assert "probability" not in text.lower()


# --- recommendations: every one has a concrete basis ---


def test_every_recommendation_has_a_concrete_basis(db_session):
    result = run_risk_summary(db_session, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH)
    assert len(result.recommendations) > 0
    for r in result.recommendations:
        assert r.basis_type in {"model_driver", "documentary_evidence", "potential_inconsistency", "scenario"}
        assert r.basis_detail.strip() != ""


# --- evidence_strength ---


def test_evidence_strength_is_one_of_three_categories(db_session):
    result = run_risk_summary(db_session, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH)
    assert result.evidence_strength in (
        "high evidence support",
        "moderate evidence support",
        "limited evidence support",
    )
