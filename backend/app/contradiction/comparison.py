"""Phase 9 context-aware claim comparison.

Given two same-type claims from a candidate chunk pair, decides one of:

  - not a comparable pair at all (claim types differ, or the surrounding
    text doesn't share enough vocabulary to plausibly be the same named
    fact) -- returns None, not counted as an evaluated comparison.
  - "contextual_difference": a difference exists but is explained by
    planned-vs-actual wording or differing reporting-cutoff dates, per the
    Phase 9 brief's explicit instruction not to flag these.
  - "flagged": the difference exceeds the documented tolerance and no
    contextual explanation was found -- a potential inconsistency
    requiring verification.
  - "not_flagged": compared, within tolerance.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.contradiction.config import (
    ACTUAL_SIDE_KEYWORDS,
    CLAIM_CONTEXT_JACCARD_MIN,
    COUNT_RELATIVE_TOLERANCE_PCT,
    CURRENCY_RELATIVE_TOLERANCE_PCT,
    PERCENTAGE_TOLERANCE_PP,
    PLANNED_SIDE_KEYWORDS,
)
from app.contradiction.extraction import Claim

_STOPWORDS = {
    "the",
    "and",
    "for",
    "have",
    "been",
    "under",
    "against",
    "with",
    "that",
    "this",
    "from",
    "total",
    "crore",
    "crores",
    "lakh",
    "lakhs",
    "cost",
    "length",
    "project",
    "projects",
    "highway",
    "highways",
    "national",
    "into",
    "were",
    "was",
    "are",
    "per",
    "cent",
    "percent",
    "also",
    "which",
    "till",
    "upto",
}

_WORD_PATTERN = re.compile(r"[a-zA-Z]{4,}")


def _content_words(text: str) -> set[str]:
    return {w for w in _WORD_PATTERN.findall(text.lower()) if w not in _STOPWORDS}


def _context_jaccard(context_a: str, context_b: str) -> float:
    words_a, words_b = _content_words(context_a), _content_words(context_b)
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)


def _has_planned_actual_asymmetry(context_a: str, context_b: str) -> bool:
    a_lower, b_lower = context_a.lower(), context_b.lower()
    a_planned = any(k in a_lower for k in PLANNED_SIDE_KEYWORDS)
    b_planned = any(k in b_lower for k in PLANNED_SIDE_KEYWORDS)
    a_actual = any(k in a_lower for k in ACTUAL_SIDE_KEYWORDS)
    b_actual = any(k in b_lower for k in ACTUAL_SIDE_KEYWORDS)
    return (a_planned and b_actual and not a_actual and not b_planned) or (
        b_planned and a_actual and not b_actual and not a_planned
    )


def _differing_reporting_dates(dates_a: set[str], dates_b: set[str]) -> bool:
    return bool(dates_a) and bool(dates_b) and dates_a.isdisjoint(dates_b)


@dataclass(frozen=True)
class ComparisonOutcome:
    status: str  # "flagged" | "not_flagged" | "contextual_difference"
    context_jaccard: float
    difference: float | None
    reason: str | None
    confidence: str | None


def _confidence_from_jaccard(jaccard: float) -> str:
    if jaccard >= 0.5:
        return "high"
    if jaccard >= 0.35:
        return "medium"
    return "low"


def compare_claims(
    claim_a: Claim,
    claim_b: Claim,
    dates_in_chunk_a: set[str],
    dates_in_chunk_b: set[str],
) -> ComparisonOutcome | None:
    """Returns None if the pair isn't comparable at all (incompatible
    types, or claims not plausibly about the same named fact). Otherwise
    returns a ComparisonOutcome -- every non-None result counts as one
    "comparable claim pair" for reporting purposes, whether or not it ends
    up flagged."""
    if claim_a.claim_type != claim_b.claim_type:
        return None
    if claim_a.claim_type in ("currency",) and claim_a.normalized_unit != claim_b.normalized_unit:
        return None

    jaccard = _context_jaccard(claim_a.short_context, claim_b.short_context)
    if jaccard < CLAIM_CONTEXT_JACCARD_MIN:
        return None

    if _has_planned_actual_asymmetry(claim_a.short_context, claim_b.short_context):
        return ComparisonOutcome(
            status="contextual_difference",
            context_jaccard=jaccard,
            difference=None,
            reason="planned_vs_actual_wording",
            confidence=None,
        )

    if claim_a.claim_type in ("currency", "count") and _differing_reporting_dates(
        dates_in_chunk_a, dates_in_chunk_b
    ):
        return ComparisonOutcome(
            status="contextual_difference",
            context_jaccard=jaccard,
            difference=None,
            reason="different_reporting_cutoff_dates",
            confidence=None,
        )

    confidence = _confidence_from_jaccard(jaccard)

    if claim_a.claim_type == "percentage":
        diff = abs(float(claim_a.normalized_value) - float(claim_b.normalized_value))
        flagged = diff > PERCENTAGE_TOLERANCE_PP
        return ComparisonOutcome(
            status="flagged" if flagged else "not_flagged",
            context_jaccard=jaccard,
            difference=diff,
            reason=None,
            confidence=confidence,
        )

    if claim_a.claim_type == "currency":
        val_a, val_b = float(claim_a.normalized_value), float(claim_b.normalized_value)
        base = max(abs(val_a), abs(val_b), 1e-9)
        relative_diff_pct = abs(val_a - val_b) / base * 100
        flagged = relative_diff_pct > CURRENCY_RELATIVE_TOLERANCE_PCT
        return ComparisonOutcome(
            status="flagged" if flagged else "not_flagged",
            context_jaccard=jaccard,
            difference=relative_diff_pct,
            reason=None,
            confidence=confidence,
        )

    if claim_a.claim_type == "count":
        val_a, val_b = float(claim_a.normalized_value), float(claim_b.normalized_value)
        base = max(abs(val_a), abs(val_b), 1e-9)
        relative_diff_pct = abs(val_a - val_b) / base * 100
        flagged = relative_diff_pct > COUNT_RELATIVE_TOLERANCE_PCT
        return ComparisonOutcome(
            status="flagged" if flagged else "not_flagged",
            context_jaccard=jaccard,
            difference=relative_diff_pct,
            reason=None,
            confidence=confidence,
        )

    if claim_a.claim_type == "date":
        flagged = claim_a.normalized_value != claim_b.normalized_value
        return ComparisonOutcome(
            status="flagged" if flagged else "not_flagged",
            context_jaccard=jaccard,
            difference=None if not flagged else 1.0,
            reason=None,
            confidence=confidence,
        )

    return None
