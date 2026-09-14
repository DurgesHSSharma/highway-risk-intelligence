# Hybrid Contradiction / Inconsistency Detection (Phase 9)

## 1. Objective

Phase 9 builds a **heuristic contradiction/inconsistency detector** over the
real 4-document, 861-chunk corpus that Phases 7-8 produced:

```
document_chunks.csv -> rule-based claim extraction -> Phase 8 embedding
reuse for cross-document topic pairing -> context-aware tolerance
comparison -> hedged "potential inconsistency requiring verification" flags
```

It identifies passages from **different source documents** that appear to
discuss the same specific fact but report meaningfully different values,
combining:

1. structured rule-based numeric/date extraction,
2. the existing Phase 8 embedding similarity (reused, never recomputed),
3. cross-document topic pairing,
4. context-aware numeric comparison,
5. conservative tolerance-based flagging.

**This is NOT a fact-checker.** It never determines that a document is
false, wrong, or erroneous. Every flagged pair is described only as a
*"potential inconsistency requiring verification"* -- a heuristic signal for
a human reviewer, not a verdict.

## 2. Architecture

```
backend/app/contradiction/
  config.py       thresholds/tolerances, all documented with real-corpus evidence
  extraction.py   rule-based claim extractor (currency/percentage/date/count)
  pairing.py      cross-document topic pairing, reusing Phase 8 embeddings
  comparison.py   context-aware tolerance comparison (per claim-pair)
  detector.py     orchestrates the full pass, builds hedged flag descriptions

backend/app/schemas/contradictions.py   API response models
backend/app/routers/documents.py        GET /documents/inconsistencies (added)
scripts/detect_contradictions.py        thin CLI wrapper (mirrors build_rag_index.py)
```

Phase 6/8 code (database schema, prediction endpoints, RAG retrieval logic,
ML models) is untouched. The only Phase 8 file modified is `app/main.py`,
which gained one line in its `lifespan` to warm the Phase 9 singleton --
Phase 8's own retrieval/answer logic is unchanged.

## 3. Numeric / date / count extraction patterns

All four claim types are extracted by `app/contradiction/extraction.py`,
pure regex + `re`/`datetime`-free normalization (Python standard library
only, no new dependency).

