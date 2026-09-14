"""Phase 9 hybrid contradiction/inconsistency detector: constants and
thresholds, in one place so extraction, pairing, comparison, and the CLI
script can never silently drift apart (same convention as
app/rag/config.py). See docs/CONTRADICTION_DETECTION.md for the full
rationale behind every value here.
"""

from __future__ import annotations

from app.config import REPO_ROOT

# --- Topic-pairing threshold ------------------------------------------------
#
# MUST be stricter than Phase 8's 0.35 retrieval threshold (that threshold
# answers "relevant to this query"; this one answers "plausibly discussing
# the same specific fact"). Chosen from a real measurement, not guessed --
# see docs/CONTRADICTION_DETECTION.md section "Topic-pairing threshold":
#
#   - Full cross-document pairwise cosine similarity was computed over the
#     real 861-chunk Phase 8 embeddings (233,883 cross-document pairs).
#   - Percentiles: p90=0.519, p95=0.563, p99=0.642, p99.5=0.670, p99.9=0.731.
#     0.75 sits above even the 99.9th percentile of ALL cross-document pairs.
#   - Manual inspection of the highest-similarity pairs (>=0.85) showed
#     near-paraphrase restatements of the same specific fact (e.g. the same
#     Bharatmala Phase-I financial-outlay figure in two different reports).
#   - Manual inspection down to the 0.75 cutoff (rank ~139) still showed
#     genuinely on-topic, fact-comparable pairs (shared tables, shared named
#     quantities). Below roughly 0.60-0.70, matches become dominated by
#     generic document-identity/boilerplate similarity (repeated "NATIONAL
#     HIGHWAY AUTHORITY OF INDIA www.nhai.org" headers, title-page-vs-table-
#     of-contents pairs) rather than a shared specific fact.
#   - 0.75 was fixed from this one-time measurement before any comparison
#     logic was tuned against real output, per the "do not loosen the
#     threshold to manufacture contradictions" instruction.
TOPIC_PAIRING_THRESHOLD = 0.75

# --- Claim-level "same named fact" gate -------------------------------------
#
# Even within a topically-similar chunk pair, two same-type claims are only
# compared if their immediate surrounding text shares enough distinguishing
# vocabulary to plausibly be the same named fact (not just two unrelated
# numbers that happen to both be currency figures on an on-topic page).
# Jaccard overlap of content words (see comparison.py._content_words),
# excluding a stoplist of generic report/unit words. 0.2 is a low bar,
# deliberately: short_context windows are short (~20-30 words) and two
# genuinely-matching sources rarely use identical phrasing, so requiring a
# high overlap would silently exclude real matches (e.g. "financial outlay"
# vs "planned financial outlay" vs "investment outlay").
CLAIM_CONTEXT_JACCARD_MIN = 0.20

# --- Comparison tolerances ---------------------------------------------------
#
# Percentage: real corpus percentages are reported to 2 decimal places
# (e.g. 75.62%, 92.72%, 170.89%) and the same fact reproduces the identical
# figure across overlapping chunks of the same document. 1.0 percentage
# point is a generous allowance for benign rounding/recomputation noise
# while still catching a real double-digit-point divergence (e.g. the
# seeded synthetic fixture's 12% vs 27%, a 15pp gap).
PERCENTAGE_TOLERANCE_PP = 1.0

# Currency: the real corpus contains one directly-observed case of benign,
# context-explained drift -- DOC-001's Rs 8,46,588 crore / 26,316 km
# (as of 31 March 2023) vs DOC-003's Rs 8,53,656 crore / 26,425 km (as of
# 31 December 2024), a ~0.8% relative difference driven entirely by a
# ~21-month later reporting cutoff. 5% is set well above that observed
# benign drift so ordinary date-driven noise does not get flagged, while a
# genuinely large divergence (e.g. the Rs 3,85,000 crore vs Rs 5,35,000
# crore Bharatmala-Phase-I-scope figures, a ~28% relative gap) still
# surfaces for human review.
CURRENCY_RELATIVE_TOLERANCE_PCT = 5.0

# Count: mirrors the currency reasoning -- the same real corpus example's
# length figures (26,316 vs 26,425 km-equivalent count-style figures) differ
# by well under 1%.
COUNT_RELATIVE_TOLERANCE_PCT = 5.0

# Date: two date claims describing the same named event either match
# exactly or they don't -- there is no principled partial-credit tolerance
# for "the CCEA approval date was mostly the same". Any exact mismatch,
# once the context/jaccard gate has established the claims are plausibly
# about the same named date, is flagged.
DATE_EXACT_MATCH_REQUIRED = True

# --- Context-aware exclusion keyword sets -----------------------------------
#
# If one claim's short_context contains a "planned-side" word and the other
# contains an "actual-side" word (and not the reverse), the difference is
# explained by planned-vs-actual reporting rather than a genuine
# inconsistency -- classified as a contextual difference, never flagged.
PLANNED_SIDE_KEYWORDS = (
    "planned",
    "approved",
    "estimated",
    "proposed",
    "sanctioned outlay",
    "ccea approved",
    "target",
    "budgeted",
)
ACTUAL_SIDE_KEYWORDS = (
    "actual",
    "awarded",
    "incurred",
    "completed",
    "expenditure",
    "achieved",
    "constructed",
    "spent",
    "utilised",
    "utilized",
    "disbursed",
)

# --- Output paths ------------------------------------------------------------
CONTRADICTION_OUTPUT_DIR = REPO_ROOT / "data" / "processed"
CLAIMS_OUTPUT_PATH = CONTRADICTION_OUTPUT_DIR / "extracted_claims.csv"
FLAGS_OUTPUT_PATH = CONTRADICTION_OUTPUT_DIR / "contradiction_flags.csv"

# --- Absolute-language safety -----------------------------------------------
#
# Every flag description must be hedged. These substrings must NEVER appear
# in generated output (case-insensitive) -- enforced both by
# detector.py's own description builder and by an automated test that
# inspects every generated flag description.
PROHIBITED_ABSOLUTE_PHRASES = (
    "confirmed contradiction",
    "contradiction detected",
    "confirmed error",
    "is false",
    "is wrong",
    "incorrect figure",
    "factual error",
    "definitely wrong",
    "proven false",
    "one of them is wrong",
)
