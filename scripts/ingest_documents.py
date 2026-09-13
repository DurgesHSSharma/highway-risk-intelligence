"""
Phase 7: reusable PDF ingestion pipeline (parsing, table-aware extraction,
OCR fallback, heading detection, deterministic chunking).

Reads data/documents/metadata.csv, verifies every catalogued document is
present under data/documents/raw/, extracts each page's text (native
PyMuPDF text, pdfplumber table fallback, or Tesseract OCR fallback,
depending on documented deterministic heuristics), and writes a
citation-ready chunk dataset to data/processed/document_chunks.csv.

This phase produces a chunk-level dataset only. No embeddings, vector
store, retrieval, or LLM integration is implemented here (see
docs/DOCUMENT_INGESTION.md).

Usage (from repo root):
    ./backend/.venv/Scripts/python.exe -m scripts.ingest_documents
"""

from __future__ import annotations

import argparse
import io
import re
import shutil
import statistics
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import pymupdf as fitz
import pdfplumber
import pytesseract
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_METADATA_PATH = REPO_ROOT / "data" / "documents" / "metadata.csv"
DEFAULT_RAW_DIR = REPO_ROOT / "data" / "documents" / "raw"
DEFAULT_OUTPUT_PATH = REPO_ROOT / "data" / "processed" / "document_chunks.csv"

# --- OCR trigger threshold -------------------------------------------------
# A page's native PyMuPDF text is judged unusable (and OCR is attempted)
# when its stripped length is below this many characters. Chosen because
# every page inspected in the real corpus was either clearly text-bearing
# (hundreds to thousands of characters) or entirely empty (0 characters,
# e.g. image-only cover pages / blank separator pages) -- there was no
# ambiguous middle ground, so a low, simple threshold is sufficient and
# avoids OCR-ing pages that already have perfectly usable native text.
MIN_NATIVE_TEXT_CHARS = 20

# --- OCR rendering ----------------------------------------------------------
OCR_DPI = 300

# --- OCR output quality flags ------------------------------------------------
# empty_ocr_output: OCR produced no usable text at all (e.g. a truly blank
#   page rendered as an image).
# suspicious_text: OCR produced text that looks garbled, detected by EITHER
#   of two signals: (a) a low ratio of alphabetic characters among all
#   non-whitespace characters (symbol/noise-heavy output), or (b) a high
#   ratio of 1-2 character whitespace-delimited tokens. Signal (b) was added
#   after manually inspecting every OCR page produced by the real corpus:
#   Tesseract misreading a grainy photo/decorative-graphic page (rather than
#   a genuine text region) characteristically produces many short garbled
#   fragments (e.g. "amt gh Tier t 4, Ok i F 8 Pe.") that are still
#   alphabetic-majority and therefore invisible to signal (a) alone, while
#   genuine short headings (e.g. "CHAPTER 6\nEXECUTION OF PROJECTS") stay
#   below the chosen threshold. Threshold picked empirically from that
#   inspection (garbled pages measured 0.45-0.75; genuine short headings
#   measured 0.0-0.40).
# low_ocr_quality: OCR produced some plausible text but very little of it --
#   too little to be confident the page's actual content was captured.
OCR_ALPHA_RATIO_THRESHOLD = 0.6
OCR_SHORT_TOKEN_RATIO_THRESHOLD = 0.4
OCR_MIN_MEANINGFUL_CHARS = 30

