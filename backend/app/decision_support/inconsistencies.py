"""Phase 11 potential-inconsistency scoping.

Phase 9's contradiction detector (`app.contradiction.detector`) is a single
global, corpus-wide pass -- it is not parameterized by project, so its raw
output cannot be "the inconsistencies for project X". This module reuses
that unchanged global result (`get_detection_summary()`, never recomputed
here) and narrows it to the flags relevant to *this specific request*: a
flag is included only if at least one of its two source chunks was actually
retrieved as documentary evidence for this project's evidence queries (see
app.decision_support.evidence). This is a filter over Phase 9's own already
-hedged output, not new contradiction-detection logic -- no flag's wording,
confidence, or status is altered.

If Phase 9 has zero global findings, or none of its findings touch this
request's retrieved evidence, the result is an explicit empty list -- never
manufactured.
"""

from __future__ import annotations

from app.contradiction.detector import ContradictionFlag, DetectionSummary


def scope_inconsistencies_to_evidence(
    summary: DetectionSummary, relevant_chunk_ids: set[str]
) -> list[ContradictionFlag]:
    if not relevant_chunk_ids:
        return []
    return [
        flag
        for flag in summary.flags
        if flag.chunk_a in relevant_chunk_ids or flag.chunk_b in relevant_chunk_ids
    ]
