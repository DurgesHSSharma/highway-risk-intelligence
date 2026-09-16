"""Phase 17C static support/how-to knowledge base for "Ask HRI".

Every answer here is hand-authored, fixed text describing THIS app's own
features -- never LLM-generated, never inferred. Matched by simple keyword
rules (checked in order, first match wins) rather than the main intent
classifier's patterns, since support topics need finer-grained routing
than the coarse intent categories in app.agent.intents.
"""

from __future__ import annotations

DEFAULT_SUPPORT_ANSWER = (
    "I can explain how to use HRI's project lifecycle and analysis features, but I couldn't match "
    "your question to a specific topic. Try asking, for example, \"How do I add a new project?\", "
    "\"How do I archive a project?\", or \"What is a what-if scenario?\"."
)

_TOPICS: list[tuple[list[str], str]] = [
    (
        ["add a project", "add new project", "add a new highway", "create a project", "create project"],
        "To add a project: go to the Projects page and click \"Add Project\", or navigate to /projects/new. "
        "You'll enter the government/project estimate information (name, highway number, state, contractor, "
        "length, contract value, planned dates). No ML risk assessment is possible until you add at least one "
        "monthly progress update, since the model needs real progress/cost data to build its input features.",
    ),
    (
        ["monthly update", "monthly progress", "progress update", "add a snapshot", "update progress"],
        "To add a monthly update: open the project's details page and click \"Add Monthly Update\". Enter that "
        "month's planned and actual physical/financial progress, cost figures, and delay factors. Only mark the "
        "status \"Completed\" once the project has actually finished -- that also requires the project's real "
        "final outcome (delay days, cost overrun), since a Completed snapshot records a known actual result.",
    ),
    (
        ["reactivate"],
        "To reactivate an archived project: open its details page (or the Projects list) and click "
        "\"Reactivate\". This clears the archived flag; the project's full history is unaffected, since "
        "archiving never deletes anything.",
    ),
    (
        ["archive a project", "archive project", "how do i archive", "deactivate a project", "archive"],
        "To archive a project: open its details page (or use the archive action in the Projects list) and "
        "click \"Archive\". This is non-destructive -- the project and all its history remain in the system, "
        "it's just marked archived and no longer treated as active. Use \"Reactivate\" to undo it.",
    ),
    (
        ["insufficient data"],
        "\"Insufficient data for model assessment\" means HRI's model doesn't yet have enough recorded monthly "
        "progress data for that project/month to build its required input features. This is never a fabricated "
        "prediction -- it's an honest \"not enough information yet\" state. Add a monthly progress update to "
        "make an assessment possible.",
    ),
    (
        ["model prediction", "what is a prediction", "how accurate"],
        "A model prediction is HRI's trained model's estimate for a project's delay/cost-overrun risk, computed "
        "from that project's own recorded progress and cost data. It is a statistical estimate, not a certainty "
        "or an official outcome -- it's always labeled separately from any actual recorded result.",
    ),
    (
        ["what-if", "what if scenario", "simulator", "hypothetical"],
        "The What-if Simulator re-scores a project's prediction under a hypothetical change you specify (e.g. "
        "\"what happens if progress improves by 10%\"), using the exact same model that serves real predictions. "
        "The result is always labeled hypothetical -- it is model re-scoring under an assumption, not a forecast "
        "of what will actually happen.",
    ),
    (
        ["document search", "search documents", "rag"],
        "Document Search retrieves relevant passages from HRI's corpus of real public highway-sector documents "
        "and shows them with their source citation (document + page). If nothing relevant is found, HRI says so "
        "explicitly rather than guessing.",
    ),
]


def match_support_topic(message: str) -> str:
    """Returns the matched topic's fixed answer, or DEFAULT_SUPPORT_ANSWER
    if nothing matches -- never empty, never fabricated."""
    text = (message or "").lower()
    for keywords, answer in _TOPICS:
        if any(kw in text for kw in keywords):
            return answer
    return DEFAULT_SUPPORT_ANSWER