# --- Table-aware (pdfplumber) fallback heuristic ----------------------------
# pdfplumber is only attempted on a page when BOTH of the following hold:
#   1. PyMuPDF's own built-in table detector (page.find_tables()) reports at
#      least one table on the page -- a cheap, already-available signal that
#      costs nothing extra since PyMuPDF is already the primary extractor.
#   2. The native text extracted from that page shows a documented sign of
#      poor structural quality for tabular content: either a high density of
#      digit characters (numeric_density) or a high fraction of lines with
#      irregular internal spacing (irregular_spacing_ratio), both consistent
#      with PyMuPDF's reading-order text flattening a multi-column table
#      into misaligned runs of numbers and short labels.
# This keeps pdfplumber off the majority of pages (verified empirically:
# NHAI Annual Report 2022-23 has 73/144 pages with a PyMuPDF-detected table,
# but only 34/144 also show the poor-quality signal) and pdfplumber's own
# extracted table is only actually used if it yields a non-trivial table
# (>=2 rows and >=2 columns) -- never a blind substitution.
TABLE_NUMERIC_DENSITY_THRESHOLD = 0.12
TABLE_IRREGULAR_SPACING_THRESHOLD = 0.3
MIN_TABLE_ROWS = 2
MIN_TABLE_COLS = 2

# --- Heading / section detection --------------------------------------------
# Best-effort only: a line is treated as a heading candidate when its font
# size is at least this multiple of the page's median body-text font size,
# and it is short enough to plausibly be a heading rather than a paragraph.
HEADING_FONT_SIZE_RATIO = 1.3
HEADING_MAX_WORDS = 12
HEADING_MAX_CHARS = 80

# --- Chunking ----------------------------------------------------------------
# "Token" here is approximated as a whitespace-delimited word -- a
# deliberate simplification to avoid adding a model-specific tokenizer
# dependency in a phase with no embeddings/LLM involved. Target ~400
# words / ~50 words overlap, paragraph- then sentence-aware, per page (a
# chunk never spans two pages, which keeps every chunk's page-level
# provenance unambiguous).
CHUNK_TARGET_WORDS = 400
CHUNK_OVERLAP_WORDS = 50

CHUNK_COLUMNS = [
    "chunk_id",
    "document_id",
    "source_filename",
    "provenance_type",
    "page_number",
    "section_heading",
    "extraction_method",
    "extraction_quality_flag",
    "chunk_index",
    "chunk_word_count",
    "chunk_text",
]


class IngestionError(Exception):
    """Raised when the document corpus is in an inconsistent, unrecoverable state."""


def locate_tesseract() -> str | None:
    """Find the Tesseract binary: PATH first, then the common Windows install path."""
    found = shutil.which("tesseract")
    if found:
        return found
    windows_default = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    if windows_default.exists():
        return str(windows_default)
    return None


_TESSERACT_PATH = locate_tesseract()
TESSERACT_AVAILABLE = _TESSERACT_PATH is not None
if TESSERACT_AVAILABLE:
    pytesseract.pytesseract.tesseract_cmd = _TESSERACT_PATH


@dataclass
class PageStats:
    native_text_pages: int = 0
    pdfplumber_fallback_pages: int = 0
    ocr_pages: int = 0
    flagged_pages: int = 0
    pages_processed: int = 0


@dataclass
class DocumentResult:
    document_id: str
    pages_processed: int
    chunk_records: list[dict] = field(default_factory=list)
    stats: PageStats = field(default_factory=PageStats)


def load_metadata(metadata_path: Path = DEFAULT_METADATA_PATH) -> pd.DataFrame:
    if not metadata_path.exists():
        raise FileNotFoundError(f"Metadata manifest not found: {metadata_path}")
    return pd.read_csv(metadata_path, dtype=str, keep_default_na=False)


def verify_catalogued_documents(metadata_df: pd.DataFrame, raw_dir: Path = DEFAULT_RAW_DIR) -> list[dict]:
    """Return the rows that are catalogued as downloaded (non-blank local_filename),
    raising IngestionError if any such file is missing on disk. Rows with a
    blank local_filename are documents Phase 2 verified but never downloaded
    (e.g. size hygiene, or a source that blocked automated fetch) -- they are
    simply skipped, not an error.
    """
    available = []
    for row in metadata_df.to_dict("records"):
        local_filename = row.get("local_filename", "").strip()
        if not local_filename:
            continue
        expected_path = raw_dir / local_filename
        if not expected_path.exists():
            raise IngestionError(
                f"Catalogued document missing on disk: document_id={row['document_id']!r} "
                f"expects file {expected_path} (declared in metadata.csv local_filename column) "
                f"but it does not exist. The document is catalogued as downloaded but the local "
                f"file is missing -- refusing to silently skip it."
            )
        row["_resolved_path"] = expected_path
        available.append(row)
    return available


