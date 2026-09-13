# Document Ingestion Pipeline (Phase 7)

## 1. Purpose

Phase 7 builds a reusable PDF ingestion pipeline that turns the real public
government/infrastructure PDFs catalogued in
[data/documents/metadata.csv](../data/documents/metadata.csv) into a
citation-ready, chunk-level dataset:

```
PDF -> extracted text -> OCR fallback where necessary -> metadata -> deterministic chunks
```

**This phase is not the retrieval system.** Nothing here queries, embeds,
indexes, or searches the chunks -- it only produces
[data/processed/document_chunks.csv](../data/processed/document_chunks.csv)
as a clean, reusable dataset for a future phase. No embeddings, vector
database, FAISS, semantic/hybrid search, reranking, RAG, LLM
answering/summarization, contradiction detection, or what-if simulation is
implemented in this phase.

## 2. Real documents processed

Phase 7 processes every document in `metadata.csv` that has a local file
present under `data/documents/raw/`. As of this phase's run, that is 4 of
the 6 catalogued real public documents:

| document_id | Title | Pages | Downloaded |
|---|---|---|---|
| DOC-001 | CAG Performance Audit, Bharatmala Pariyojana Phase I | 264 | Phase 7 |
| DOC-002 | NHAI Annual Report 2022-23 | 144 | Phase 7 |
| DOC-003 | MoRTH Annual Report 2024-25 | 144 | Phase 7 |
| DOC-004 | PRS Legislative Research DFG 2025-26 Analysis | 13 | Phase 2 |

DOC-005 and DOC-006 (two PIB press releases) remain catalogued but not
locally available -- see section 3.

## 3. Corpus expansion (Phase 7)

Phase 2 had verified 6 real public documents via HTTP but only downloaded
one (DOC-004, 785 KB) to keep the repository lightweight. Per the Phase 7
brief, downloading the remaining verified documents was attempted honestly:

**Attempted: 5** (DOC-001, DOC-002, DOC-003, DOC-005, DOC-006)

**Succeeded: 3**

- DOC-001 (CAG audit, 8,105,572 bytes) -- downloaded, byte-exact match to
  the HTTP `Content-Length`, verified as a genuine PDF via its `%PDF-1.7`
  magic bytes.
- DOC-002 (NHAI Annual Report, 7,701,522 bytes) -- downloaded, byte-exact
  match, verified `%PDF-1.3` magic bytes.
- DOC-003 (MoRTH Annual Report, 19,474,671 bytes) -- downloaded, byte-exact
  match, verified `%PDF-1.6` magic bytes.

All three were re-verified live (HTTP HEAD, `Content-Length` compared
before download) on 2026-09-13 before downloading, using the same
verification standard as Phase 2.

**Failed: 2**

- DOC-005 (PIB Year End Review 2024) -- HTTP 401 Unauthorized, both with
  the original request and a retry using a browser-like `User-Agent`
  string. Consistent with PIB's known bot-protection, not a broken link.
- DOC-006 (PIB land-acquisition press release) -- same HTTP 401 result for
  the same reason.

Additionally, both PIB URLs are HTML press-release pages
(`PressReleseDetailm.aspx`, `Pressreleaseshare.aspx`), not direct PDF
links -- so even a successful fetch would not have produced an
ingestible PDF document. This is disclosed in `metadata.csv` and here
rather than silently treated as a PDF gap.

No URL or document was invented. No replacement document was substituted
for a failed download. `metadata.csv` and
[data/README.md](../data/README.md) were updated to reflect exactly what
was downloaded, when, and how it was verified -- see the
`verification_method` / `verification_date` columns.

## 4. Provenance convention

This phase follows the existing convention (see `data/README.md`,
section "Provenance labels used throughout this project"):

- **REAL PUBLIC DATA** -- the four source PDFs and the `metadata.csv`
  manifest itself.
- **DERIVED DATA** -- `data/processed/document_chunks.csv` is derived
  entirely from the four real PDFs above; it is not itself a primary
  document and must never be presented as an original government
  publication. Every chunk carries `provenance_type` copied from its
  source document's `metadata.csv` row (`REAL PUBLIC DATA` for all chunks
  in this run), so the label travels with the data, not just the docs.

