"""Phase 9 tolerance/context-aware comparison tests, plus the seeded
synthetic fixture (tests/fixtures/contradiction_synthetic_fixture.json) and
the absolute-language safety checks required by the Phase 9 brief.
"""

from __future__ import annotations

import json

import pytest

from app.config import REPO_ROOT
from app.contradiction.comparison import compare_claims
from app.contradiction.config import PROHIBITED_ABSOLUTE_PHRASES
from app.contradiction.detector import _build_description
from app.contradiction.extraction import extract_claims_from_chunk

FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "contradiction_synthetic_fixture.json"


@pytest.fixture(scope="module")
def synthetic_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


# --- Tolerance logic ---------------------------------------------------


def _percentage_claim(chunk_id, doc_id, text):
    claims = extract_claims_from_chunk(chunk_id, doc_id, 1, text)
    return next(c for c in claims if c.claim_type == "percentage")


def _currency_claim(chunk_id, doc_id, text):
    claims = extract_claims_from_chunk(chunk_id, doc_id, 1, text)
    return next(c for c in claims if c.claim_type == "currency")


def test_clearly_divergent_percentages_are_flagged():
    a = _percentage_claim("A_p1_c0", "DOC-A", "Cost overrun for the Alpha Bypass project was 12% as audited.")
    b = _percentage_claim("B_p1_c0", "DOC-B", "Cost overrun for the Alpha Bypass project was 27% as audited.")
    outcome = compare_claims(a, b, set(), set())
    assert outcome is not None
    assert outcome.status == "flagged"
    assert outcome.difference == pytest.approx(15.0)


def test_clearly_consistent_percentages_are_not_flagged():
    a = _percentage_claim("A_p1_c0", "DOC-A", "Cost overrun for the Alpha Bypass project was 12% as audited.")
    b = _percentage_claim("B_p1_c0", "DOC-B", "Cost overrun for the Alpha Bypass project was 12% as audited.")
    outcome = compare_claims(a, b, set(), set())
    assert outcome is not None
    assert outcome.status == "not_flagged"


def test_trivial_percentage_rounding_difference_is_not_flagged():
    a = _percentage_claim("A_p1_c0", "DOC-A", "Cost overrun for the Alpha Bypass project was 75.62% as audited.")
    b = _percentage_claim("B_p1_c0", "DOC-B", "Cost overrun for the Alpha Bypass project was 75.7% as audited.")
    outcome = compare_claims(a, b, set(), set())
    assert outcome is not None
    assert outcome.status == "not_flagged", "a 0.08 point difference is within the 1.0pp tolerance"


def test_clearly_divergent_currency_is_flagged():
    a = _currency_claim("A_p1_c0", "DOC-A", "The Alpha Bypass project outlay was ₹3,85,000 crore.")
    b = _currency_claim("B_p1_c0", "DOC-B", "The Alpha Bypass project outlay was ₹5,35,000 crore.")
    outcome = compare_claims(a, b, set(), set())
    assert outcome is not None
    assert outcome.status == "flagged"


def test_trivial_currency_rounding_difference_is_not_flagged():
    a = _currency_claim("A_p1_c0", "DOC-A", "The Alpha Bypass project outlay was ₹5,35,000 crore.")
    b = _currency_claim("B_p1_c0", "DOC-B", "The Alpha Bypass project outlay was ₹5,36,000 crore.")
    outcome = compare_claims(a, b, set(), set())
    assert outcome is not None
    assert outcome.status == "not_flagged", "under 1% relative difference is within the 5% tolerance"


def test_incompatible_claim_types_are_not_comparable():
    pct = _percentage_claim("A_p1_c0", "DOC-A", "Cost overrun for the Alpha Bypass project was 12% as audited.")
    cur = _currency_claim("B_p1_c0", "DOC-B", "The Alpha Bypass project outlay was ₹5,35,000 crore.")
    assert compare_claims(pct, cur, set(), set()) is None


def test_unrelated_context_claims_are_not_comparable():
    a = _percentage_claim("A_p1_c0", "DOC-A", "Cost overrun for the Alpha Bypass project was 12% as audited.")
    b = _percentage_claim("B_p1_c0", "DOC-B", "Literacy rate in the district improved to 12% this year.")
    assert compare_claims(a, b, set(), set()) is None, (
        "two unrelated 12% figures with no shared vocabulary must not be treated as the same named fact"
    )


# --- Context-aware exclusion --------------------------------------------


def test_planned_vs_actual_wording_is_a_contextual_difference_not_flagged():
    a = _currency_claim("A_p1_c0", "DOC-A", "Planned outlay for Alpha Bypass was ₹5,35,000 crore.")
    b = _currency_claim("B_p1_c0", "DOC-B", "Actual cost for Alpha Bypass was ₹6,90,000 crore.")
    outcome = compare_claims(a, b, set(), set())
    assert outcome is not None
    assert outcome.status == "contextual_difference"
    assert outcome.reason == "planned_vs_actual_wording"