def analyze_text_quality(text: str) -> tuple[float, float]:
    """Return (numeric_density, irregular_spacing_ratio) for a page's native text."""
    non_ws = re.sub(r"\s", "", text)
    if not non_ws:
        return 0.0, 0.0
    numeric_density = sum(c.isdigit() for c in non_ws) / len(non_ws)
    lines = [line for line in text.split("\n") if line.strip()]
    if not lines:
        return numeric_density, 0.0
    irregular = sum(1 for line in lines if re.search(r"\S {3,}\S", line))
    return numeric_density, irregular / len(lines)


def should_attempt_pdfplumber(native_text: str, table_count: int) -> bool:
    if table_count == 0:
        return False
    numeric_density, irregular_spacing_ratio = analyze_text_quality(native_text)
    return (
        numeric_density > TABLE_NUMERIC_DENSITY_THRESHOLD
        or irregular_spacing_ratio > TABLE_IRREGULAR_SPACING_THRESHOLD
    )


def format_pdfplumber_tables(tables: list[list[list[str | None]]]) -> str:
    blocks = []
    for table in tables:
        rows = [" | ".join(cell.strip() if cell else "" for cell in row) for row in table]
        blocks.append("\n".join(rows))
    return "\n\n".join(blocks)


def extract_meaningful_pdfplumber_tables(pdfplumber_page: "pdfplumber.page.Page") -> str | None:
    tables = pdfplumber_page.extract_tables()
    meaningful = [t for t in tables if len(t) >= MIN_TABLE_ROWS and len(t[0] or []) >= MIN_TABLE_COLS]
    if not meaningful:
        return None
    return format_pdfplumber_tables(meaningful)


def classify_ocr_quality(text: str) -> str | None:
    stripped = text.strip()
    if not stripped:
        return "empty_ocr_output"
    non_ws = re.sub(r"\s", "", stripped)
    alpha_ratio = sum(c.isalpha() for c in non_ws) / len(non_ws) if non_ws else 0.0
    tokens = stripped.split()
    short_token_ratio = sum(1 for t in tokens if len(t) <= 2) / len(tokens) if tokens else 0.0
    if alpha_ratio < OCR_ALPHA_RATIO_THRESHOLD or short_token_ratio > OCR_SHORT_TOKEN_RATIO_THRESHOLD:
        return "suspicious_text"
    if len(stripped) < OCR_MIN_MEANINGFUL_CHARS:
        return "low_ocr_quality"
    return None


def ocr_page(fitz_page: "fitz.Page") -> str:
    if not TESSERACT_AVAILABLE:
        raise IngestionError(
            "OCR fallback was triggered but Tesseract is not installed/reachable. "
            "Install Tesseract (see docs/DOCUMENT_INGESTION.md) or ensure it is on PATH."
        )
    pix = fitz_page.get_pixmap(dpi=OCR_DPI)
    image = Image.open(io.BytesIO(pix.tobytes("png")))
    return pytesseract.image_to_string(image)


def detect_heading(fitz_page: "fitz.Page") -> str | None:
    """Best-effort, font-size-based heading detection. Returns None (not an
    invented value) when no reliable heading candidate is found on the page.
    """
    page_dict = fitz_page.get_text("dict")
    sizes: list[float] = []
    candidates: list[tuple[float, int, str]] = []
    order = 0
    for block in page_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            if not spans:
                continue
            text = "".join(s.get("text", "") for s in spans).strip()
            if not text:
                continue
            size = max(s.get("size", 0.0) for s in spans)
            sizes.append(size)
            candidates.append((size, order, text))
            order += 1
    if not sizes:
        return None
    median_size = statistics.median(sizes)
    threshold = median_size * HEADING_FONT_SIZE_RATIO
    heading_candidates = [
        (size, seq, text)
        for size, seq, text in candidates
        if size >= threshold and text and len(text) <= HEADING_MAX_CHARS and len(text.split()) <= HEADING_MAX_WORDS
    ]
    if not heading_candidates:
        return None
    heading_candidates.sort(key=lambda item: (-item[0], item[1]))
    return heading_candidates[0][2]