## 5. PyMuPDF extraction (primary)

Every page is opened with PyMuPDF (`pymupdf`, imported as `fitz`) and its
native text extracted via `page.get_text()`. For every page, the pipeline
records: `document_id`, `page_number` (1-based), `extraction_method`,
detected `section_heading` (best-effort), and the extracted text before
chunking.

## 6. pdfplumber table-aware fallback

**Heuristic (deterministic, two conditions, both must hold):**

1. PyMuPDF's own built-in table detector, `page.find_tables()`, reports at
   least one table on the page. This is a free signal -- no extra library
   call needed to get it, since PyMuPDF is already the primary extractor.
2. The page's native text shows a documented sign of poor structural
   quality for tabular content:
   - `numeric_density` (fraction of non-whitespace characters that are
     digits) `> 0.12`, OR
   - `irregular_spacing_ratio` (fraction of non-empty lines containing 3+
     consecutive interior spaces -- a sign of collapsed table columns)
     `> 0.3`.

Only when both conditions hold does the pipeline call
`pdfplumber_page.extract_tables()`. Its output is used only if it yields
at least one *meaningful* table (>=2 rows and >=2 columns) -- never a
blind substitution. When used, the pdfplumber table (formatted as
`cell | cell | cell` rows) is **appended** to the original native text
(not a replacement), so no narrative text is lost; `extraction_method` is
set to `pdfplumber_table`.

**Why this heuristic, not "run pdfplumber on every table-flagged page":**
empirically, on the NHAI Annual Report, PyMuPDF's table detector alone
flags 73 of 144 pages, but only 34 of those also show the poor-quality
signal above -- meaning most PyMuPDF-detected tables are already rendered
adequately by native text and do not need a second extraction pass.

**Verified improvement example** (NHAI Annual Report, page 21): native
PyMuPDF text flattens a multi-column funding table into a jumbled run of
repeated column headers ("Length (km) / Total Capital Cost..." repeated
out of order); pdfplumber's `extract_tables()` recovers the same data as
clean rows, e.g. `['1', 'Delhi - Mumbai EXP', '1,368', '98,819', ...]`.

**Limitation, disclosed honestly:** this does not claim perfect table
reconstruction. Complex nested/merged-cell tables may still lose some
structure in pdfplumber's own row/column extraction; this was not
independently audited cell-by-cell across all 120 fallback pages.

## 7. Heading / section detection (best-effort)

Font-size based only, deliberately simple per the brief's "does not need
to be perfect" instruction. For each page, PyMuPDF's `"dict"` text mode
gives per-line font sizes; a line is a heading candidate if its font size
is `>= 1.3x` the page's median body-text font size, and the line is short
(`<= 12` words, `<= 80` characters). The largest, earliest such candidate
on the page is used; if none qualifies, `section_heading` is left blank
(never invented).

**Disclosed limitation found during the real run:** one page in the CAG
report (page 25) yields a heading of `"5HSRUW1RRI"` instead of the
expected `"Report No.19..."` running header. Manual inspection confirmed
this is a literal PyMuPDF-decoded string from that specific PDF's embedded
font encoding on that occurrence, not a bug in the heading-detection logic
-- other occurrences of the same running header on nearby pages decode
correctly. Best-effort heading detection can occasionally surface a raw
font-encoding artifact like this; it is not filtered out, since doing so
would require guessing which decoded strings are "real" without a
reliable signal.

Across the real corpus, 277 of 861 chunks (~32%) carry a non-blank
`section_heading`; the rest are left blank as documented.

## 8. OCR fallback

**Trigger threshold:** OCR is attempted on a page only when its native
PyMuPDF text, stripped of whitespace, is under **20 characters**
(`MIN_NATIVE_TEXT_CHARS`). This threshold was chosen after inspecting
every page in the real corpus: pages were either clearly text-bearing
(hundreds to thousands of characters) or completely empty (0 characters --
e.g. image-only cover pages or blank section-separator pages). There was
no ambiguous middle ground in this corpus, so a low, simple threshold is
sufficient.