- **Currency**: qualifies only if a rupee symbol (`₹`, the literal backtick
  `` ` `` -- this corpus's alternate font-decoded rupee glyph, see
  `docs/DOCUMENT_INGESTION.md` section 7 for the same phenomenon in
  headings -- `Rs.`, `INR`) OR a `crore`/`crores`/`lakh`/`lakhs`/`cr.` unit
  suffix is present; a bare number is never treated as currency. Handles
  Indian comma grouping (`5,35,000`) and the compound `"X lakh crore"` unit
  (`= X * 100,000` crore). Everything normalizes to **crore** as the
  comparison unit. A currency-shaped match immediately followed by `/km` or
  `per km` is excluded -- it is a **rate**, not an absolute total, and
  comparing a rate to a total would be a unit-conversion/aggregation-level
  category error.
- **Percentage**: `\d+(\.\d+)?\s*(%|per\s*cent|percent)`, case-insensitive.
  Normalizes to a plain float (percentage points).
- **Date**: three real formats observed in this corpus --
  `DD/MM/YYYY`/`DD-MM-YYYY`/`DD.MM.YYYY` (day/month order per Indian
  government document convention, an explicit documented assumption when
  both day and month are `<=12` and therefore ambiguous),
  `DD Month YYYY` (e.g. "31 March 2023"), and `Month DD, YYYY` (e.g.
  "February 20, 2025", found in DOC-004). Normalized to ISO `YYYY-MM-DD`
  internally; the original matched text is always preserved as `raw_text`.
- **Count**: only extracted when a number is immediately followed by a
  curated count noun (`projects`, `packages`, `parks`, `districts`, `PIUs`,
  `schemes`, `cases`, optionally preceded by "highway") -- never a blind
  "every number is a count" rule. `corridors`/`expressways` were
  deliberately **excluded** from this noun list after real-corpus testing
  showed they are almost always flattened PDF-table row labels in this
  corpus (see section 4 below), not genuine "N corridors" count phrasing.

Every extracted claim carries: `claim_id`, `chunk_id`, `document_id`,
`page_number`, `claim_type`, `raw_text` (verbatim matched text),
`normalized_value`, `normalized_unit`, and `short_context` (the ~120
characters of chunk text surrounding the match).

## 4. Extraction limitations (disclosed honestly)

Regex-based extraction is **not exhaustive or perfect**, per the Phase 9
brief's explicit instruction. Specific, real limitations found while
building and testing this extractor against the actual corpus:

- **Flattened PDF tables are a real hazard.** Two genuine bugs were found
  and fixed during development (not merely theoretical):
  - `Rs` (case-insensitive, originally without a word boundary) matched as
    a bare substring inside unrelated words -- e.g. the trailing "rs" of
    "Corridors" in a flattened table row ("...4 National Corridors
    5,000...") was misread as the currency symbol "Rs" prefixing "5,000".
    Fixed with negative lookaround (`(?<![A-Za-z])Rs\.?(?![A-Za-z])`).
  - Including `corridors`/`expressways` as count nouns produced false
    "N Expressways" claims where the number was actually the *previous*
    table row's data cell and "Expressways" the *next* row's label (e.g.
    "...824 732 Expressways 2,422..." -- 732 is a completed-length figure,
    not a count of 732 expressways). Fixed by excluding these two nouns
    from the count-noun list (see section 3).
  - After these fixes, the real-corpus false-positive flag count dropped
    from 14 to 3 (see section 13) -- these were genuine extraction bugs,
    not threshold-tuning.
- **Table cells without an adjacent unit are missed.** A `pdfplumber_table`
  chunk's pipe-delimited cell text (e.g. `"| 8,737 | 5,986 |"`) carries no
  inline unit token near the number, so it is not picked up as a currency
  or count claim -- only the same table's earlier native-text rendering
  (which this corpus's chunks usually also contain, see
  `docs/DOCUMENT_INGESTION.md` section 6) contributes claims.
- **OCR-reversed/garbled text is not parsed meaningfully.** The one known
  reversed-text table artifact (`docs/DOCUMENT_INGESTION.md`'s
  `"5HSRUW1RRI"`-style font-decoding cases) will not yield sensible claims;
  this is inherited from Phase 7's own disclosed OCR/extraction quality,
  not a new Phase 9 defect.
- **The count-noun list is a fixed, curated set.** It will not catch every
  real count phrasing in a larger or different corpus.
- **DD/MM vs MM/DD date ambiguity** is resolved by assuming Indian
  government DD/MM/YYYY convention whenever both components are `<=12` --
  not individually verified per occurrence.

## 5. Existing Phase 8 embedding reuse

Phase 9 **never recomputes embeddings**. `app/contradiction/pairing.py`
loads the already-committed `rag_index/embeddings.npy` (861 x 384,
L2-normalized `sentence-transformers/all-MiniLM-L6-v2` vectors) and
`rag_index/metadata.json`'s chunk mapping directly, and computes the full
cross-document pairwise cosine similarity as one matrix multiply (embeddings
are already unit-norm, so inner product = cosine similarity -- identical
convention to Phase 8's FAISS `IndexFlatIP`). No new embedding model call,
no FAISS rebuild.

## 6. Topic-pairing threshold

**Chosen value: 0.75** -- more than double Phase 8's 0.35 retrieval
threshold, and deliberately so: Phase 8's threshold answers *"is this chunk
relevant to this query?"*; Phase 9's threshold must answer the much
stricter *"are these two chunks from different documents plausibly
discussing the same specific fact?"*.

**How it was chosen** -- measured directly from the real corpus, before any
comparison/tolerance logic was written or tuned:

- Computed the full cross-document pairwise cosine similarity over all 861
  real chunk embeddings: 233,883 cross-document pairs.
- Percentile distribution of that similarity: p50=0.345, p75=0.440,
  p90=0.519, p95=0.563, p99=0.642, p99.5=0.670, p99.9=0.731,
  p99.99=0.838, max=0.933. **0.75 sits above even the 99.9th percentile**
  of all cross-document pairs -- only 139 of 233,883 pairs (0.06%) clear it.
- Manually inspected representative pairs across bands:
  - **>=0.85** (15 pairs): near-paraphrase restatements of the exact same
    specific fact -- e.g. DOC-001, DOC-002, and DOC-003 each separately
    describing the Bharatmala Phase-I CCEA approval, length, and outlay
    figures in near-identical sentences.
  - **0.75-0.85** (~92 pairs): still genuinely on-topic and fact-comparable
    -- shared financial/corridor tables, the same named quantities, e.g.
    DOC-002's and DOC-003's Access-Controlled-Corridor cost tables.
  - **~0.72-0.75** (just below the chosen cutoff): still reasonably
    specific (shared BPP-I audit tables, corridor lists) -- inspected to
    confirm the cutoff wasn't arbitrarily excluding good candidates.
  - **~0.60-0.70**: quality drops sharply -- dominated by generic
    document-identity/boilerplate matches (repeated "NATIONAL HIGHWAY
    AUTHORITY OF INDIA www.nhai.org" page headers, a title-page-vs-table-
    of-contents pair) rather than a shared specific fact.
- 0.75 was fixed from this one-time measurement and never loosened
  afterward to manufacture a larger candidate set.

**Candidate pair count at 0.75: 139** (cross-document chunk pairs).

## 7. Comparison tolerances

- **Percentage: flag if `|difference| > 1.0` percentage point.** This
  corpus reports percentages to 2 decimal places (e.g. 75.62%, 92.72%,
  170.89%), and the identical fact reproduces the exact figure across
  overlapping chunks of the same document. 1.0pp is a generous allowance
  for benign rounding/recomputation noise while still catching a real
  double-digit-point divergence (the seeded synthetic fixture's 12% vs
  27%, a 15pp gap).
- **Currency: flag if relative difference > 5.0%** (values normalized to
  crore). Justified by one directly-observed real-corpus case of benign,
  context-explained drift: DOC-001's ₹8,46,588 crore / 26,316 km (as of 31
  March 2023) vs DOC-003's ₹8,53,656 crore / 26,425 km (as of 31 December
  2024) -- a ~0.8% relative difference driven entirely by a ~21-month later
  reporting cutoff. 5% sits well above that observed benign drift, so
  ordinary date-driven noise does not get flagged, while a genuinely large
  divergence (the ₹3,85,000 crore vs ₹5,35,000 crore Bharatmala-Phase-I
  scope figures, a ~28% relative gap -- see section 13) still surfaces.
- **Count: flag if relative difference > 5.0%** -- mirrors the currency
  reasoning (the same real example's length figures differ by well under
  1%).
- **Date: flag on any exact mismatch** of the normalized calendar date,
  once the context/same-named-fact gate (section 8) has established the
  two claims are plausibly about the same named date. There is no
  principled partial-credit tolerance for "the approval date was mostly
  the same."

Tolerances were fixed from this reasoning before the final real-corpus run
and were **not** adjusted afterward to change which specific pairs got
flagged.

## 8. Context-aware comparison rules

Two same-type claims are compared only if all of the following hold:

1. **Same-named-fact gate**: the two claims' `short_context` windows share
   enough distinguishing vocabulary (Jaccard overlap of content words,
   excluding a stoplist of generic report/unit words, `>= 0.20`) to
   plausibly be about the same specific fact -- not just two unrelated
   numbers that happen to share a claim type on an on-topic page.
2. **No planned-vs-actual asymmetry**: if one claim's context contains a
   "planned-side" word (planned, approved, estimated, proposed, sanctioned
   outlay, CCEA approved, target, budgeted) and the other contains an
   "actual-side" word (actual, awarded, incurred, completed, expenditure,
   achieved, constructed, spent, utilised/utilized, disbursed) -- and not
   the reverse -- the difference is classified as a **contextual
   difference**, never flagged.
3. **No differing reporting-cutoff dates** (currency/count claims only): if
   the two claims' own chunks each carry at least one extracted date claim
   and those date sets are completely disjoint, the pair is anchored to
   different as-of dates and is classified as a **contextual difference**,
   never flagged. This directly explains the real DOC-001 (31 March 2023)
   vs DOC-003 (31 December 2024) length/cost pair from section 7 above.

Only pairs that clear all of these (and then fail the numeric tolerance)
are flagged.

## 9. Real corpus results (actual, measured)

Run via `python -m scripts.detect_contradictions` against the real,
committed 4-document, 861-chunk corpus and `rag_index/`:

| Metric | Count |
|---|---|
| Chunks considered | 861 |
| Total claims extracted | 3,697 |
| &nbsp;&nbsp;currency | 1,019 |
| &nbsp;&nbsp;percentage | 629 |
| &nbsp;&nbsp;date | 1,861 |
| &nbsp;&nbsp;count | 188 |
| Cross-document candidate chunk pairs (topic threshold 0.75) | 139 |
| Comparable claim pairs evaluated | 7 |
| &nbsp;&nbsp;contextual differences excluded | 3 |
| &nbsp;&nbsp;flagged (potential inconsistencies) | 3 |

**All 3 real flags**, verbatim (hedged descriptions as actually generated):

1. **DOC-002 p.20** (`'₹ 3,85,000 Crore'`) vs **DOC-003 p.24**
   (`'` 8,53,656 crore'`) -- both discuss the Bharatmala Phase-I capital
   cost/outlay, similarity 0.867, relative difference ~54.9%.
2. **DOC-002 p.20** (`'₹ 1,50,000 Crore'`) vs **DOC-004 p.2**
   (`'5,35,000 crore'`) -- similarity 0.887, relative difference ~72.0%.
3. **DOC-002 p.20** (`'₹ 6,29,831 Cr.'`) vs **DOC-004 p.2**
   (`'5,35,000 crore'`) -- similarity 0.887, relative difference ~15.1%.

**What these likely reflect (disclosed, not asserted as fact)**: DOC-002
partitions the Bharatmala Phase-I outlay into a BPP-I-only figure
(₹3,85,000 crore) plus a separate residual-NHDP figure (₹1,50,000 crore),
while DOC-001/DOC-003/DOC-004 elsewhere quote a single combined figure
(₹5,35,000 / ₹8,53,656 crore) that appears to include both components. This
is a plausible **scope/aggregation-level difference** that the current
heuristics (section 8) could not fully disambiguate from context alone --
which is exactly the kind of case this system is designed to surface for a
human to check, not resolve on its own. **No claim is made here that either
document is wrong.**

This is a real, honestly-reported result. It was not manufactured, and the
thresholds/tolerances above were not adjusted after seeing it.

## 10. Seeded synthetic test result

A clearly-labeled fixture,
[tests/fixtures/contradiction_synthetic_fixture.json](../tests/fixtures/contradiction_synthetic_fixture.json),
proves the mechanism independently of the real corpus:

> `SYN-001`: "Test Highway Project X had a reported cost overrun of **12%**
> as assessed by the state audit team."
> `SYN-002`: "Test Highway Project X had a reported cost overrun of **27%**
> according to the central monitoring agency."

Result: extracted as two percentage claims (12.0 and 27.0), correctly
identified as the same named fact (shared "Test Highway Project X" /
"cost overrun" vocabulary), and **flagged** with an absolute difference of
15.0 percentage points (exceeds the 1.0pp tolerance) -- status `"flagged"`.

**This fixture is never part of the real corpus, RAG index, or real-corpus
statistics above** -- it lives only in `tests/fixtures/`, uses
`SYN-`-prefixed document IDs that do not and must not appear in
`data/documents/metadata.csv` (verified by an automated test), and is
never written to `data/processed/document_chunks.csv` or `rag_index/`.

## 11. API endpoint

```
GET /documents/inconsistencies
```

Implemented in `backend/app/routers/documents.py` (same router as the
Phase 8 `/documents/search` endpoint, following its conventions). Returns
the real corpus results: chunk/claim counts, candidate/comparable-pair
counts, and the full flag list -- every flag hedged, never absolute. A
zero-flag result (not the actual real-corpus outcome, but exercised
directly in tests) returns a valid `200` with `flagged_count: 0` and
`flags: []`, never an error. The detector runs once at FastAPI startup
(`app/main.py`'s `lifespan`, alongside the existing Phase 6/8 warm-up
calls) and is cached, never rebuilt per request.

## 12. Test results

New tests (all passing, exercised against the real corpus wherever the
brief calls for it, plus the isolated seeded fixture):

- `backend/tests/test_contradiction_extraction.py` -- real-corpus currency/
  percentage/date/count extraction, plus regression tests for the two
  extraction bugs found and fixed (section 4).
- `backend/tests/test_contradiction_pairing.py` -- threshold behavior,
  cross-document-only pairing, determinism, real candidate-pair count.
- `backend/tests/test_contradiction_comparison.py` -- tolerance logic
  (divergent/consistent/trivial-rounding cases), context-aware exclusion
  (planned-vs-actual, differing reporting dates), the seeded synthetic
  fixture, and absolute-language safety checks.
- `backend/tests/test_contradictions_api.py` -- endpoint structure, hedged
  language, the zero-flags response path, and re-verification that the
  existing Phase 6/8 endpoints are unaffected.
- `tests/test_detect_contradictions.py` -- full end-to-end real-corpus run,
  determinism across independent runs, flag-id sequencing.

Final repo-wide count: **215 pre-existing tests (Phase 1-8) + new Phase 9
tests, all passing** -- see the Phase 9 completion report for the exact
final number.

## 13. Determinism

`app/contradiction/pairing.py` sorts candidate pairs by
`(-similarity, chunk_id_a, chunk_id_b)`; `app/contradiction/detector.py`
sorts final flags by `(document_a, chunk_a, document_b, chunk_b,
claim_type, raw_claim_a, raw_claim_b)` before assigning sequential
`FLAG-000N` ids -- output never depends on unordered dict/set iteration.
Verified for real: `scripts.detect_contradictions` was run twice
independently and its full text output diffed byte-for-byte identical; an
automated test (`test_real_corpus_detection_is_deterministic_across_independent_runs`)
locks this in.

## 14. Known limitations

- See section 4 for extraction-specific limitations.
- The claim-context Jaccard gate (section 8) is a coarse heuristic -- a
  genuinely comparable pair phrased with very different vocabulary could
  be missed (a false negative), and two claims that happen to share
  vocabulary without being the same fact could in principle still slip
  through if the wording is similar enough (mitigated, not eliminated, by
  the 0.20 threshold).
- Context-aware exclusion (planned-vs-actual, differing reporting dates) is
  keyword/date-based, not a semantic understanding of scope -- as section 9
  discloses, a genuine scope/aggregation-level difference (BPP-I-only vs.
  BPP-I-plus-NHDP) was not caught by these heuristics and surfaced as a
  flag instead. This is disclosed as a known limitation, not hidden.
- Date-format disambiguation (DD/MM vs MM/DD) relies on a documented
  convention assumption, not per-occurrence verification.

## 15. Small-corpus limitation

The corpus contains only 4 real documents / 861 chunks. 139 candidate
pairs and 3 flags are results specific to this small corpus and should not
be generalized to a larger or different document set -- more documents
covering more genuinely overlapping facts would likely change both the
candidate-pair count and the flagged count substantially. A future corpus
expansion (more real documents) could change all of these numbers; they
are not claimed as representative of a general "contradiction rate" in
highway-sector reporting.

## 16. This is NOT a fact-checker

This system never determines that any document is false, wrong,
erroneous, or definitively contradictory. It identifies passages that
*appear* to report the same fact with different values and surfaces them,
hedged, for human verification. A flagged pair could turn out to have a
legitimate explanation (different scope, different reporting date,
rounding, a typo in either source, or something not yet considered) that
this system cannot determine on its own. Absolute language ("confirmed
contradiction", "confirmed error", "is false", "is wrong", "incorrect
figure", "factual error") is explicitly banned from every generated
description and enforced by an automated test
(`test_flag_description_never_contains_prohibited_absolute_language`).