def normalize_paragraphs(text: str) -> list[str]:
    raw_paragraphs = re.split(r"\n\s*\n", text)
    paragraphs = []
    for raw in raw_paragraphs:
        collapsed = re.sub(r"\s*\n\s*", " ", raw).strip()
        collapsed = re.sub(r" {2,}", " ", collapsed)
        if collapsed:
            paragraphs.append(collapsed)
    return paragraphs


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")


def split_sentences(paragraph: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(paragraph) if s.strip()]


def chunk_page_text(
    text: str,
    target_words: int = CHUNK_TARGET_WORDS,
    overlap_words: int = CHUNK_OVERLAP_WORDS,
) -> list[str]:
    """Deterministic paragraph/sentence-aware chunking of a single page's text.
    Never merges text across pages. If a single sentence exceeds the target
    size on its own, it is safely split by word count as a last resort.
    """
    units: list[str] = []
    for paragraph in normalize_paragraphs(text):
        units.extend(split_sentences(paragraph))
    if not units:
        return []

    step = max(target_words - overlap_words, 1)
    chunks: list[str] = []
    current_words: list[str] = []
    for sentence in units:
        sentence_words = sentence.split()
        if len(sentence_words) > target_words:
            if current_words:
                chunks.append(" ".join(current_words))
                current_words = []
            for i in range(0, len(sentence_words), step):
                chunks.append(" ".join(sentence_words[i : i + target_words]))
            continue
        if current_words and len(current_words) + len(sentence_words) > target_words:
            chunks.append(" ".join(current_words))
            current_words = current_words[-overlap_words:] if overlap_words > 0 else []
        current_words.extend(sentence_words)
    if current_words:
        chunks.append(" ".join(current_words))
    return chunks


def make_chunk_id(document_id: str, page_number: int, chunk_index: int) -> str:
    return f"{document_id}_p{page_number:04d}_c{chunk_index:02d}"


def process_document(document_id: str, path: Path, provenance_type: str) -> DocumentResult:
    stats = PageStats()
    chunk_records: list[dict] = []
    source_filename = path.name

    fitz_doc = fitz.open(path)
    pdfplumber_doc = pdfplumber.open(path)
    try:
        for page_index in range(len(fitz_doc)):
            page_number = page_index + 1
            fitz_page = fitz_doc[page_index]
            native_text = fitz_page.get_text()

            extraction_method: str
            quality_flag: str | None = None
            final_text: str

            if len(native_text.strip()) >= MIN_NATIVE_TEXT_CHARS:
                extraction_method = "native_text"
                final_text = native_text
                table_count = len(fitz_page.find_tables().tables)
                if should_attempt_pdfplumber(native_text, table_count):
                    pb_page = pdfplumber_doc.pages[page_index]
                    table_text = extract_meaningful_pdfplumber_tables(pb_page)
                    if table_text:
                        extraction_method = "pdfplumber_table"
                        final_text = native_text.strip() + "\n\n[TABLE - pdfplumber extraction]\n" + table_text
                        stats.pdfplumber_fallback_pages += 1
                stats.native_text_pages += 1
            else:
                extraction_method = "ocr"
                final_text = ocr_page(fitz_page)
                quality_flag = classify_ocr_quality(final_text)
                stats.ocr_pages += 1
                if quality_flag:
                    stats.flagged_pages += 1

            heading = detect_heading(fitz_page)
            page_chunks = chunk_page_text(final_text)
            for chunk_index, chunk_text in enumerate(page_chunks):
                chunk_records.append(
                    {
                        "chunk_id": make_chunk_id(document_id, page_number, chunk_index),
                        "document_id": document_id,
                        "source_filename": source_filename,
                        "provenance_type": provenance_type,
                        "page_number": page_number,
                        "section_heading": heading or "",
                        "extraction_method": extraction_method,
                        "extraction_quality_flag": quality_flag or "",
                        "chunk_index": chunk_index,
                        "chunk_word_count": len(chunk_text.split()),
                        "chunk_text": chunk_text,
                    }
                )
            stats.pages_processed += 1
    finally:
        fitz_doc.close()
        pdfplumber_doc.close()

    return DocumentResult(
        document_id=document_id,
        pages_processed=stats.pages_processed,
        chunk_records=chunk_records,
        stats=stats,
    )


