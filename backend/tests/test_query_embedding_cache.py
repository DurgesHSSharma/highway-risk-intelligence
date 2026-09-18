"""Tests for app.rag.query_embedding_cache -- the precomputed embeddings for the
FIXED evidence-query strings (see that module's docstring for why it exists).

The central safety claim is that retrieval behaves identically with and without
the cache: same chunks, same ranks, same scores. That is asserted directly here
against the real committed FAISS index and the real embedding model -- never a
fake index or a mocked model.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from app.decision_support.evidence import DEFAULT_EVIDENCE_QUERIES
from app.decision_support.topic_mapping import topic_for_raw_predictor_column
from app.rag import embedding_model, query_embedding_cache as qec
from app.rag.config import EMBEDDING_DIM, EMBEDDING_MODEL_NAME, NORMALIZE_EMBEDDINGS
from app.rag.embedding_model import embed_texts
from app.rag.retrieval import get_retrieval_service
from scripts.prepare_features import PREDICTOR_COLUMNS


@pytest.fixture(autouse=True)
def _fresh_cache():
    qec.reset_fixed_query_cache_for_tests()
    yield
    qec.reset_fixed_query_cache_for_tests()


def _every_query_the_evidence_pipeline_can_send() -> set[str]:
    """Enumerated independently of the build script: the defaults, plus the topic
    phrase for every predictor column a live SHAP driver can resolve to."""
    return set(DEFAULT_EVIDENCE_QUERIES) | {topic_for_raw_predictor_column(c) for c in PREDICTOR_COLUMNS}


def _write_artifact(path, **overrides):
    payload = {
        "embedding_model": EMBEDDING_MODEL_NAME,
        "embedding_dim": EMBEDDING_DIM,
        "normalized": NORMALIZE_EMBEDDINGS,
        "queries": {"project delay": [0.0] * EMBEDDING_DIM},
    }
    payload.update(overrides)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# --- the committed artifact ---------------------------------------------------


def test_every_query_the_evidence_pipeline_can_send_is_cached():
    cache = qec.load_fixed_query_embeddings()
    missing = sorted(_every_query_the_evidence_pipeline_can_send() - cache.keys())
    assert not missing, (
        f"{len(missing)} evidence query string(s) are not in rag_index/fixed_query_embeddings.json: {missing}. "
        "Regenerate it with `python -m scripts.build_query_embedding_cache` (from the repo root)."
    )


def test_cached_vectors_are_well_formed_unit_vectors():
    cache = qec.load_fixed_query_embeddings()
    assert cache, "the committed fixed-query embedding cache should not be empty"
    for query, vector in cache.items():
        assert vector.shape == (1, EMBEDDING_DIM), query
        assert vector.dtype == np.float32, query
        assert np.isfinite(vector).all(), query
        assert abs(float(np.linalg.norm(vector)) - 1.0) < 1e-4, f"{query!r} is not L2-normalized"


def test_cached_vectors_match_the_live_embedding_model():
    """Guards against a stale/foreign artifact: each stored vector must equal what
    the live model produces for the same string today."""
    for query, cached in qec.load_fixed_query_embeddings().items():
        live = embed_texts([query])
        assert np.allclose(cached, live, atol=1e-5), f"cached embedding for {query!r} drifted from the live model"


# --- retrieval is unchanged by the cache -----------------------------------------


def test_retrieval_results_are_identical_with_and_without_the_cache(monkeypatch):
    service = get_retrieval_service()
    for query in sorted(_every_query_the_evidence_pipeline_can_send()):
        with_cache = service.retrieve(query, top_k=5)
        with monkeypatch.context() as m:
            m.setattr(qec, "get_cached_query_embedding", lambda _q: None)  # force the live model
            live = service.retrieve(query, top_k=5)

        assert with_cache.not_found == live.not_found, query
        assert [r.chunk_id for r in with_cache.results] == [r.chunk_id for r in live.results], query
        assert [r.rank for r in with_cache.results] == [r.rank for r in live.results], query
        for a, b in zip(with_cache.results, live.results):
            assert a.similarity_score == pytest.approx(b.similarity_score, abs=1e-5), query


# --- the model is only used when it has to be ----------------------------------------


def test_a_fixed_query_never_touches_the_embedding_model(monkeypatch):
    def _forbidden(*_args, **_kwargs):
        raise AssertionError("the embedding model must not be used for a cached fixed query")

    # Block both the cache module's fallback AND the lowest-level model loader, so the
    # test also fails if retrieval ever bypasses `embed_query` and reaches the model
    # some other way.
    monkeypatch.setattr(qec, "embed_texts", _forbidden)
    monkeypatch.setattr(embedding_model, "get_embedding_model", _forbidden)
    response = get_retrieval_service().retrieve("project delay", top_k=3)
    assert response.query == "project delay"  # retrieval completed without the model


def test_a_free_text_query_still_uses_the_live_model(monkeypatch):
    real = qec.embed_texts
    calls: list[list[str]] = []

    def _counting(texts):
        calls.append(list(texts))
        return real(texts)

    monkeypatch.setattr(qec, "embed_texts", _counting)
    query = "How much money has NHAI raised through the InvIT mode?"
    response = get_retrieval_service().retrieve(query, top_k=3)
    assert calls == [[query]]
    assert not response.not_found  # the real in-corpus question still resolves


@pytest.mark.parametrize("variant", ["Project Delay", "project delay ", " project delay", "PROJECT DELAY"])
def test_matching_is_exact_string_only(variant):
    assert qec.get_cached_query_embedding("project delay") is not None
    assert qec.get_cached_query_embedding(variant) is None


def test_returned_vector_is_a_copy_so_the_shared_cache_cannot_be_mutated():
    first = qec.get_cached_query_embedding("project delay")
    first[:] = 123.0
    second = qec.get_cached_query_embedding("project delay")
    assert not np.allclose(second, 123.0)
    assert abs(float(np.linalg.norm(second)) - 1.0) < 1e-4


# --- the cache is only ever an optimization: bad artifacts are ignored ----------------


def test_missing_artifact_disables_the_cache_without_raising(tmp_path):
    assert qec.load_fixed_query_embeddings(tmp_path / "does_not_exist.json") == {}


def test_unreadable_artifact_is_ignored(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{ this is not json", encoding="utf-8")
    assert qec.load_fixed_query_embeddings(bad) == {}


@pytest.mark.parametrize(
    "override",
    [
        {"embedding_model": "some-other/model"},
        {"embedding_dim": EMBEDDING_DIM + 1},
        {"normalized": not NORMALIZE_EMBEDDINGS},
        {"queries": {"project delay": [0.0] * (EMBEDDING_DIM - 1)}},  # wrong vector length
        {"queries": {"project delay": [float("nan")] * EMBEDDING_DIM}},  # non-finite values
    ],
)
def test_artifact_for_a_different_model_or_with_bad_vectors_is_rejected_whole(tmp_path, override):
    assert qec.load_fixed_query_embeddings(_write_artifact(tmp_path / "a.json", **override)) == {}


def test_valid_artifact_round_trips(tmp_path):
    loaded = qec.load_fixed_query_embeddings(_write_artifact(tmp_path / "ok.json"))
    assert set(loaded) == {"project delay"}
    assert loaded["project delay"].shape == (1, EMBEDDING_DIM)


def test_embed_query_falls_back_to_the_live_model_when_the_cache_is_unavailable(monkeypatch):
    monkeypatch.setattr(qec, "load_fixed_query_embeddings", lambda *a, **k: {})
    real = qec.embed_texts
    calls: list[list[str]] = []
    monkeypatch.setattr(qec, "embed_texts", lambda texts: (calls.append(list(texts)), real(texts))[1])
    qec.reset_fixed_query_cache_for_tests()

    vector = qec.embed_query("project delay")
    assert calls == [["project delay"]]
    assert vector.shape == (1, EMBEDDING_DIM)
