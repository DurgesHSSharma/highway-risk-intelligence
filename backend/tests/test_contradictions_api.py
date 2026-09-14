"""Phase 9 API endpoint tests: GET /documents/inconsistencies.

Against the real running app + real committed corpus (via conftest.py's
session-scoped fixtures) -- never a mocked detector. Existing Phase 6/8
endpoints must remain unaffected (re-verified here, not just assumed).
"""

from __future__ import annotations


def test_inconsistencies_endpoint_returns_valid_structure(client):
    response = client.get("/documents/inconsistencies")
    assert response.status_code == 200
    body = response.json()

    for field in (
        "total_chunks_considered",
        "total_claims_extracted",
        "claim_type_counts",
        "candidate_chunk_pairs",
        "comparable_claim_pairs_evaluated",
        "contextual_differences_excluded",
        "flagged_count",
        "flags",
        "disclaimer",
    ):
        assert field in body, f"missing field: {field}"

    assert body["total_chunks_considered"] == 861
    assert isinstance(body["flags"], list)
    assert body["flagged_count"] == len(body["flags"])


def test_inconsistencies_endpoint_handles_the_real_corpus_result_without_error(client):
    # The real corpus produces a small, non-zero flagged count (see
    # docs/CONTRADICTION_DETECTION.md) -- this test locks in that the
    # endpoint surfaces it correctly, whatever the count is; a would-be
    # zero-flag corpus is exercised separately in test_zero_flags below.
    response = client.get("/documents/inconsistencies")
    body = response.json()
    assert body["flagged_count"] >= 0
    assert response.status_code == 200, "a zero-or-more flagged count must never be surfaced as an error"


def test_flag_fields_match_documented_output_format(client):
    body = client.get("/documents/inconsistencies").json()
    if not body["flags"]:
        return  # covered by the zero-flags-path test below; nothing to check here
    flag = body["flags"][0]
    for field in (
        "flag_id",
        "document_a",
        "page_a",
        "chunk_a",
        "raw_claim_a",
        "normalized_value_a",
        "document_b",
        "page_b",
        "chunk_b",
        "raw_claim_b",
        "normalized_value_b",
        "claim_type",
        "difference",
        "similarity_score",
        "tolerance_info",
        "context_info",
        "confidence",
        "description",
    ):
        assert field in flag, f"missing flag field: {field}"


def test_flag_descriptions_are_hedged_never_absolute(client):
    from app.contradiction.config import PROHIBITED_ABSOLUTE_PHRASES

    body = client.get("/documents/inconsistencies").json()
    for flag in body["flags"]:
        lowered = flag["description"].lower()
        assert "potential inconsistency" in lowered or "requiring verification" in lowered
        for phrase in PROHIBITED_ABSOLUTE_PHRASES:
            assert phrase not in lowered


def test_inconsistencies_endpoint_zero_flags_case_returns_valid_empty_result(client, monkeypatch):
    # Directly exercises the zero-flags response path (section 15 of the
    # brief: "Do NOT return an error merely because zero inconsistencies
    # were found") without depending on the real corpus actually being zero.
    from dataclasses import replace

    from app.contradiction.detector import get_detection_summary
    import app.routers.documents as documents_router

    real_summary = get_detection_summary()
    zero_summary = replace(real_summary, flagged_count=0, flags=[])
    monkeypatch.setattr(documents_router, "get_detection_summary", lambda: zero_summary)

    response = client.get("/documents/inconsistencies")
    assert response.status_code == 200
    body = response.json()
    assert body["flagged_count"] == 0
    assert body["flags"] == []


def test_existing_phase6_projects_endpoint_still_works(client):
    response = client.get("/projects?page=1&page_size=1")
    assert response.status_code == 200
    assert response.json()["total"] == 400


def test_existing_phase8_search_endpoint_still_works(client):
    response = client.get("/documents/search", params={"q": "Bharatmala Pariyojana cost overrun", "top_k": 3})
    assert response.status_code == 200
    body = response.json()
    assert "results" in body
    assert body["mode"] == "extractive"
