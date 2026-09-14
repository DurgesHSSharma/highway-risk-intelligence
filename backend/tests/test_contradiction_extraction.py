"""Phase 9 structured-claim extraction tests.

Real-corpus extraction tests use actual chunk text from the committed
`data/processed/document_chunks.csv` and verified extractor output (see
docs/CONTRADICTION_DETECTION.md) -- not invented examples. A few isolated
edge-case tests use small hand-built strings to pin down a single specific
regex behavior in isolation.
"""

from __future__ import annotations

import pandas as pd
import pytest

from app.contradiction.extraction import extract_claims_from_chunk, extract_claims_from_chunks
from app.config import REPO_ROOT

CHUNKS_CSV = REPO_ROOT / "data" / "processed" / "document_chunks.csv"


@pytest.fixture(scope="module")
def chunks_df() -> pd.DataFrame:
    return pd.read_csv(CHUNKS_CSV)


def _chunk_row(chunks_df: pd.DataFrame, chunk_id: str) -> pd.Series:
    match = chunks_df[chunks_df["chunk_id"] == chunk_id]
    assert len(match) == 1, f"expected exactly one row for {chunk_id}"
    return match.iloc[0]


def _extract(chunks_df: pd.DataFrame, chunk_id: str):
    row = _chunk_row(chunks_df, chunk_id)
    return extract_claims_from_chunk(row["chunk_id"], row["document_id"], int(row["page_number"]), row["chunk_text"])


# --- Real-corpus extraction: currency -----------------------------------


def test_real_corpus_currency_crore_with_backtick_rupee_symbol(chunks_df):
    claims = _extract(chunks_df, "DOC-001_p0011_c00")
    currency = [c for c in claims if c.claim_type == "currency"]
    values = {c.normalized_value for c in currency}
    assert 535000.0 in values, "expected the ₹5,35,000 crore Bharatmala Phase-I outlay figure"
    assert 846588.0 in values, "expected the ₹8,46,588 crore sanctioned-cost figure"
    for c in currency:
        assert c.normalized_unit == "crore"


def test_real_corpus_currency_lakh_crore_compound_unit(chunks_df):
    row = _chunk_row(chunks_df, "DOC-002_p0020_c00")
    claims = extract_claims_from_chunk(
        row["chunk_id"], row["document_id"], int(row["page_number"]), row["chunk_text"]
    )
    currency = [c for c in claims if c.claim_type == "currency"]
    # "5.35 lakh crores" -> 5.35 * 100,000 = 535,000 crore.
    assert any(abs(c.normalized_value - 535000.0) < 1e-6 for c in currency)


def test_real_corpus_currency_rs_prefix_with_indian_comma_grouping(chunks_df):
    claims = _extract(chunks_df, "DOC-004_p0001_c00")
    currency = [c for c in claims if c.claim_type == "currency"]
    values = {c.normalized_value for c in currency}
    assert 287333.0 in values  # "Rs 2,87,333 crore"
    assert 335173.0 in values  # "Rs 3,35,173 crore"


def test_currency_extraction_preserves_raw_text():
    claims = extract_claims_from_chunk("X_p0001_c00", "X", 1, "The outlay was ₹47,500 crore for the corridor.")
    currency = [c for c in claims if c.claim_type == "currency"]
    assert len(currency) == 1
    assert currency[0].raw_text == "₹47,500 crore"
    assert currency[0].normalized_value == 47500.0


def test_currency_bare_number_without_symbol_or_unit_is_not_extracted():
    claims = extract_claims_from_chunk("X_p0001_c00", "X", 1, "There were 26316 items counted in the survey.")
    assert not any(c.claim_type == "currency" for c in claims)


def test_currency_per_km_rate_is_excluded_not_mislabeled_as_total(chunks_df):
    # DOC-001 p.11 contains "` 15.37 crore/km" -- a per-km RATE, which must
    # never be extracted as an absolute currency total (see extraction.py's
    # _PER_KM_RATE_SUFFIX comment: comparing a rate to a total would be a
    # unit-conversion/aggregation-level category error).
    claims = _extract(chunks_df, "DOC-001_p0011_c00")
    assert not any(abs(float(c.normalized_value) - 15.37) < 1e-6 for c in claims if c.claim_type == "currency")


def test_currency_rs_does_not_match_inside_another_word():
    # Regression test: "Rs" is a valid currency symbol, but must not match
    # as a bare substring inside an unrelated word (e.g. the trailing "rs"
    # of "Corridors") -- see extraction.py's _CURRENCY_PATTERN comment.
    claims = extract_claims_from_chunk("X_p0001_c00", "X", 1, "4 National Corridors 5,000 2,601 2,576 0 25")
    currency = [c for c in claims if c.claim_type == "currency"]
    assert not any(c.normalized_value == 5000.0 for c in currency), (
        "the trailing 'rs' of 'Corridors' must not be read as the currency symbol 'Rs'"
    )


# --- Real-corpus extraction: percentage ----------------------------------


def test_real_corpus_percentage_per_cent_phrasing(chunks_df):
    claims = _extract(chunks_df, "DOC-001_p0011_c00")
    percentages = [c for c in claims if c.claim_type == "percentage"]
    assert any(abs(c.normalized_value - 75.62) < 1e-6 for c in percentages)
    assert all(c.normalized_unit == "percentage_points" for c in percentages)