**OCR process:** the page is rendered to a PNG image via
`page.get_pixmap(dpi=300)`, then passed to `pytesseract.image_to_string()`.
`extraction_method` is set to `"ocr"`.

**Quality flags (deterministic):**

- `empty_ocr_output` -- OCR produced no text at all after stripping
  whitespace.
- `suspicious_text` -- triggered by **either** of two signals:
  (a) the ratio of alphabetic characters among non-whitespace characters
  is below 0.6 (symbol/noise-heavy output), or
  (b) the ratio of 1-2 character whitespace-delimited tokens exceeds 0.4.
  Signal (b) was added after manually inspecting every OCR page produced
  by the real corpus: several image/decorative-photo pages produced
  alphabetic-majority but genuinely garbled text (e.g.
  `"amt gh Tier t 4, Ok i F 8 Pe."`), which signal (a) alone could not
  catch since the garbled characters are still letters. The short-token
  threshold (0.4) was set from that inspection: garbled pages measured
  0.45-0.75 on this ratio, while genuine short headings (e.g.
  `"CHAPTER 6\nEXECUTION OF PROJECTS"`) measured 0.0-0.40.
- `low_ocr_quality` -- OCR produced plausible-looking text, but under 30
  characters total (e.g. a lone chapter title on an otherwise blank page).
- No flag -- OCR output passed both checks and is at least 30 characters.

Pages that produce zero OCR text (`empty_ocr_output`) generate zero chunks
for that page (there is no text to chunk); they are still counted in the
run summary's "flagged low-quality pages" total, even though they leave no
row in the final chunk CSV.

**OCR actually exercised on real scanned content:** yes. Tesseract was not
pre-installed on this machine; it was installed via `winget` (the free,
open-source UB-Mannheim build, `Tesseract-OCR 5.4.0`) as part of this
phase and verified with `tesseract --version`. It was then run against 32
real pages across the corpus that fell below the native-text threshold --
mostly cover pages, section-separator pages, and decorative photo pages in
the CAG and MoRTH reports. Example real result: MoRTH Annual Report 2024-25
page 1 (a cover page with zero native text layer) OCRs cleanly to
`"GOVERNMENT OF INDIA\nMINISTRY OF ROAD TRANSPORT\nAND HIGHWAYS, NEW
DELHI"`. OCR accuracy is not quantified as a percentage (no ground-truth
transcription exists to measure against) -- only the deterministic quality
flags above are reported.

## 9. Chunking

**Token definition (approximation, disclosed):** a "token" is approximated
as a whitespace-delimited word. This avoids adding a model-specific
tokenizer dependency in a phase with no embeddings/LLM involved, at the
cost of not matching a real subword tokenizer's count exactly.

- **Target chunk size:** ~400 words.
- **Overlap:** ~50 words between consecutive chunks on the same page.
- **Boundary strategy:** paragraph boundaries first (native text is split
  on blank-line gaps, with wrapped lines within a paragraph rejoined),
  then sentence boundaries (a deterministic regex sentence splitter) within
  each paragraph. Sentences are greedily packed into a chunk until adding
  the next sentence would exceed the 400-word target; the next chunk then
  starts with the last ~50 words of the previous chunk (the overlap) before
  continuing. A single sentence that itself exceeds the target size is
  safely split by raw word count as a last resort (rare in practice).
- **A chunk never spans two pages.** Every chunk belongs to exactly one
  `(document_id, page_number)`, so page-level citation provenance is never
  ambiguous or lost during chunking.
- Real chunk sizes: median 282 words, 25th/75th percentile 152/377 words,
  matching the intended range (some chunks are shorter because they are
  the last, non-overlapping remainder of a short page).

## 10. Required chunk metadata

Every row in `document_chunks.csv` has:

