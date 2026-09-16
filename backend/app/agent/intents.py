"""Phase 17C deterministic intent classification for "Ask HRI".

Pure keyword/regex rules -- no probabilistic/LLM classification (see
docs/ASK_HRI_AGENT.md for the local-LLM-feasibility rationale this
follows). Order matters: patterns are checked most-specific-first so a
query that could plausibly match two categories resolves to the more
distinctive one -- e.g. "Which projects have high delay risk?" contains
"risk" but is a PORTFOLIO query (ranked list), not a RISK query (single
project's SHAP drivers), because the RISK patterns require a much more
specific "why ... risk" shape than a bare "risk" keyword.

Every category here maps 1:1 to a tool in app.agent.tools. UNSUPPORTED is
not a failure mode -- it is the deliberately correct answer whenever no
pattern matches, so the agent never has to guess.
"""

from __future__ import annotations

import re

INTENT_PROJECT = "project"
INTENT_RISK = "risk"
INTENT_PORTFOLIO = "portfolio"
INTENT_DOCUMENT = "document"
INTENT_WHATIF = "whatif"
INTENT_SUPPORT = "support"
INTENT_UNSUPPORTED = "unsupported"

ALL_INTENTS = (
    INTENT_PROJECT,
    INTENT_RISK,
    INTENT_PORTFOLIO,
    INTENT_DOCUMENT,
    INTENT_WHATIF,
    INTENT_SUPPORT,
    INTENT_UNSUPPORTED,
)

# Checked in this exact order -- see module docstring.
_WHATIF_PATTERNS = [
    r"\bwhat happens if\b",
    r"\bwhat would happen if\b",
    r"\bwhat if\b",
]

_SUPPORT_PATTERNS = [
    r"\bhow do i\b",
    r"\bhow can i\b",
    r"\bhow to\b",
    r"\bhow does .+ work\b",
    r"\bwhat does .+ mean\b",
    r"\bwhat is (a |an )?(model prediction|what-?if|insufficient data|hri)\b",
]

_RISK_PATTERNS = [
    r"\bwhy is\b.*\brisk",
    r"\bwhy are\b.*\brisk",
    r"\bwhy .* high risk\b",
    r"\bwhy .* risky\b",
    r"\brisk driver",
    r"\brisk summary\b",
    r"\bwhy .* (delay|cost overrun)\b",
    r"\bwhat.?s driving\b",
]

_PORTFOLIO_PATTERNS = [
    r"\bwhich projects\b",
    r"\bdistribution\b",
    r"\bportfolio\b",
    r"\bhow many projects\b",
    r"\btop risk",
    r"\bsegment",
    r"\bby state\b",
    r"\bby contractor\b",
    r"\bby (project )?type\b",
    r"\btrend",
    r"\bacross the (portfolio|corpus)\b",
]

_PROJECT_PATTERNS = [
    r"\binformation about\b",
    r"\bdetails? (about|for|on)\b",
    r"\btell me about\b",
    r"\bstatus of\b",
    r"\bshow me\b",
]

_DOCUMENT_PATTERNS = [
    r"\bdocument",
    r"\breport",
    r"\bmention",
    r"\bsay about\b",
    r"\baccording to\b",
]

_RULES: list[tuple[str, list[str]]] = [
    (INTENT_WHATIF, _WHATIF_PATTERNS),
    (INTENT_SUPPORT, _SUPPORT_PATTERNS),
    (INTENT_RISK, _RISK_PATTERNS),
    (INTENT_PORTFOLIO, _PORTFOLIO_PATTERNS),
    (INTENT_PROJECT, _PROJECT_PATTERNS),
    (INTENT_DOCUMENT, _DOCUMENT_PATTERNS),
]


def classify_intent(message: str) -> str:
    """Returns one of ALL_INTENTS. Never raises, never returns a value
    outside that set. UNSUPPORTED is the correct, explicit result when no
    rule matches -- never a guess."""
    text = (message or "").lower()
    for intent, patterns in _RULES:
        if any(re.search(p, text) for p in patterns):
            return intent
    return INTENT_UNSUPPORTED