def run_ingestion(
    metadata_path: Path = DEFAULT_METADATA_PATH,
    raw_dir: Path = DEFAULT_RAW_DIR,
    output_path: Path = DEFAULT_OUTPUT_PATH,
) -> dict:
    metadata_df = load_metadata(metadata_path)
    available_docs = verify_catalogued_documents(metadata_df, raw_dir)

    all_chunk_records: list[dict] = []
    total_stats = PageStats()
    documents_processed = []

    for row in available_docs:
        result = process_document(row["document_id"], row["_resolved_path"], row["provenance_type"])
        all_chunk_records.extend(result.chunk_records)
        total_stats.native_text_pages += result.stats.native_text_pages
        total_stats.pdfplumber_fallback_pages += result.stats.pdfplumber_fallback_pages
        total_stats.ocr_pages += result.stats.ocr_pages
        total_stats.flagged_pages += result.stats.flagged_pages
        total_stats.pages_processed += result.stats.pages_processed
        documents_processed.append({"document_id": row["document_id"], "pages": result.pages_processed})

    output_path.parent.mkdir(parents=True, exist_ok=True)
    chunk_df = pd.DataFrame(all_chunk_records, columns=CHUNK_COLUMNS)
    chunk_df.to_csv(output_path, index=False)

    return {
        "documents_processed": documents_processed,
        "documents_catalogued_but_unavailable": len(metadata_df) - len(available_docs),
        "pages_processed": total_stats.pages_processed,
        "native_text_pages": total_stats.native_text_pages,
        "pdfplumber_fallback_pages": total_stats.pdfplumber_fallback_pages,
        "ocr_pages": total_stats.ocr_pages,
        "flagged_pages": total_stats.flagged_pages,
        "chunks_produced": len(all_chunk_records),
        "output_path": str(output_path),
        "tesseract_available": TESSERACT_AVAILABLE,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA_PATH)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()

    print(f"Reading metadata from {args.metadata}")
    print(f"Tesseract available: {TESSERACT_AVAILABLE}"
          + (f" ({_TESSERACT_PATH})" if TESSERACT_AVAILABLE else " -- OCR pages will raise IngestionError"))

    summary = run_ingestion(args.metadata, args.raw_dir, args.output)

    print("\n=== Phase 7 ingestion run summary ===")
    print(f"Documents processed: {len(summary['documents_processed'])}")
    for doc in summary["documents_processed"]:
        print(f"  - {doc['document_id']}: {doc['pages']} pages")
    print(f"Documents catalogued but not locally available (skipped, not an error): "
          f"{summary['documents_catalogued_but_unavailable']}")
    print(f"Pages processed: {summary['pages_processed']}")
    print(f"  native-text pages: {summary['native_text_pages']}")
    print(f"  pdfplumber fallback pages: {summary['pdfplumber_fallback_pages']}")
    print(f"  OCR-triggered pages: {summary['ocr_pages']}")
    print(f"  flagged low-quality pages: {summary['flagged_pages']}")
    print(f"Chunks produced: {summary['chunks_produced']}")
    print(f"Output written to: {summary['output_path']}")


if __name__ == "__main__":
    main()
