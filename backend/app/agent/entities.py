"""Phase 17C entity extraction for "Ask HRI" -- pure regex/keyword rules,
no NLP model. Every extractor returns `None` (never guesses, never raises)
when its entity genuinely isn't present in the message; app.agent.router
decides what to do about a missing required entity.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.validation import MONTH_PATTERN

PROJECT_ID_RE = re.compile(r"\bHRI-\d{4,}\b", re.IGNORECASE)
MONTH_RE = re.compile(MONTH_PATTERN.strip("^$"))

_RISK_LEVEL_WORDS = ["critical", "high", "medium", "low"]

_SEGMENT_DIMENSION_KEYWORDS = [
    ("contractor", "contractor"),
    ("project type", "project_type"),
    ("state", "state"),
]


def extract_project_id(message: str) -> str | None:
    m = PROJECT_ID_RE.search(message or "")
    return m.group(0).upper() if m else None


def extract_reporting_month(message: str) -> str | None:
    m = MONTH_RE.search(message or "")
    return m.group(0) if m else None


def extract_risk_level(message: str) -> str | None:
    text = (message or "").lower()
    for level in _RISK_LEVEL_WORDS:
        if re.search(rf"\b{level}\b", text):
            return level.upper()
    return None


def extract_segment_dimension(message: str) -> str | None:
    """Returns one of "state"/"project_type"/"contractor" -- the dimension
    a portfolio-analytics query wants to group by -- or None if the
    message doesn't name one (the caller then falls back to the overall
    portfolio overview rather than guessing a dimension)."""
    text = (message or "").lower()
    for phrase, dimension in _SEGMENT_DIMENSION_KEYWORDS:
        if phrase in text:
            return dimension
    return None


# --- what-if override parsing -------------------------------------------
#
# A deliberately small, explicit whitelist -- see docs/ASK_HRI_AGENT.md.
# Every field here is one of scripts.prepare_features.PREDICTOR_COLUMNS
# (verified by a test); nothing outside that set is ever produced. Any
# phrasing not covered here returns None, which the router turns into an
# honest "I can't parse that what-if request" response -- never a guess.

_UP_WORDS = {"improve", "improves", "improved", "increase", "increases", "increased", "rise", "rises", "risen", "overrun", "overruns"}
_DOWN_WORDS = {"decrease", "decreases", "decreased", "worsen", "worsens", "worsened", "drop", "drops", "dropped", "fall", "falls", "fallen", "decline", "declines"}

_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")

# Ordered longest-phrase-first so "financial progress" is matched before
# the shorter "progress" would otherwise steal it.
_CONCEPTS: list[tuple[str, str, str]] = [
    # (phrase, predictor_column, mode)
    ("financial progress", "actual_financial_progress_pct", "additive_pct_point"),
    ("physical progress", "actual_physical_progress_pct", "additive_pct_point"),
    ("progress", "actual_physical_progress_pct", "additive_pct_point"),
    ("contractor productivity", "contractor_productivity_factor", "multiplicative_pct"),
    ("productivity", "contractor_productivity_factor", "multiplicative_pct"),
    ("expenditure", "actual_cost_to_date_inr_cr", "multiplicative_pct"),
    ("cost", "actual_cost_to_date_inr_cr", "multiplicative_pct"),
]


@dataclass(frozen=True)
class WhatIfIntent:
    field: str
    mode: str  # "additive_pct_point" | "multiplicative_pct"
    magnitude_pct: float
    direction: str  # "up" | "down"
    concept_phrase: str

    def apply(self, baseline_value: float) -> float:
        signed = self.magnitude_pct if self.direction == "up" else -self.magnitude_pct
        if self.mode == "additive_pct_point":
            return max(0.0, min(100.0, baseline_value + signed))
        return baseline_value * (1.0 + signed / 100.0)


def parse_whatif_intent(message: str) -> WhatIfIntent | None:
    text = (message or "").lower()

    percent_match = _PERCENT_RE.search(text)
    if not percent_match:
        return None
    magnitude = float(percent_match.group(1))

    concept_phrase = None
    field = None
    mode = None
    for phrase, col, m in _CONCEPTS:
        if phrase in text:
            concept_phrase, field, mode = phrase, col, m
            break
    if field is None:
        return None

    direction = None
    for word in re.findall(r"[a-z]+", text):
        if word in _UP_WORDS:
            direction = "up"
            break
        if word in _DOWN_WORDS:
            direction = "down"
            break
    if direction is None:
        return None

    return WhatIfIntent(field=field, mode=mode, magnitude_pct=magnitude, direction=direction, concept_phrase=concept_phrase)
