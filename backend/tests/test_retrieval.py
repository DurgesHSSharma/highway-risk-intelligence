"""Phase 8 retrieval tests, against the REAL committed rag_index/ built from
the real 4-document corpus (loaded once for the whole session by the
`_phase8_rag_index` conftest fixture) -- never a fake/mocked index, per the
project's no-fabrication rule.

The hand-built question set (tests/fixtures/rag_test_questions.json, one
level up at the repo root) was written after reading actual chunk text and
verified by running the real retrieval service -- see
docs/RAG_SYSTEM.md "Test-question methodology".
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.config import REPO_ROOT
from app.rag.config import RELEVANCE_THRESHOLD
from app.rag.retrieval import InvalidQueryError, get_retrieval_service

FIXTURES_PATH = REPO_ROOT / "tests" / "fixtures" / "rag_test_questions.json"


@pytest.fixture(scope="module")
def question_set() -> dict:
    return json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def service():
    return get_retrieval_service()


def test_service_loaded_with_full_real_corpus(service):
    assert service.vector_count == 861
    assert service.mapping_count == 861


def test_retrieve_returns_ranked_results(service):
    response = service.retrieve("highway project cost overrun and delay", top_k=5)
    assert not response.not_found
    assert len(response.results) > 0
    ranks = [r.rank for r in response.results]
    assert ranks == list(range(1, len(response.results) + 1))


def test_similarity_scores_are_ordered_descending(service):
    response = service.retrieve("Bharatmala Pariyojana land acquisition delay", top_k=5, threshold=0.0)
    scores = [r.similarity_score for r in response.results]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.parametrize("top_k", [1, 3, 5])
def test_top_k_limits_result_count(service, top_k):
    response = service.retrieve("What was the Delhi-Vadodara Expressway cost-benefit analysis compared against?", top_k=top_k)
    assert len(response.results) <= top_k


@pytest.mark.parametrize("bad_query", ["", "   ", None])
def test_invalid_or_empty_query_raises_clear_error(service, bad_query):
    with pytest.raises(InvalidQueryError):
        service.retrieve(bad_query, top_k=5)


def test_relevance_threshold_filters_low_scoring_candidates(service):
    query = "What was the Delhi-Vadodara Expressway cost-benefit analysis compared against?"
    permissive = service.retrieve(query, top_k=5, threshold=0.0)
    strict = service.retrieve(query, top_k=5, threshold=0.99)

    assert len(permissive.results) > 0
    assert strict.not_found is True
    assert strict.results == []


def test_out_of_corpus_questions_return_not_found(service, question_set):
    for case in question_set["out_of_corpus"]:
        response = service.retrieve(case["question"], top_k=5, threshold=RELEVANCE_THRESHOLD)
        assert response.not_found is True, f"expected not_found for out-of-corpus query: {case['question']!r}"
        assert response.results == []


def test_in_corpus_questions_retrieve_expected_document_and_page_within_topk(service, question_set):
    failures = []
    for case in question_set["in_corpus"]:
        response = service.retrieve(case["question"], top_k=5, threshold=0.0)
        hit = any(
            r.document_id == case["expected_document_id"] and r.page_number == case["expected_page_number"]
            for r in response.results
        )
        if not hit:
            failures.append(case["id"])
    assert not failures, f"these grounded questions did not retrieve their expected doc/page in top-5: {failures}"


def test_low_quality_flagged_chunk_is_retrievable_and_flag_is_preserved(service):
    metadata_path = REPO_ROOT / "rag_index" / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    flagged_entries = [e for e in metadata["mapping"] if e["extraction_quality_flag"] is not None]
    assert len(flagged_entries) == 10

    target = next(e for e in flagged_entries if e["extraction_quality_flag"] == "low_ocr_quality")
    response = service.retrieve(target["text"], top_k=10, threshold=0.0)

    match = next((r for r in response.results if r.chunk_id == target["chunk_id"]), None)
    assert match is not None, "the flagged chunk's own text did not retrieve itself within top-10"
    assert match.quality_flag == "low_ocr_quality"


def test_citation_format(service):
    response = service.retrieve("NHAI congestion points on national highways", top_k=1, threshold=0.0)
    assert len(response.results) == 1
    citation = response.results[0].citation()
    assert re.match(r"^\[DOC-\d{3}, p\. \d+\]$", citation), citation


def test_retrieval_is_deterministic_for_repeated_queries(service):
    query = "What change of scope was recommended for the Hapur Bypass-Moradabad project?"
    first = service.retrieve(query, top_k=5, threshold=0.0)
    second = service.retrieve(query, top_k=5, threshold=0.0)

    first_ids = [r.chunk_id for r in first.results]
    second_ids = [r.chunk_id for r in second.results]
    first_scores = [r.similarity_score for r in first.results]
    second_scores = [r.similarity_score for r in second.results]

    assert first_ids == second_ids
    assert first_scores == second_scores
