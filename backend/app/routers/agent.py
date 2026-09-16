"""Phase 17C "Ask HRI" endpoint: POST /agent/query.

Thin HTTP layer -- all classification/routing/tool-calling logic lives in
app.agent.router.handle_query, which already converts every expected
failure (unknown project, insufficient data, unparseable what-if, no
matching intent) into a normal 200 response with
answer_type="unsupported" rather than an HTTP error. A malformed request
body (missing/empty `message`) is rejected at 422 by AgentQueryRequest's
own Pydantic validation, before this function ever runs.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agent.router import handle_query
from app.db.base import get_db
from app.schemas.agent import AgentQueryRequest, AgentQueryResponse

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/query", response_model=AgentQueryResponse)
def query(payload: AgentQueryRequest, db: Session = Depends(get_db)) -> AgentQueryResponse:
    return handle_query(db, payload.message, payload.project_id)