| Column | Description |
|---|---|
| `chunk_id` | Deterministic: `{document_id}_p{page_number:04d}_c{chunk_index:02d}` |
| `document_id` | Matches a row in `metadata.csv` |
| `source_filename` | The local PDF filename |
| `provenance_type` | Copied from the source document's `metadata.csv` row |
| `page_number` | 1-based page number within the source PDF |
| `section_heading` | Best-effort detected heading, or blank |
| `extraction_method` | `native_text` \| `pdfplumber_table` \| `ocr` |
| `extraction_quality_flag` | Blank, or one of the OCR flags in section 8 |
| `chunk_index` | 0-based index of this chunk within its page |
| `chunk_word_count` | Word count of `chunk_text` (whitespace-split) |
| `chunk_text` | The chunk's text |

`page_range` was considered but not added: since chunks never span pages,
`page_number` alone is sufficient and an identical `page_range` column
would be redundant.

## 11. Determinism strategy

No random IDs, no timestamps, no UUIDs anywhere in the chunk dataset.
`chunk_id` is a pure function of `document_id`, `page_number`, and
`chunk_index`. Document processing order follows `metadata.csv` row order;
page order follows the PDF's own page order; chunk order follows the
greedy left-to-right packing above. **Verified**, not just claimed: the
real ingestion script was run twice against the unchanged corpus and the
two output CSVs were diffed byte-for-byte -- identical. This is also
covered by an automated test
(`test_ingestion_is_deterministic_across_runs`).

## 12. Missing-file failure behavior

`verify_catalogued_documents()` checks every `metadata.csv` row with a
non-blank `local_filename` against `data/documents/raw/`. If the file is
missing, it raises `IngestionError` naming the exact `document_id` and
expected file path, before any PDF processing begins -- never a bare
low-level traceback. Rows with a *blank* `local_filename` (documents
Phase 2 verified but never downloaded, like DOC-005/DOC-006) are not an
error; they are simply skipped and counted in the run summary as
"documents catalogued but not locally available." This is covered by
`test_verify_catalogued_documents_raises_clear_error_for_missing_file`,
which uses an isolated `tmp_path` scenario and never touches the real
corpus.

## 13. Final real ingestion run statistics (actual, not estimated)

```
Documents processed: 4 (DOC-001, DOC-002, DOC-003, DOC-004)
Documents catalogued but not locally available: 2 (DOC-005, DOC-006)
Pages processed: 565
  native-text pages: 533
  pdfplumber fallback pages: 120
  OCR-triggered pages: 32
  flagged low-quality pages: 25 (15 empty_ocr_output [zero chunks], 5 suspicious_text, 5 low_ocr_quality)
Chunks produced: 861
```

Per-document chunk counts: DOC-001 441, DOC-002 223, DOC-003 169, DOC-004 28.

Output file: [data/processed/document_chunks.csv](../data/processed/document_chunks.csv)

## 14. Limitations (disclosed)

- **Small corpus.** Only 4 real documents (565 pages) are ingested. This
  reflects the honestly-disclosed real-data scarcity already documented in
  `data/README.md` and `docs/SYNTHETIC_DATA_METHODOLOGY.md`, not a defect
  in this phase's pipeline.
- **Heading detection is best-effort** and purely font-size based; it
  will miss headings that are not visually distinguished by a larger font,
  and (as documented in section 7) can occasionally surface a raw
  font-encoding artifact from a source PDF's embedded font rather than the
  intended text.
- **OCR was genuinely exercised** on 32 real pages (see section 8), but
  all of them were short cover/separator/photo pages, not a full page of
  dense scanned body text -- so OCR's behavior on a large, continuously
  scanned document (e.g. an old scanned report with no text layer at all)
  remains untested in this corpus, since no such document exists in it.
- **Table extraction is not pixel-perfect.** The pdfplumber fallback
  materially improves structure recovery for detected tables (see the
  worked example in section 6) but complex merged-cell or nested tables
  may still lose some structure; this was spot-checked, not exhaustively
  audited cell-by-cell.
- **"Token" is a word-count approximation**, not a real subword tokenizer
  count (see section 9); actual downstream embedding-model token counts
  will differ somewhat from the ~400/~50 targets.
- **DOC-005 and DOC-006 remain unavailable**, blocked by PIB's
  bot-protection (HTTP 401) even after retrying with a browser-like
  User-Agent, and are HTML press-release pages rather than direct PDF
  links regardless (section 3).
