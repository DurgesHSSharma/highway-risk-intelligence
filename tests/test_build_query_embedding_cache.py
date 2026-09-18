"""Tests for scripts/build_query_embedding_cache.py, run at the repo root (same
convention as tests/test_build_rag_index.py). They exercise the real embedding
model and the real committed rag_index/fixed_query_embeddings.json -- never a
fake model or a stand-in artifact; only the CLI-output test writes to tmp_path.
"""

from __future__ import annotations

import json
import sys

import numpy as np

import scripts.build_query_embedding_cache as builder  # adds backend/ to sys.path as a side effect

from app.decision_support.evidence import DEFAULT_EVIDENCE_QUERIES  # noqa: E402
from app.decision_support.topic_mapping import FEATURE_TOPIC_MAP  # noqa: E402
from app.rag.config import (  # noqa: E402
    EMBEDDING_DIM,
    EMBEDDING_MODEL_NAME,
    FIXED_QUERY_EMBEDDINGS_PATH,
    NORMALIZE_EMBEDDINGS,
)


def _committed() -> dict:
    return json.loads(FIXED_QUERY_EMBEDDINGS_PATH.read_text(encoding="utf-8"))


def test_enumerated_queries_are_the_defaults_plus_every_topic_phrase_sorted_and_unique():
    queries = builder.enumerate_fixed_queries()
    assert queries == sorted(set(DEFAULT_EVIDENCE_QUERIES) | set(FEATURE_TOPIC_MAP.values()))
    assert len(queries) == len(set(queries))
    for default in DEFAULT_EVIDENCE_QUERIES:
        assert default in queries


def test_committed_artifact_holds_exactly_the_enumerated_queries_for_the_configured_model():
    payload = _committed()
    assert payload["embedding_model"] == EMBEDDING_MODEL_NAME
    assert payload["embedding_dim"] == EMBEDDING_DIM
    assert payload["normalized"] is NORMALIZE_EMBEDDINGS
    assert sorted(payload["queries"]) == builder.enumerate_fixed_queries()
    assert payload["query_count"] == len(payload["queries"])
    for query, values in payload["queries"].items():
        assert len(values) == EMBEDDING_DIM, query


def test_regenerating_reproduces_the_committed_vectors():
    """Reproducibility: rebuilding from the real model gives the committed vectors
    (tolerance only for cross-machine float noise, ~1e-7)."""
    regenerated = json.loads(builder.build_payload_text(builder.enumerate_fixed_queries()))
    committed = _committed()
    assert sorted(regenerated["queries"]) == sorted(committed["queries"])
    for query, values in committed["queries"].items():
        assert np.allclose(values, regenerated["queries"][query], atol=1e-6), query


def test_cli_writes_a_valid_lf_only_artifact(tmp_path, monkeypatch):
    out = tmp_path / "fixed_query_embeddings.json"
    monkeypatch.setattr(sys, "argv", ["build_query_embedding_cache", "--output", str(out)])
    builder.main()

    raw = out.read_bytes()
    assert b"\r" not in raw, "artifact must use LF line endings (.gitattributes: *.json eol=lf)"
    payload = json.loads(raw.decode("utf-8"))
    assert sorted(payload["queries"]) == builder.enumerate_fixed_queries()
    assert raw.endswith(b"\n")
