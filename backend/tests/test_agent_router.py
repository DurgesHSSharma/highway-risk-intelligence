"""Phase 17C "Ask HRI" end-to-end tests: POST /agent/query against the
real committed dataset/models/RAG index/contradiction detector (the shared
session `client` fixture, backend/tests/conftest.py) -- never a fabricated
fixture, matching this project's established convention for every other
grounded endpoint's tests.

HRI-0006/2022-12 (non-terminal) and HRI-0006/2023-06 (terminal) are the
same real, previously-documented examples Phases 11/12/17 already use
elsewhere in this test suite.
"""

from __future__ import annotations

NON_TERMINAL_PROJECT = "HRI-0006"
NON_TERMINAL_MONTH = "2022-12"
TERMINAL_MONTH = "2023-06"


def _post(client, message, project_id=None):
    body = {"message": message}
    if project_id is not None:
        body["project_id"] = project_id
    return client.post("/agent/query", json=body)


# --- one test per required query category --------------------------------


def test_project_query(client):
    resp = _post(client, f"Show me information about {NON_TERMINAL_PROJECT}.")
    assert resp.status_code == 200
    body = resp.json()
    assert body["intent"] == "project"
    assert body["answer_type"] == "actual"
    assert NON_TERMINAL_PROJECT in body["message"]


