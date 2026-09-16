"""Phase 17C intent classification tests (app.agent.intents) -- every
required category, plus deliberately ambiguous and unsupported queries.
"""

from __future__ import annotations

import pytest

from app.agent.intents import (
    ALL_INTENTS,
    INTENT_DOCUMENT,
    INTENT_PORTFOLIO,
    INTENT_PROJECT,
    INTENT_RISK,
    INTENT_SUPPORT,
    INTENT_UNSUPPORTED,
    INTENT_WHATIF,
    classify_intent,
)


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Show me information about HRI-0006.", INTENT_PROJECT),
        ("Tell me about HRI-0019", INTENT_PROJECT),
        ("Why is HRI-0006 high risk?", INTENT_RISK),
        ("What's driving the delay risk for HRI-0328?", INTENT_RISK),
        ("Which projects have high delay risk?", INTENT_PORTFOLIO),
        ("What is the risk distribution by state?", INTENT_PORTFOLIO),
        ("Show me the portfolio trend", INTENT_PORTFOLIO),
        ("What do the project documents say about this requirement?", INTENT_DOCUMENT),
        ("What does the CAG report mention about cost escalation?", INTENT_DOCUMENT),
        ("What happens if progress improves by 10%?", INTENT_WHATIF),
        ("What if cost increases by 5% for HRI-0006?", INTENT_WHATIF),
        ("How do I add a new highway?", INTENT_SUPPORT),
        ("How do I archive a project?", INTENT_SUPPORT),
        ("How can I run a what-if simulation?", INTENT_SUPPORT),
        ("Who will win the next election?", INTENT_UNSUPPORTED),
        ("What's the weather like today?", INTENT_UNSUPPORTED),
    ],
)
def test_classify_intent_matches_expected_category(message, expected):
    assert classify_intent(message) == expected


def test_classify_intent_never_returns_outside_the_known_set():
    for message in ["", "   ", "asdkjfh 1234 !!!", "HRI-0006"]:
        assert classify_intent(message) in ALL_INTENTS


def test_portfolio_wins_over_risk_for_a_plural_ranked_query():
    """'high delay risk' contains the word 'risk', but this is a
    portfolio-scale ranked-list query, not a single-project SHAP-driver
    query -- the distinctive 'which projects' phrase must win."""
    assert classify_intent("Which projects have high delay risk?") == INTENT_PORTFOLIO


def test_support_wins_over_document_for_a_how_to_about_reports():
    """'report' alone is a document-search keyword, but 'how do I' is a
    much more specific support signal and must be checked first."""
    assert classify_intent("How do I download a report?") == INTENT_SUPPORT


def test_ambiguous_ungrounded_query_is_unsupported():
    assert classify_intent("asdkjfh random gibberish 12345") == INTENT_UNSUPPORTED
