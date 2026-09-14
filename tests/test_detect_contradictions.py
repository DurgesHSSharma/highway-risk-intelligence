"""Phase 9 end-to-end detector tests, run at the repo root (mirrors the
existing tests/test_build_rag_index.py convention). Runs the real detector
against the real committed corpus and rag_index/ -- never a fake index or
synthetic substitute. The seeded synthetic fixture is exercised separately
in backend/tests/test_contradiction_comparison.py and is never mixed into
these real-corpus statistics.
"""

from __future__ import annotations

import scripts.detect_contradictions  # noqa: F401  (adds backend/ to sys.path as a side effect)

from app.contradiction.detector import run_detection  # noqa: E402


def test_real_corpus_detection_runs_end_to_end():
    summary = run_detection()
    assert summary.total_chunks_considered == 861
    assert summary.total_claims_extracted > 0
    assert summary.candidate_chunk_pairs > 0


def test_real_corpus_claim_type_counts_cover_all_four_types():
    summary = run_detection()
    for claim_type in ("currency", "percentage", "date", "count"):
        assert claim_type in summary.claim_type_counts
        assert summary.claim_type_counts[claim_type] > 0


def test_real_corpus_comparable_pairs_breakdown_is_internally_consistent():
    summary = run_detection()
    # comparable_claim_pairs_evaluated = flagged + contextual_difference + not_flagged
    # (not_flagged isn't tracked as its own field, but must be >= 0).
    implied_not_flagged = (
        summary.comparable_claim_pairs_evaluated - summary.flagged_count - summary.contextual_differences_excluded
    )
    assert implied_not_flagged >= 0
    assert summary.comparable_claim_pairs_evaluated >= summary.flagged_count


def test_real_corpus_flagged_count_is_honestly_reported_not_forced():
    # Locks in the actual measured real-corpus result (see
    # docs/CONTRADICTION_DETECTION.md "Real corpus results") so a future
    # change to extraction/tolerance is caught rather than silently
    # drifting. This is not a claim that 3 is "the right" number -- it is
    # what this detector, with its documented thresholds, actually finds.
    summary = run_detection()
    assert summary.flagged_count == 3


def test_real_corpus_detection_is_deterministic_across_independent_runs():
    first = run_detection()
    second = run_detection()

    assert first.total_claims_extracted == second.total_claims_extracted
    assert first.candidate_chunk_pairs == second.candidate_chunk_pairs
    assert first.flagged_count == second.flagged_count

    first_flag_ids = [f.flag_id for f in first.flags]
    second_flag_ids = [f.flag_id for f in second.flags]
    assert first_flag_ids == second_flag_ids

    first_keys = [(f.chunk_a, f.chunk_b, f.claim_type, f.raw_claim_a, f.raw_claim_b) for f in first.flags]
    second_keys = [(f.chunk_a, f.chunk_b, f.claim_type, f.raw_claim_a, f.raw_claim_b) for f in second.flags]
    assert first_keys == second_keys


def test_all_flags_are_cross_document():
    summary = run_detection()
    for flag in summary.flags:
        assert flag.document_a != flag.document_b


def test_all_flags_carry_hedged_non_absolute_descriptions():
    from app.contradiction.config import PROHIBITED_ABSOLUTE_PHRASES

    summary = run_detection()
    for flag in summary.flags:
        lowered = flag.description.lower()
        assert "potential inconsistency" in lowered
        for phrase in PROHIBITED_ABSOLUTE_PHRASES:
            assert phrase not in lowered


def test_flag_ids_are_unique_and_sequential():
    summary = run_detection()
    ids = [f.flag_id for f in summary.flags]
    assert ids == [f"FLAG-{i:04d}" for i in range(1, len(ids) + 1)]