def test_risk_query(client):
    resp = _post(client, f"Why is {NON_TERMINAL_PROJECT} high risk? {NON_TERMINAL_MONTH}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["intent"] == "risk"
    assert body["answer_type"] == "prediction"
    assert body["predictions"]["significant_delay_probability"] is not None


def test_portfolio_query(client):
    resp = _post(client, "Which projects have high delay risk?")
    assert resp.status_code == 200
    body = resp.json()
    assert body["intent"] == "portfolio"
    assert body["answer_type"] == "prediction"
    assert len(body["message"]) > 0


def test_document_query(client):
    resp = _post(client, "What do the project documents say about cost escalation?")
    assert resp.status_code == 200
    body = resp.json()
    assert body["intent"] == "document"
    assert body["answer_type"] == "document_evidence"
    assert len(body["citations"]) > 0
    for c in body["citations"]:
        assert c["document_id"]
        assert c["citation"].startswith("[")


def test_whatif_query(client):
    resp = _post(client, f"What happens if progress improves by 10% for {NON_TERMINAL_PROJECT}? {NON_TERMINAL_MONTH}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["intent"] == "whatif"
    assert body["answer_type"] == "hypothetical"
    assert "hypothetical" in body["message"].lower()


def test_support_query(client):
    resp = _post(client, "How do I archive a project?")
    assert resp.status_code == 200
    body = resp.json()
    assert body["intent"] == "support"
    assert body["answer_type"] == "support"
    assert "archive" in body["message"].lower()


def test_unsupported_query(client):
    resp = _post(client, "Who will win the next election?")
    assert resp.status_code == 200
    body = resp.json()
    assert body["intent"] == "unsupported"
    assert body["answer_type"] == "unsupported"
    assert body["message"] == "HRI does not have sufficient information to answer that."


# --- missing entity / context -----------------------------------------


def test_risk_query_without_project_id_asks_for_clarification(client):
    resp = _post(client, "Why is this so risky?")
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer_type"] == "unsupported"
    assert "which project" in body["message"].lower()


def test_project_query_without_id_returns_clarification_not_a_guess(client):
    resp = _post(client, "Show me the project details.")
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer_type"] == "unsupported"
    assert "which project" in body["message"].lower()


def test_project_context_from_page_is_used_when_message_has_no_id(client):
    resp = _post(client, "Tell me about this project.", project_id=NON_TERMINAL_PROJECT)
    assert resp.status_code == 200
    body = resp.json()
    assert body["project_id"] == NON_TERMINAL_PROJECT
    assert body["answer_type"] == "actual"


def test_explicit_id_in_message_wins_over_page_context(client):
    resp = _post(client, "Show me information about HRI-0019.", project_id=NON_TERMINAL_PROJECT)
    assert resp.status_code == 200
    assert resp.json()["project_id"] == "HRI-0019"


def test_unknown_project_returns_honest_not_found_not_a_500(client):
    resp = _post(client, "Show me information about HRI-9999.")
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer_type"] == "unsupported"
    assert "HRI-9999" in body["message"]


# --- actual vs prediction vs hypothetical labeling -----------------------


def test_terminal_snapshot_risk_query_is_labeled_actual_not_prediction(client):
    resp = _post(client, f"Why is {NON_TERMINAL_PROJECT} high risk? {TERMINAL_MONTH}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer_type"] == "actual"
    assert body["predictions"]["actual_final_delay_days"] is not None
    assert body["predictions"]["final_delay_days_predicted"] is None  # never blended
    assert "actual" in body["message"].lower()


def test_non_terminal_risk_query_is_labeled_prediction_not_actual(client):
    resp = _post(client, f"Why is {NON_TERMINAL_PROJECT} high risk? {NON_TERMINAL_MONTH}")
    body = resp.json()
    assert resp.status_code == 200
    assert body["answer_type"] == "prediction"
    assert body["predictions"]["actual_final_delay_days"] is None  # never blended


def test_whatif_is_always_labeled_hypothetical_never_prediction(client):
    resp = _post(client, f"What happens if cost increases by 5% for {NON_TERMINAL_PROJECT}? {NON_TERMINAL_MONTH}")
    body = resp.json()
    assert body["answer_type"] == "hypothetical"
    assert body["disclaimer"] is not None


# --- terminal-project what-if safety -------------------------------------


def test_whatif_on_a_project_with_only_a_terminal_snapshot_never_fabricates(client):
    """A project whose only reachable snapshot is terminal cannot be
    what-if'd (the existing simulator rejects terminal snapshots) -- this
    must come back as an honest unsupported/clarification response, never
    a fabricated hypothetical result."""
    resp = _post(client, f"What happens if progress improves by 10% for {NON_TERMINAL_PROJECT}? {TERMINAL_MONTH}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer_type"] == "unsupported"


def test_whatif_malformed_request_is_unsupported_not_an_error(client):
    resp = _post(client, f"What happens if progress improves for {NON_TERMINAL_PROJECT}?")  # no %
    assert resp.status_code == 200
    assert resp.json()["answer_type"] == "unsupported"


def test_whatif_unrecognized_concept_is_unsupported(client):
    resp = _post(client, f"What happens if the moon turns blue by 10% for {NON_TERMINAL_PROJECT}?")
    assert resp.status_code == 200
    assert resp.json()["answer_type"] == "unsupported"


# --- hallucination resistance / citation presence -------------------------


def test_out_of_corpus_document_query_says_not_found_never_invents_a_citation(client):
    resp = _post(client, "What do the documents say about the recipe for chocolate cake?")
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer_type"] == "unsupported"
    assert body["citations"] == []
    assert "not found" in body["message"].lower()


def test_document_query_citations_reference_real_documents_only(client):
    resp = _post(client, "What do the documents say about Bharatmala?")
    assert resp.status_code == 200
    body = resp.json()
    if body["answer_type"] == "document_evidence":
        for c in body["citations"]:
            assert c["document_id"].startswith("DOC-")
            assert isinstance(c["page_number"], int)
            assert len(c["text"]) > 0


def test_risk_query_never_fabricates_a_shap_driver_name(client):
    resp = _post(client, f"Why is {NON_TERMINAL_PROJECT} high risk? {NON_TERMINAL_MONTH}")
    body = resp.json()
    from scripts.prepare_features import PREDICTOR_COLUMNS

    # The synthesized message names a driver via backtick-quoted
    # `feature_name` -- if present, it must be one of the audited 45
    # predictor columns, never an invented string.
    import re

    matches = re.findall(r"`([a-z_]+)`", body["message"])
    assert matches, "expected at least one backtick-quoted driver name"
    for name in matches:
        assert name in PREDICTOR_COLUMNS


# --- malformed input / expected-error handling -----------------------


def test_empty_message_returns_422(client):
    resp = client.post("/agent/query", json={"message": ""})
    assert resp.status_code == 422


def test_missing_message_field_returns_422(client):
    resp = client.post("/agent/query", json={})
    assert resp.status_code == 422


def test_overlong_message_returns_422(client):
    resp = client.post("/agent/query", json={"message": "x" * 5000})
    assert resp.status_code == 422


def test_no_scenario_here_produces_a_500(client):
    """Sweeps every required category plus edge cases once more, asserting
    only that none of them ever returns a 5xx -- the master prompt's
    explicit "no expected case should produce a 500" requirement."""
    messages = [
        "Show me information about HRI-0006.",
        "Show me information about HRI-9999.",
        f"Why is {NON_TERMINAL_PROJECT} high risk?",
        "Which projects have high delay risk?",
        "What is the risk distribution by state?",
        "What do the documents say about cost escalation?",
        "What do the documents say about chocolate cake recipes?",
        f"What happens if progress improves by 10% for {NON_TERMINAL_PROJECT}? {NON_TERMINAL_MONTH}",
        f"What happens if progress improves for {NON_TERMINAL_PROJECT}?",
        "How do I add a new highway?",
        "How do I archive a project?",
        "Who will win the next election?",
        "",
    ]
    for message in messages:
        if message == "":
            continue  # covered by test_empty_message_returns_422 as a 422, not this sweep
        resp = _post(client, message)
        assert resp.status_code < 500, f"{message!r} -> {resp.status_code}: {resp.text}"
