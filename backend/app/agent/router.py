"""Phase 17C "Ask HRI" orchestration (NOT the FastAPI HTTP router -- that's
app.routers.agent, which calls handle_query() below and returns its
result almost directly). Named router.py per the master prompt's file
list; think of it as the query router in the required flow:

    user message
      -> classify_intent (app.agent.intents)
      -> extract entities (app.agent.entities)
      -> validate required entity present (else return a clarification,
         answer_type="unsupported" -- never guess)
      -> call exactly one tool (app.agent.tools)
      -> build a grounded AgentQueryResponse (app.agent.synthesizer)

Every branch below either calls a real tool and reports its real output,
or returns a fixed, honest "not enough information" response -- there is
no path that fabricates a project, a number, a citation, or a document.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.agent import synthesizer, tools
from app.agent.entities import (
    extract_project_id,
    extract_reporting_month,
    extract_risk_level,
    extract_segment_dimension,
    parse_whatif_intent,
)
from app.agent.intents import (
    INTENT_DOCUMENT,
    INTENT_PORTFOLIO,
    INTENT_PROJECT,
    INTENT_RISK,
    INTENT_SUPPORT,
    INTENT_WHATIF,
    classify_intent,
)
from app.agent.support_kb import match_support_topic
from app.ml.features import FeatureConstructionError
from app.schemas.agent import (
    UNSUPPORTED_MESSAGE,
    AgentCitationOut,
    AgentPredictionOut,
    AgentQueryResponse,
)
from app.simulation.service import InvalidOverrideFieldsError

MISSING_PROJECT_CLARIFICATION = (
    "Which project would you like me to look at? Please include an HRI project ID such as HRI-0006."
)


def _unsupported(intent: str, message: str) -> AgentQueryResponse:
    return AgentQueryResponse(answer_type="unsupported", intent=intent, message=message)


def _resolve_project_id(message: str, context_project_id: str | None) -> str | None:
    return extract_project_id(message) or context_project_id


def handle_query(db: Session, message: str, context_project_id: str | None = None) -> AgentQueryResponse:
    intent = classify_intent(message)

    if intent == INTENT_SUPPORT:
        return AgentQueryResponse(answer_type="support", intent=intent, message=match_support_topic(message))

    if intent == INTENT_PROJECT:
        return _handle_project(db, message, context_project_id)

    if intent == INTENT_RISK:
        return _handle_risk(db, message, context_project_id)

    if intent == INTENT_WHATIF:
        return _handle_whatif(db, message, context_project_id)

    if intent == INTENT_PORTFOLIO:
        return _handle_portfolio(db, message)

    if intent == INTENT_DOCUMENT:
        return _handle_document(message)

    return _unsupported("unsupported", UNSUPPORTED_MESSAGE)


def _handle_project(db: Session, message: str, context_project_id: str | None) -> AgentQueryResponse:
    project_id = _resolve_project_id(message, context_project_id)
    if project_id is None:
        return _unsupported(INTENT_PROJECT, MISSING_PROJECT_CLARIFICATION)

    try:
        result = tools.lookup_project(db, project_id)
    except tools.ProjectNotFoundError:
        return _unsupported(INTENT_PROJECT, f"I couldn't find a project with ID '{project_id}'.")

    return AgentQueryResponse(
        answer_type="actual",
        intent=INTENT_PROJECT,
        message=synthesizer.render_project_answer(result),
        project_id=project_id,
    )


def _handle_risk(db: Session, message: str, context_project_id: str | None) -> AgentQueryResponse:
    project_id = _resolve_project_id(message, context_project_id)
    if project_id is None:
        return _unsupported(INTENT_RISK, MISSING_PROJECT_CLARIFICATION)

    reporting_month = extract_reporting_month(message)
    try:
        result = tools.get_risk_answer(db, project_id, reporting_month)
    except tools.ProjectNotFoundError:
        return _unsupported(INTENT_RISK, f"I couldn't find a project with ID '{project_id}'.")
    except tools.SnapshotNotFoundError as exc:
        return _unsupported(INTENT_RISK, str(exc))
    except FeatureConstructionError as exc:
        return _unsupported(
            INTENT_RISK,
            f"There isn't enough recorded data for {project_id} to build a model assessment yet. ({exc})",
        )

    is_actual = result.prediction_status == "actual_outcome"
    predictions = None
    if is_actual:
        predictions = AgentPredictionOut(
            actual_final_delay_days=result.predictions["final_delay_days"].actual_value,
            actual_significant_delay=result.predictions["significant_delay"].actual_value,
            actual_cost_overrun=result.predictions["cost_overrun"].actual_value,
            actual_final_cost_overrun_pct=result.predictions["final_cost_overrun_pct"].actual_value,
        )
    else:
        predictions = AgentPredictionOut(
            significant_delay_probability=result.predictions["significant_delay"].probability_of_significant_delay,
            final_delay_days_predicted=result.predictions["final_delay_days"].predicted_final_delay_days,
            cost_overrun_probability=result.predictions["cost_overrun"].probability_of_cost_overrun,
            final_cost_overrun_pct_predicted=result.predictions["final_cost_overrun_pct"].predicted_final_cost_overrun_pct,
        )

    citations = [
        AgentCitationOut(document_id=r.document_id, page_number=r.page_number, citation=r.citation(), text=r.text)
        for e in result.evidence
        if not e.not_found
        for r in e.results[:2]
    ]

    return AgentQueryResponse(
        answer_type="actual" if is_actual else "prediction",
        intent=INTENT_RISK,
        message=synthesizer.render_risk_answer(result),
        project_id=project_id,
        reporting_month=result.project.reporting_month,
        predictions=predictions,
        citations=citations,
        disclaimer=synthesizer.SYNTHETIC_DATA_DISCLAIMER_ACTUAL if is_actual else synthesizer.SYNTHETIC_DATA_DISCLAIMER_MODEL,
    )


def _handle_whatif(db: Session, message: str, context_project_id: str | None) -> AgentQueryResponse:
    project_id = _resolve_project_id(message, context_project_id)
    if project_id is None:
        return _unsupported(INTENT_WHATIF, MISSING_PROJECT_CLARIFICATION)

    whatif = parse_whatif_intent(message)
    if whatif is None:
        return _unsupported(
            INTENT_WHATIF,
            "I couldn't understand that what-if request. Try phrasing it like \"what happens if progress "
            f"improves by 10% for {project_id}\" or \"what happens if cost increases by 5%\".",
        )

    reporting_month = extract_reporting_month(message)
    try:
        result = tools.run_whatif(db, project_id, whatif, reporting_month)
    except tools.ProjectNotFoundError:
        return _unsupported(INTENT_WHATIF, f"I couldn't find a project with ID '{project_id}'.")
    except (tools.SnapshotNotFoundError, tools.NoNonTerminalSnapshotError, tools.TerminalSnapshotError) as exc:
        return _unsupported(INTENT_WHATIF, str(exc))
    except InvalidOverrideFieldsError as exc:
        return _unsupported(INTENT_WHATIF, str(exc))
    except FeatureConstructionError as exc:
        return _unsupported(
            INTENT_WHATIF,
            f"There isn't enough recorded data for {project_id} to run a what-if simulation yet. ({exc})",
        )

    return AgentQueryResponse(
        answer_type="hypothetical",
        intent=INTENT_WHATIF,
        message=synthesizer.render_whatif_answer(result, whatif),
        project_id=project_id,
        reporting_month=result.reporting_month,
        disclaimer=synthesizer.SYNTHETIC_DATA_DISCLAIMER_MODEL,
    )


def _handle_portfolio(db: Session, message: str) -> AgentQueryResponse:
    dimension = extract_segment_dimension(message)
    risk_level = extract_risk_level(message)
    shape, data = tools.get_portfolio_answer(db, dimension=dimension, risk_level=risk_level)
    return AgentQueryResponse(
        answer_type="prediction",
        intent=INTENT_PORTFOLIO,
        message=synthesizer.render_portfolio_answer(shape, data),
        disclaimer=synthesizer.SYNTHETIC_DATA_DISCLAIMER_MODEL,
    )


def _handle_document(message: str) -> AgentQueryResponse:
    response, answer_text = tools.search_documents(message)
    if response.not_found:
        return _unsupported(INTENT_DOCUMENT, answer_text)

    citations = [
        AgentCitationOut(document_id=r.document_id, page_number=r.page_number, citation=r.citation(), text=r.text)
        for r in response.results
    ]
    return AgentQueryResponse(
        answer_type="document_evidence",
        intent=INTENT_DOCUMENT,
        message=synthesizer.render_document_answer(answer_text),
        citations=citations,
    )
