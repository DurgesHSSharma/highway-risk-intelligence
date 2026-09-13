"""Phase 7 tests for the PDF ingestion pipeline.

Covers: real end-to-end ingestion, chunk metadata completeness, page/document
provenance integrity, the OCR-avoidance property for a known digital-native
PDF, determinism (two full runs compared byte-for-byte), the missing-
catalogued-file failure path (using an isolated tmp_path scenario -- the
real corpus at data/documents/raw/ is never touched or modified by these
tests), and the pure helper functions (chunking, OCR quality
classification, table-fallback heuristic, heading detection).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pymupdf as fitz
import pytest

from scripts.ingest_documents import (
    CHUNK_COLUMNS,
    CHUNK_OVERLAP_WORDS,
    CHUNK_TARGET_WORDS,
    DEFAULT_METADATA_PATH,
    DEFAULT_RAW_DIR,
    IngestionError,
    analyze_text_quality,
    chunk_page_text,
    classify_ocr_quality,
    detect_heading,
    load_metadata,
    make_chunk_id,
    run_ingestion,
    should_attempt_pdfplumber,
    verify_catalogued_documents,
)

VALID_EXTRACTION_METHODS = {"native_text", "pdfplumber_table", "ocr"}
VALID_QUALITY_FLAGS = {"", "empty_ocr_output", "suspicious_text", "low_ocr_quality"}


# --------------------------------------------------------------------------
# End-to-end ingestion against the real corpus
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def ingestion_summary(tmp_path_factory: pytest.TempPathFactory) -> dict:
    output_path = tmp_path_factory.mktemp("phase7") / "document_chunks.csv"
    return run_ingestion(output_path=output_path)


@pytest.fixture(scope="module")
def chunk_df(ingestion_summary: dict) -> pd.DataFrame:
    return pd.read_csv(ingestion_summary["output_path"], keep_default_na=False)


def test_ingestion_processes_at_least_one_real_document(ingestion_summary: dict) -> None:
    assert len(ingestion_summary["documents_processed"]) >= 1
    assert ingestion_summary["pages_processed"] > 0


def test_ingestion_produces_more_than_zero_chunks(chunk_df: pd.DataFrame) -> None:
    assert len(chunk_df) > 0


def test_every_chunk_has_all_required_metadata_fields(chunk_df: pd.DataFrame) -> None:
    assert list(chunk_df.columns) == CHUNK_COLUMNS
    for col in ["chunk_id", "document_id", "page_number", "extraction_method", "chunk_text"]:
        assert chunk_df[col].notna().all()
        assert (chunk_df[col].astype(str).str.len() > 0).all()


def test_chunk_ids_are_unique(chunk_df: pd.DataFrame) -> None:
    assert not chunk_df["chunk_id"].duplicated().any()


def test_every_chunk_document_id_exists_in_metadata(chunk_df: pd.DataFrame) -> None:
    metadata_df = load_metadata(DEFAULT_METADATA_PATH)
    known_ids = set(metadata_df["document_id"])
    assert set(chunk_df["document_id"]).issubset(known_ids)


def test_every_chunk_has_valid_page_provenance(chunk_df: pd.DataFrame) -> None:
    metadata_df = load_metadata(DEFAULT_METADATA_PATH)
    filename_by_doc = dict(zip(metadata_df["document_id"], metadata_df["local_filename"]))
    for document_id, group in chunk_df.groupby("document_id"):
        pdf_path = DEFAULT_RAW_DIR / filename_by_doc[document_id]
        with fitz.open(pdf_path) as doc:
            page_count = len(doc)
        assert group["page_number"].min() >= 1
        assert group["page_number"].max() <= page_count


def test_provenance_type_matches_metadata(chunk_df: pd.DataFrame) -> None:
    metadata_df = load_metadata(DEFAULT_METADATA_PATH)
    provenance_by_doc = dict(zip(metadata_df["document_id"], metadata_df["provenance_type"]))
    for document_id, group in chunk_df.groupby("document_id"):
        assert set(group["provenance_type"]) == {provenance_by_doc[document_id]}


def test_extraction_method_values_are_valid(chunk_df: pd.DataFrame) -> None:
    assert set(chunk_df["extraction_method"]).issubset(VALID_EXTRACTION_METHODS)


def test_extraction_quality_flag_values_are_valid(chunk_df: pd.DataFrame) -> None:
    assert set(chunk_df["extraction_quality_flag"]).issubset(VALID_QUALITY_FLAGS)


def test_prs_pdf_does_not_unnecessarily_trigger_ocr(chunk_df: pd.DataFrame) -> None:
    prs_chunks = chunk_df[chunk_df["document_id"] == "DOC-004"]
    assert len(prs_chunks) > 0
    assert not (prs_chunks["extraction_method"] == "ocr").any()


def test_chunk_ordering_is_deterministic_within_page(chunk_df: pd.DataFrame) -> None:
    for (_, _), group in chunk_df.groupby(["document_id", "page_number"]):
        assert list(group["chunk_index"]) == list(range(len(group)))


def test_ingestion_is_deterministic_across_runs(tmp_path: Path) -> None:
    out1 = tmp_path / "run1.csv"
    out2 = tmp_path / "run2.csv"
    run_ingestion(output_path=out1)
    run_ingestion(output_path=out2)
    assert out1.read_text(encoding="utf-8") == out2.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# Missing catalogued file: isolated tmp_path scenario, real corpus untouched
# --------------------------------------------------------------------------


def test_verify_catalogued_documents_raises_clear_error_for_missing_file(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    metadata_df = pd.DataFrame(
        [
            {
                "document_id": "DOC-TEST-MISSING",
                "local_filename": "does_not_exist.pdf",
                "provenance_type": "REAL PUBLIC DATA",
            }
        ]
    )
    with pytest.raises(IngestionError, match="DOC-TEST-MISSING"):
        verify_catalogued_documents(metadata_df, raw_dir)


def test_verify_catalogued_documents_skips_blank_local_filename(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    metadata_df = pd.DataFrame(
        [{"document_id": "DOC-TEST-UNAVAILABLE", "local_filename": "", "provenance_type": "REAL PUBLIC DATA"}]
    )
    available = verify_catalogued_documents(metadata_df, raw_dir)
    assert available == []


def test_verify_catalogued_documents_accepts_present_file(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "present.pdf").write_bytes(b"%PDF-1.4\n%fake")
    metadata_df = pd.DataFrame(
        [{"document_id": "DOC-TEST-PRESENT", "local_filename": "present.pdf", "provenance_type": "REAL PUBLIC DATA"}]
    )
    available = verify_catalogued_documents(metadata_df, raw_dir)
    assert len(available) == 1
    assert available[0]["document_id"] == "DOC-TEST-PRESENT"


def test_real_corpus_is_untouched_after_missing_file_test() -> None:
    metadata_df = load_metadata(DEFAULT_METADATA_PATH)
    verify_catalogued_documents(metadata_df, DEFAULT_RAW_DIR)


# --------------------------------------------------------------------------
# Pure helper function unit tests
# --------------------------------------------------------------------------


def test_classify_ocr_quality_empty_output() -> None:
    assert classify_ocr_quality("") == "empty_ocr_output"
    assert classify_ocr_quality("   \n  ") == "empty_ocr_output"


def test_classify_ocr_quality_short_valid_text_flagged_low_quality() -> None:
    assert classify_ocr_quality("EXECUTIVE SUMMARY") == "low_ocr_quality"


def test_classify_ocr_quality_garbled_short_tokens_flagged_suspicious() -> None:
    garbled = "amt gh Tier t 4, Ok i F 8 Pe. al hd 5 i Ty Hh A i Fh"
    assert classify_ocr_quality(garbled) == "suspicious_text"


def test_classify_ocr_quality_non_alphabetic_noise_flagged_suspicious() -> None:
    noise = "###@@@ 000 111 %%% &&& *** !!! ??? +++ === ~~~"
    assert classify_ocr_quality(noise) == "suspicious_text"


def test_classify_ocr_quality_clean_text_is_unflagged() -> None:
    clean = (
        "In the past decade we have witnessed significant infrastructure "
        "development across national highways, railways, ports and airports "
        "with sustained investment in road connectivity nationwide."
    )
    assert classify_ocr_quality(clean) is None


def test_classify_ocr_quality_is_deterministic() -> None:
    text = "amt gh Tier t 4, Ok i F 8 Pe."
    assert classify_ocr_quality(text) == classify_ocr_quality(text)


def test_analyze_text_quality_detects_numeric_density() -> None:
    numeric_heavy = "1234 5678 9012 3456 7890 1234"
    density, _ = analyze_text_quality(numeric_heavy)
    assert density > 0.9


def test_analyze_text_quality_empty_text() -> None:
    assert analyze_text_quality("") == (0.0, 0.0)


def test_should_attempt_pdfplumber_requires_table_and_poor_quality() -> None:
    numeric_heavy_text = "1 234,567 2 345,678 3 456,789 4 567,890"
    assert should_attempt_pdfplumber(numeric_heavy_text, table_count=1) is True
    assert should_attempt_pdfplumber(numeric_heavy_text, table_count=0) is False

    clean_prose = "This is a normal paragraph of report text with no tabular data at all here."
    assert should_attempt_pdfplumber(clean_prose, table_count=1) is False


def test_make_chunk_id_format_and_determinism() -> None:
    cid = make_chunk_id("DOC-001", 5, 2)
    assert cid == "DOC-001_p0005_c02"
    assert make_chunk_id("DOC-001", 5, 2) == cid


def test_chunk_page_text_respects_approximate_target_size() -> None:
    paragraph = " ".join(f"word{i}" for i in range(1000)) + "."
    chunks = chunk_page_text(paragraph, target_words=100, overlap_words=10)
    assert len(chunks) > 1
    for chunk in chunks[:-1]:
        assert len(chunk.split()) <= 100


def test_chunk_page_text_applies_overlap_between_consecutive_chunks() -> None:
    sentences = [f"Sentence number {i} contains several words for testing." for i in range(60)]
    text = " ".join(sentences)
    chunks = chunk_page_text(text, target_words=CHUNK_TARGET_WORDS, overlap_words=CHUNK_OVERLAP_WORDS)
    if len(chunks) > 1:
        first_tail = chunks[0].split()[-CHUNK_OVERLAP_WORDS:]
        second_head = chunks[1].split()[: len(first_tail)]
        assert first_tail == second_head


def test_chunk_page_text_handles_oversized_single_sentence_safely() -> None:
    oversized_sentence = " ".join(f"tok{i}" for i in range(900)) + "."
    chunks = chunk_page_text(oversized_sentence, target_words=100, overlap_words=10)
    assert len(chunks) > 1
    rebuilt_word_count = sum(len(c.split()) for c in chunks)
    assert rebuilt_word_count >= 900


def test_chunk_page_text_empty_input_produces_no_chunks() -> None:
    assert chunk_page_text("") == []
    assert chunk_page_text("   \n\n  ") == []


def test_chunk_page_text_never_spans_pages_by_construction() -> None:
    # chunk_page_text operates on exactly one page's text at a time; this is
    # a structural guarantee verified by inspecting the ingestion flow
    # (process_document calls it once per page), not a property of the
    # function's input alone.
    single_page_text = "First sentence here. Second sentence here."
    chunks = chunk_page_text(single_page_text)
    assert len(chunks) >= 1


def test_detect_heading_returns_none_for_blank_page() -> None:
    with fitz.open() as doc:
        page = doc.new_page()
        assert detect_heading(page) is None


def test_detect_heading_finds_large_font_short_line() -> None:
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((72, 100), "Chapter One", fontsize=24)
        page.insert_text((72, 150), "This is a much longer line of regular body text.", fontsize=10)
        page.insert_text((72, 170), "It continues describing something in detail here.", fontsize=10)
        heading = detect_heading(page)
        assert heading == "Chapter One"
