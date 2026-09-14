"""Phase 9 cross-document topic pairing tests, against the REAL committed
rag_index/ built from the real 4-document corpus (loaded once per session
by conftest.py's `_phase8_rag_index` fixture) -- never a fake index.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from app.contradiction.config import TOPIC_PAIRING_THRESHOLD
from app.contradiction.pairing import find_candidate_chunk_pairs
from app.rag.config import EMBEDDINGS_PATH, METADATA_PATH, RELEVANCE_THRESHOLD


@pytest.fixture(scope="module")
def mapping() -> list[dict]:
    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    return metadata["mapping"]


@pytest.fixture(scope="module")
def embeddings() -> np.ndarray:
    return np.load(EMBEDDINGS_PATH)


def test_topic_pairing_threshold_is_stricter_than_phase8_retrieval_threshold():
    assert TOPIC_PAIRING_THRESHOLD > RELEVANCE_THRESHOLD


def test_candidate_pairs_are_never_within_the_same_document(mapping, embeddings):
    pairs = find_candidate_chunk_pairs(mapping, embeddings, threshold=TOPIC_PAIRING_THRESHOLD)
    assert pairs, "expected at least one real cross-document candidate pair at the documented threshold"
    for p in pairs:
        assert p.document_id_a != p.document_id_b


def test_candidate_pairs_meet_the_similarity_threshold(mapping, embeddings):
    pairs = find_candidate_chunk_pairs(mapping, embeddings, threshold=TOPIC_PAIRING_THRESHOLD)
    for p in pairs:
        assert p.similarity >= TOPIC_PAIRING_THRESHOLD


def test_candidate_pair_count_matches_documented_real_corpus_measurement(mapping, embeddings):
    # Measured directly from the real corpus (see docs/CONTRADICTION_DETECTION.md
    # "Topic-pairing threshold") -- locks in the number so a future change to
    # the embeddings/threshold is caught rather than silently drifting.
    pairs = find_candidate_chunk_pairs(mapping, embeddings, threshold=TOPIC_PAIRING_THRESHOLD)
    assert len(pairs) == 139


def test_a_stricter_threshold_yields_fewer_or_equal_pairs(mapping, embeddings):
    loose = find_candidate_chunk_pairs(mapping, embeddings, threshold=0.60)
    strict = find_candidate_chunk_pairs(mapping, embeddings, threshold=0.85)
    assert len(strict) <= len(loose)


def test_pairing_is_deterministic(mapping, embeddings):
    first = find_candidate_chunk_pairs(mapping, embeddings, threshold=TOPIC_PAIRING_THRESHOLD)
    second = find_candidate_chunk_pairs(mapping, embeddings, threshold=TOPIC_PAIRING_THRESHOLD)
    assert [(p.chunk_id_a, p.chunk_id_b, p.similarity) for p in first] == [
        (p.chunk_id_a, p.chunk_id_b, p.similarity) for p in second
    ]


def test_pairs_are_sorted_by_descending_similarity(mapping, embeddings):
    pairs = find_candidate_chunk_pairs(mapping, embeddings, threshold=TOPIC_PAIRING_THRESHOLD)
    similarities = [p.similarity for p in pairs]
    assert similarities == sorted(similarities, reverse=True)


def test_embeddings_mapping_length_mismatch_raises():
    with pytest.raises(ValueError):
        find_candidate_chunk_pairs([{"document_id": "X", "chunk_id": "a"}], np.zeros((2, 384), dtype="float32"))