def test_real_corpus_percentage_symbol_form(chunks_df):
    # Regression coverage for the "%\s" boundary bug (see extraction.py's
    # _PERCENTAGE_PATTERN comment) -- these are real "%"-symbol percentages
    # from DOC-004, not "per cent" phrasing.
    claims = _extract(chunks_df, "DOC-004_p0001_c00")
    percentages = {c.normalized_value for c in claims if c.claim_type == "percentage"}
    assert 2.0 in percentages
    assert 88.0 in percentages
    assert 2.4 in percentages


def test_percentage_extraction_handles_decimal_values():
    claims = extract_claims_from_chunk("X_p0001_c00", "X", 1, "The variance was 7.25 percent last quarter.")
    percentages = [c for c in claims if c.claim_type == "percentage"]
    assert len(percentages) == 1
    assert percentages[0].normalized_value == 7.25


# --- Real-corpus extraction: date -----------------------------------------


def test_real_corpus_date_day_month_year_phrasing(chunks_df):
    claims = _extract(chunks_df, "DOC-001_p0011_c00")
    dates = {c.normalized_value for c in claims if c.claim_type == "date"}
    assert "2023-03-31" in dates  # "31 March 2023"


def test_real_corpus_date_month_day_year_phrasing(chunks_df):
    claims = _extract(chunks_df, "DOC-004_p0001_c00")
    dates = {c.normalized_value for c in claims if c.claim_type == "date"}
    assert "2025-02-20" in dates  # "February 20, 2025"
    assert "2024-07-25" in dates  # "July 25, 2024"


def test_real_corpus_date_numeric_dd_mm_yyyy_phrasing(chunks_df):
    claims = _extract(chunks_df, "DOC-001_p0212_c00")
    dates = {c.normalized_value for c in claims if c.claim_type == "date"}
    assert "2018-05-09" in dates  # "09-05-2018"
    assert "2021-10-30" in dates  # "30-10-2021"


def test_date_extraction_preserves_raw_text():
    claims = extract_claims_from_chunk("X_p0001_c00", "X", 1, "Approved on 24 October 2017 by the committee.")
    dates = [c for c in claims if c.claim_type == "date"]
    assert len(dates) == 1
    assert dates[0].raw_text == "24 October 2017"
    assert dates[0].normalized_value == "2017-10-24"


# --- Real-corpus extraction: count -----------------------------------------


def test_real_corpus_count_projects_phrasing(chunks_df):
    claims = _extract(chunks_df, "DOC-001_p0011_c00")
    counts = [c for c in claims if c.claim_type == "count"]
    assert any(c.normalized_value == 58.0 and c.normalized_unit == "projects" for c in counts)


def test_count_not_extracted_for_arbitrary_numbers():
    # "Do NOT blindly treat every number as a count" -- a bare km length
    # must not be picked up as a count claim.
    claims = extract_claims_from_chunk("X_p0001_c00", "X", 1, "The corridor spans 26,316 km in total.")
    assert not any(c.claim_type == "count" for c in claims)


def test_count_requires_contextual_noun_immediately_after_number():
    claims = extract_claims_from_chunk("X_p0001_c00", "X", 1, "In total, 697 highway projects were delayed nationwide.")
    counts = [c for c in claims if c.claim_type == "count"]
    assert len(counts) == 1
    assert counts[0].normalized_value == 697.0
    assert counts[0].normalized_unit == "projects"


# --- Structural / metadata requirements ------------------------------------


def test_every_claim_has_required_fields(chunks_df):
    claims = _extract(chunks_df, "DOC-001_p0011_c00")
    assert claims, "expected at least one claim from this chunk"
    for c in claims:
        assert c.claim_id
        assert c.chunk_id == "DOC-001_p0011_c00"
        assert c.document_id == "DOC-001"
        assert c.page_number == 11
        assert c.claim_type in {"currency", "percentage", "date", "count"}
        assert c.raw_text
        assert c.normalized_value is not None
        assert c.short_context


def test_claim_ids_are_deterministic_and_unique_within_a_chunk(chunks_df):
    claims_first = _extract(chunks_df, "DOC-001_p0011_c00")
    claims_second = _extract(chunks_df, "DOC-001_p0011_c00")
    assert [c.claim_id for c in claims_first] == [c.claim_id for c in claims_second]
    ids = [c.claim_id for c in claims_first]
    assert len(ids) == len(set(ids))


def test_extract_claims_from_chunks_is_deterministic(chunks_df):
    included = chunks_df.head(50)
    first = extract_claims_from_chunks(included)
    second = extract_claims_from_chunks(included)
    assert [c.claim_id for c in first] == [c.claim_id for c in second]
    assert [c.normalized_value for c in first] == [c.normalized_value for c in second]


def test_extract_claims_from_chunk_handles_empty_text():
    assert extract_claims_from_chunk("X_p0001_c00", "X", 1, "") == []
    assert extract_claims_from_chunk("X_p0001_c00", "X", 1, "   ") == []
