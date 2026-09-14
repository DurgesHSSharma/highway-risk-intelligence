"""Phase 8 API tests: GET /documents/search against the real running FastAPI
app (via TestClient, real committed rag_index/ loaded once per session by
conftest's `_phase8_rag_index` fixture). A separate REAL uvicorn smoke test
(not TestClient) was also run manually -- see docs/RAG_SYSTEM.md "API smoke
test" and the Phase 8 completion report.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_search_returns_relevant_results_for_in_corpus_query(client: TestClient):
    resp = client.get(
        "/documents/search",
        params={"q": "What was the Delhi-Vadodara Expressway cost-benefit analysis compared against?", "top_k": 5},
    )
    assert resp.status_code == 200
    body = resp.json()

    assert body["not_found"] is False
    assert body["mode"] == "extractive"
    assert len(body["results"]) > 0
    top = body["results"][0]
    assert top["document_id"] == "DOC-001"
    assert top["page_number"] == 60
    assert top["citation"] == "[DOC-001, p. 60]"
    assert body["answer"].startswith("From [DOC-001, p. 60]")
    assert '"' in body["answer"]


def test_search_out_of_corpus_query_returns_not_found(client: TestClient):
    resp = client.get("/documents/search", params={"q": "What is the recipe for making chocolate cake?", "top_k": 5})
    assert resp.status_code == 200
    body = resp.json()

    assert body["not_found"] is True
    assert body["results"] == []
    assert body["answer"] == "Not found in the available documents."


def test_search_empty_query_returns_422(client: TestClient):
    resp = client.get("/documents/search", params={"q": ""})
    assert resp.status_code == 422


def test_search_whitespace_only_query_returns_422(client: TestClient):
    resp = client.get("/documents/search", params={"q": "   "})
    assert resp.status_code == 422


def test_search_missing_query_param_returns_422(client: TestClient):
    resp = client.get("/documents/search")
    assert resp.status_code == 422


def test_search_respects_top_k(client: TestClient):
    resp = client.get("/documents/search", params={"q": "highway construction national highways India", "top_k": 1})
    assert resp.status_code == 200
    assert len(resp.json()["results"]) <= 1


def test_search_low_quality_flag_visible_in_response(client: TestClient):
    resp = client.get("/documents/search", params={"q": "CHAPTER 4 FUND MANAGEMENT", "top_k": 10})
    assert resp.status_code == 200
    body = resp.json()
    flags = [r["quality_flag"] for r in body["results"]]
    assert any(f is not None for f in flags), "expected at least one flagged result for this OCR heading query"


def test_search_response_includes_corpus_disclaimer(client: TestClient):
    resp = client.get("/documents/search", params={"q": "national highways", "top_k": 3})
    assert resp.status_code == 200
    assert "4 real public documents" in resp.json()["corpus_disclaimer"]


def test_existing_phase6_prediction_endpoint_still_works(client: TestClient):
    """Sanity check that adding Phase 8's router/lifespan resource did not
    break the Phase 6 prediction endpoint."""
    resp = client.get("/health")
    assert resp.status_code == 200

    projects_resp = client.get("/projects", params={"page": 1, "page_size": 1})
    assert projects_resp.status_code == 200
    assert projects_resp.json()["total"] > 0
