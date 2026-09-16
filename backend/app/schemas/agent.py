"""Phase 17C "Ask HRI" request/response schemas.

`answer_type` mirrors the exact ACTUAL / PREDICTION / HYPOTHETICAL /
DOCUMENT_EVIDENCE / SUPPORT / UNSUPPORTED categories the master prompt
requires -- never blended. `predictions`/`citations` are populated only
when the matched intent actually produced them (e.g. a SUPPORT answer has
neither); this is a deliberately lean, purpose-built shape for the chat UI,
not a raw dump of the richer internal RiskSummaryResult/SimulationResult
dataclasses those come from.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ANSWER_TYPES = ("actual", "prediction", "hypothetical", "document_evidence", "support", "unsupported")

UNSUPPORTED_MESSAGE = "HRI does not have sufficient information to answer that."


class AgentQueryRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    project_id: str | None = Field(
        default=None,
        description="Optional page context (e.g. the project the user is currently viewing). Used only when "
        "the message text itself doesn't name a project.",
    )


class AgentPredictionOut(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_used: str | None = None
    significant_delay_probability: float | None = None
    final_delay_days_predicted: float | None = None
    cost_overrun_probability: float | None = None
    final_cost_overrun_pct_predicted: float | None = None
    actual_final_delay_days: int | None = None
    actual_significant_delay: int | None = None
    actual_cost_overrun: int | None = None
    actual_final_cost_overrun_pct: float | None = None


class AgentCitationOut(BaseModel):
    document_id: str
    page_number: int
    citation: str
    text: str


class AgentQueryResponse(BaseModel):
    answer_type: Literal["actual", "prediction", "hypothetical", "document_evidence", "support", "unsupported"]
    intent: str
    message: str
    project_id: str | None = None
    reporting_month: str | None = None
    predictions: AgentPredictionOut | None = None
    citations: list[AgentCitationOut] = []
    disclaimer: str | None = None
