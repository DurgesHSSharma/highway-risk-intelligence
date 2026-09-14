"""Phase 8 required answer mode: citation-grounded EXTRACTIVE answering,
built entirely from retrieved chunk text. No LLM involved, no paraphrasing,
no outside knowledge, no inference -- the top relevant chunk is returned
verbatim with its citation, or a fixed "not found" message when nothing
retrieved meets the relevance threshold.
"""

from __future__ import annotations

from app.rag.config import NOT_FOUND_MESSAGE
from app.rag.retrieval import RetrievalResponse


def build_extractive_answer(response: RetrievalResponse) -> str:
    if response.not_found or not response.results:
        return NOT_FOUND_MESSAGE

    top = response.results[0]
    flag_note = f", extraction quality flag: {top.quality_flag}" if top.quality_flag else ""
    header = f"From {top.citation()} (extraction method: {top.extraction_method}{flag_note}):"
    return f'{header}\n\n"{top.text}"'