def test_differing_reporting_cutoff_dates_is_a_contextual_difference_not_flagged():
    a = _currency_claim("A_p1_c0", "DOC-A", "As of 31 March 2023, the Alpha Bypass project cost was ₹5,35,000 crore.")
    b = _currency_claim(
        "B_p1_c0", "DOC-B", "As of 31 December 2024, the Alpha Bypass project cost was ₹5,50,000 crore."
    )
    dates_a = {"2023-03-31"}
    dates_b = {"2024-12-31"}
    outcome = compare_claims(a, b, dates_a, dates_b)
    assert outcome is not None
    assert outcome.status == "contextual_difference"
    assert outcome.reason == "different_reporting_cutoff_dates"


def test_same_reporting_date_does_not_trigger_contextual_exclusion():
    a = _currency_claim("A_p1_c0", "DOC-A", "As of 31 March 2023, the Alpha Bypass project cost was ₹5,35,000 crore.")
    b = _currency_claim("B_p1_c0", "DOC-B", "As of 31 March 2023, the Alpha Bypass project cost was ₹6,90,000 crore.")
    dates_a = {"2023-03-31"}
    dates_b = {"2023-03-31"}
    outcome = compare_claims(a, b, dates_a, dates_b)
    assert outcome is not None
    assert outcome.status == "flagged"


# --- Seeded synthetic fixture (section 13) -------------------------------


def test_synthetic_fixture_is_not_part_of_the_real_corpus(synthetic_fixture):
    # The fixture's document_ids must never collide with real catalogued
    # documents (DOC-001..DOC-004/006) -- see data/documents/metadata.csv.
    assert synthetic_fixture["chunk_a"]["document_id"].startswith("SYN-")
    assert synthetic_fixture["chunk_b"]["document_id"].startswith("SYN-")


def test_synthetic_fixture_is_correctly_detected_as_a_potential_inconsistency(synthetic_fixture):
    chunk_a, chunk_b = synthetic_fixture["chunk_a"], synthetic_fixture["chunk_b"]
    claims_a = extract_claims_from_chunk(chunk_a["chunk_id"], chunk_a["document_id"], chunk_a["page_number"], chunk_a["text"])
    claims_b = extract_claims_from_chunk(chunk_b["chunk_id"], chunk_b["document_id"], chunk_b["page_number"], chunk_b["text"])

    pct_a = next(c for c in claims_a if c.claim_type == synthetic_fixture["expected_claim_type"])
    pct_b = next(c for c in claims_b if c.claim_type == synthetic_fixture["expected_claim_type"])

    assert pct_a.normalized_value == synthetic_fixture["expected_normalized_value_a"]
    assert pct_b.normalized_value == synthetic_fixture["expected_normalized_value_b"]

    outcome = compare_claims(pct_a, pct_b, set(), set())
    assert outcome is not None
    assert outcome.status == synthetic_fixture["expected_outcome_status"]
    assert outcome.difference == pytest.approx(synthetic_fixture["expected_absolute_difference"])


def test_synthetic_fixture_document_ids_never_appear_in_real_metadata():
    import csv

    metadata_path = REPO_ROOT / "data" / "documents" / "metadata.csv"
    with open(metadata_path, encoding="utf-8") as f:
        real_document_ids = {row["document_id"] for row in csv.DictReader(f)}
    assert "SYN-001" not in real_document_ids
    assert "SYN-002" not in real_document_ids


# --- Absolute-language safety (section 11) --------------------------------


def test_flag_description_uses_hedged_language():
    desc = _build_description("DOC-001", 11, "DOC-002", 20, "currency")
    lowered = desc.lower()
    assert "potential inconsistency" in lowered
    assert "requiring verification" in lowered


@pytest.mark.parametrize("claim_type", ["currency", "percentage", "date", "count"])
def test_flag_description_never_contains_prohibited_absolute_language(claim_type):
    desc = _build_description("DOC-001", 11, "DOC-002", 20, claim_type)
    lowered = desc.lower()
    for phrase in PROHIBITED_ABSOLUTE_PHRASES:
        assert phrase not in lowered, f"prohibited absolute phrase {phrase!r} found in: {desc!r}"


def test_prohibited_phrase_list_is_actually_enforced():
    # If the description builder ever regresses to using banned wording, it
    # must raise rather than silently emit unsafe output.
    from app.contradiction import detector as detector_module

    original = detector_module.PROHIBITED_ABSOLUTE_PHRASES
    try:
        detector_module.PROHIBITED_ABSOLUTE_PHRASES = ("definitive finding",)
        with pytest.raises(RuntimeError):
            _build_description("DOC-001", 11, "DOC-002", 20, "currency")
    finally:
        detector_module.PROHIBITED_ABSOLUTE_PHRASES = original
