"""Phase 9 rule-based structured-claim extractor.

Regex/rule-based extraction over chunk text, pulling out four claim types
(currency, percentage, date, count) wherever the surrounding text gives a
clear enough signal. This is NOT exhaustive or perfect -- see the
"Extraction limitations" section of docs/CONTRADICTION_DETECTION.md for
what it deliberately does not attempt to catch (e.g. pdfplumber table cells
whose unit lives in a separate header row, OCR-reversed table text).

Every claim preserves its original matched text (`raw_text`) alongside the
normalized value, and never removes/alters the source chunk data -- this is
a read-only pass over the already-committed Phase 7 chunk dataset.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

CONTEXT_WINDOW_CHARS = 60

MONTH_NAMES = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}
_MONTH_ALT = "|".join(MONTH_NAMES.keys())

COUNT_NOUNS = (
    "projects?",
    "packages?",
    "parks?",
    "districts?",
    "pius?",
    "schemes?",
    "cases?",
)
# "corridors"/"expressways" were deliberately excluded even though they
# appear as count-like nouns in prose -- in this corpus they are almost
# always flattened PDF-table ROW LABELS (e.g. ".. 824 732 Expressways
# 2,422 1,791 .."), where the number immediately before the word is the
# PREVIOUS row's data cell, not a count of that noun. Including them
# produced false "N Expressways" claims from adjacent, unrelated table
# cells -- see docs/CONTRADICTION_DETECTION.md "Extraction limitations".

# --- Compiled patterns -------------------------------------------------------

# Currency: qualifies only if a rupee symbol/Rs/INR prefix OR a crore/lakh
# unit suffix is present (never a bare number). Handles the corpus's mixed
# rupee-symbol rendering (genuine "₹" in some PDFs, a literal backtick "`"
# in others due to embedded-font decoding -- see docs/DOCUMENT_INGESTION.md
# section 7 for the same font-encoding phenomenon observed in headings) and
# Indian comma grouping (5,35,000), which `float()` handles fine once commas
# are stripped regardless of grouping convention.
#
# The "Rs"/"INR" symbol alternatives use negative lookaround, not `\b`,
# because plain `Rs\.?` (case-insensitive, no boundary) was found to match
# mid-word -- e.g. the trailing "rs" of "Corridors 5,000" in a flattened
# PDF table was misread as the currency symbol "Rs" prefixing "5,000".
_CURRENCY_PATTERN = re.compile(
    r"(?P<symbol>₹|`|(?<![A-Za-z])Rs\.?(?![A-Za-z])|(?<![A-Za-z])INR(?![A-Za-z]))?\s*"
    r"(?P<number>\d[\d,]*(?:\.\d+)?)\s*"
    r"(?P<unit>lakh\s*crores?|crores?|lakhs?|cr\.)?",
    re.IGNORECASE,
)

# A currency-shaped match immediately followed by "/km" or "per km" is a
# PER-KILOMETRE RATE, not an absolute total -- comparing a rate against a
# total would be a unit-conversion/aggregation-level category error (see
# the Phase 9 brief's explicit context-awareness requirements). Excluded
# from currency-claim extraction entirely rather than mis-tagged.
_PER_KM_RATE_SUFFIX = re.compile(r"^\s*(?:/\s*km|per\s+km)", re.IGNORECASE)

# Trailing `(?!\w)` rather than `\b`: `\b` never matches between "%" and a
# following space/punctuation, since neither side is a word character, so
# a naive `\b` here silently matched nothing for the common "12% " case.
_PERCENTAGE_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(%|per\s*cent|percent)(?!\w)", re.IGNORECASE)

_NUMERIC_DATE_PATTERN = re.compile(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})\b")
_DAY_MONTH_YEAR_PATTERN = re.compile(rf"\b(\d{{1,2}})\s+({_MONTH_ALT})\s+(\d{{4}})\b", re.IGNORECASE)
_MONTH_DAY_YEAR_PATTERN = re.compile(rf"\b({_MONTH_ALT})\s+(\d{{1,2}}),?\s+(\d{{4}})\b", re.IGNORECASE)

_COUNT_PATTERN = re.compile(
    rf"\b(\d{{1,3}}(?:,\d{{3}})*)\s+(?:highway\s+)?({'|'.join(COUNT_NOUNS)})\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Claim:
    claim_id: str
    chunk_id: str
    document_id: str
    page_number: int
    claim_type: str  # "currency" | "percentage" | "date" | "count"
    raw_text: str
    normalized_value: float | str
    normalized_unit: str | None
    short_context: str


def _short_context(text: str, start: int, end: int) -> str:
    lo = max(0, start - CONTEXT_WINDOW_CHARS)
    hi = min(len(text), end + CONTEXT_WINDOW_CHARS)
    return " ".join(text[lo:hi].split())


def _extract_currency(text: str) -> list[tuple[int, int, str, float, str]]:
    """Returns (start, end, raw_text, normalized_value_crore, unit) tuples."""
    out = []
    for m in _CURRENCY_PATTERN.finditer(text):
        symbol = m.group("symbol")
        unit = m.group("unit")
        if not symbol and not unit:
            continue  # bare number -- not a currency claim
        number_str = m.group("number")
        if not number_str or not re.search(r"\d", number_str):
            continue
        if _PER_KM_RATE_SUFFIX.match(text[m.end():]):
            continue  # per-km rate, not an absolute total -- see comment above
        try:
            value = float(number_str.replace(",", ""))
        except ValueError:
            continue

        unit_norm = (unit or "").lower().replace(" ", "")
        if unit_norm.startswith("lakhcrore"):
            value_crore = value * 100_000
        elif unit_norm.startswith("lakh"):
            value_crore = value / 100
        elif unit_norm.startswith("crore") or unit_norm.startswith("cr"):
            value_crore = value
        else:
            # Symbol present, no crore/lakh unit -- a plain rupee amount,
            # converted to crore for a consistent comparison unit.
            value_crore = value / 10_000_000

        out.append((m.start(), m.end(), m.group(0).strip(), value_crore, "crore"))
    return out


def _extract_percentage(text: str) -> list[tuple[int, int, str, float, str]]:
    out = []
    for m in _PERCENTAGE_PATTERN.finditer(text):
        value = float(m.group(1))
        out.append((m.start(), m.end(), m.group(0).strip(), value, "percentage_points"))
    return out


def _extract_dates(text: str) -> list[tuple[int, int, str, str, None]]:
    out = []
    for m in _NUMERIC_DATE_PATTERN.finditer(text):
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        # Corpus convention: Indian government documents use DD/MM/YYYY.
        # Ambiguous when both day and month are <= 12; documented assumption
        # (see docs/CONTRADICTION_DETECTION.md), not resolved by inspecting
        # every instance.
        if month > 12:
            day, month = month, day
        if not (1 <= month <= 12 and 1 <= day <= 31):
            continue
        iso = f"{year:04d}-{month:02d}-{day:02d}"
        out.append((m.start(), m.end(), m.group(0), iso, None))

    for m in _DAY_MONTH_YEAR_PATTERN.finditer(text):
        day, month_name, year = int(m.group(1)), m.group(2).lower(), int(m.group(3))
        month = MONTH_NAMES[month_name]
        if not (1 <= day <= 31):
            continue
        iso = f"{year:04d}-{month:02d}-{day:02d}"
        out.append((m.start(), m.end(), m.group(0), iso, None))

    for m in _MONTH_DAY_YEAR_PATTERN.finditer(text):
        month_name, day, year = m.group(1).lower(), int(m.group(2)), int(m.group(3))
        month = MONTH_NAMES[month_name]
        if not (1 <= day <= 31):
            continue
        iso = f"{year:04d}-{month:02d}-{day:02d}"
        out.append((m.start(), m.end(), m.group(0), iso, None))

    return out


def _extract_counts(text: str) -> list[tuple[int, int, str, float, str]]:
    out = []
    for m in _COUNT_PATTERN.finditer(text):
        number_str = m.group(1)
        noun = m.group(2).lower()
        try:
            value = float(number_str.replace(",", ""))
        except ValueError:
            continue
        out.append((m.start(), m.end(), m.group(0).strip(), value, noun))
    return out


def extract_claims_from_chunk(
    chunk_id: str, document_id: str, page_number: int, chunk_text: str
) -> list[Claim]:
    """Extracts all four claim types from one chunk's text, ordered by
    position of first appearance in the text (deterministic claim_id
    numbering)."""
    if not isinstance(chunk_text, str) or not chunk_text.strip():
        return []

    raw_matches: list[tuple[int, int, str, str, float | str, str | None]] = []
    for start, end, raw, value, unit in _extract_currency(chunk_text):
        raw_matches.append((start, end, "currency", raw, value, unit))
    for start, end, raw, value, unit in _extract_percentage(chunk_text):
        raw_matches.append((start, end, "percentage", raw, value, unit))
    for start, end, raw, value, unit in _extract_dates(chunk_text):
        raw_matches.append((start, end, "date", raw, value, unit))
    for start, end, raw, value, unit in _extract_counts(chunk_text):
        raw_matches.append((start, end, "count", raw, value, unit))

    raw_matches.sort(key=lambda t: (t[0], t[1]))

    claims: list[Claim] = []
    for idx, (start, end, claim_type, raw, value, unit) in enumerate(raw_matches):
        claims.append(
            Claim(
                claim_id=f"{chunk_id}_claim{idx:03d}",
                chunk_id=chunk_id,
                document_id=document_id,
                page_number=page_number,
                claim_type=claim_type,
                raw_text=raw,
                normalized_value=value,
                normalized_unit=unit,
                short_context=_short_context(chunk_text, start, end),
            )
        )
    return claims


def extract_claims_from_chunks(chunks) -> list[Claim]:
    """Extracts claims from every row of an included-chunks DataFrame (see
    app/rag/chunks.py::load_and_filter_chunks), in the DataFrame's own row
    order -- deterministic, no dependency on dict/set iteration order."""
    all_claims: list[Claim] = []
    for _, row in chunks.iterrows():
        all_claims.extend(
            extract_claims_from_chunk(
                chunk_id=row["chunk_id"],
                document_id=row["document_id"],
                page_number=int(row["page_number"]),
                chunk_text=row["chunk_text"],
            )
        )
    return all_claims
