"""Phase 13 PDF report endpoint tests:
GET /projects/{project_id}/report.pdf?reporting_month=YYYY-MM.

Uses PyMuPDF (`fitz`) to parse the generated PDF and assert on its real
extracted text -- PyMuPDF is already a Phase 7 dependency (PDF ingestion),
so no new PDF-parsing dependency was added for these tests (see
docs/PHASE_13.md).
"""

from __future__ import annotations

import re

import fitz
import pytest

KNOWN_PROJECT_ID = "HRI-0006"
NON_TERMINAL_MONTH = "2022-12"
TERMINAL_MONTH = "2023-06"
UNKNOWN_PROJECT_ID = "HRI-9999"


def _pdf_text(pdf_bytes: bytes) -> str:
    """Extracts all text and collapses whitespace runs (including the line
    breaks PyMuPDF preserves at ReportLab's own word-wrap points) to single
    spaces, so a long sentence that wraps across PDF lines can still be
    matched as one contiguous substring."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        raw = "".join(page.get_text() for page in doc)
    finally:
        doc.close()
    return re.sub(r"\s+", " ", raw)


@pytest.fixture(scope="module")
def non_terminal_response(client):
    return client.get(f"/projects/{KNOWN_PROJECT_ID}/report.pdf", params={"reporting_month": NON_TERMINAL_MONTH})


@pytest.fixture(scope="module")
def terminal_response(client):
    return client.get(f"/projects/{KNOWN_PROJECT_ID}/report.pdf", params={"reporting_month": TERMINAL_MONTH})


def test_returns_200(non_terminal_response):
    assert non_terminal_response.status_code == 200


def test_content_type_is_pdf(non_terminal_response):
    assert non_terminal_response.headers["content-type"] == "application/pdf"


def test_response_body_is_non_zero(non_terminal_response):
    assert len(non_terminal_response.content) > 0


def test_response_has_pdf_signature(non_terminal_response):
    assert non_terminal_response.content[:5] == b"%PDF-"


def test_response_has_downloadable_filename(non_terminal_response):
    disposition = non_terminal_response.headers.get("content-disposition", "")
    assert "attachment" in disposition
    assert ".pdf" in disposition
    assert KNOWN_PROJECT_ID in disposition


def test_pdf_can_be_parsed_by_a_local_pdf_parser(non_terminal_response):
    # A genuinely malformed/fake PDF would raise here.
    doc = fitz.open(stream=non_terminal_response.content, filetype="pdf")
    assert doc.page_count >= 1
    doc.close()


def test_pdf_text_contains_project_id(non_terminal_response):
    text = _pdf_text(non_terminal_response.content)
    assert KNOWN_PROJECT_ID in text


def test_pdf_text_contains_reporting_month(non_terminal_response):
    text = _pdf_text(non_terminal_response.content)
    assert NON_TERMINAL_MONTH in text


def test_pdf_text_contains_real_project_fields(non_terminal_response, client):
    project = client.get(f"/projects/{KNOWN_PROJECT_ID}").json()
    text = _pdf_text(non_terminal_response.content)
    assert project["project_name"] in text
    assert project["highway_number"] in text
    assert project["state"] in text


def test_pdf_text_contains_real_snapshot_values(non_terminal_response, client):
    snapshot = client.get(f"/projects/{KNOWN_PROJECT_ID}/snapshots/{NON_TERMINAL_MONTH}").json()
    text = _pdf_text(non_terminal_response.content)
    assert f"{snapshot['land_acquisition_delay_days']:.0f}" in text or str(
        int(snapshot["land_acquisition_delay_days"])
    ) in text


def test_pdf_text_matches_live_prediction_source(non_terminal_response, client):
    """The PDF must use the same backend data as the on-screen risk-summary
    (brief requirement: 'PDF data matches the on-screen report source')."""
    risk = client.get(f"/projects/{KNOWN_PROJECT_ID}/risk-summary", params={"reporting_month": NON_TERMINAL_MONTH}).json()
    text = _pdf_text(non_terminal_response.content)
    assert re.sub(r"\s+", " ", risk["risk_summary"]["significant_delay_summary"]) in text
    assert re.sub(r"\s+", " ", risk["risk_summary"]["final_delay_days_summary"]) in text


def test_pdf_text_contains_disclaimers(non_terminal_response):
    text = _pdf_text(non_terminal_response.content)
    assert "prototype decision-support system" in text
    assert "SYNTHETIC" in text
    assert "not causation" in text


def test_pdf_text_contains_live_shap_section_for_non_terminal(non_terminal_response):
    text = _pdf_text(non_terminal_response.content)
    assert "SHAP" in text
    assert "Live model prediction" in text


def test_terminal_snapshot_returns_200(terminal_response):
    assert terminal_response.status_code == 200
    assert terminal_response.content[:5] == b"%PDF-"


def test_terminal_snapshot_shows_recorded_actual_outcome_not_prediction(terminal_response):
    text = _pdf_text(terminal_response.content)
    assert "Recorded actual outcome" in text
    assert "Live model prediction" not in text


def test_terminal_snapshot_does_not_fabricate_shap(terminal_response):
    text = _pdf_text(terminal_response.content)
    assert "Skipped: this snapshot is terminal" in text


def test_terminal_snapshot_does_not_fabricate_scenario(terminal_response):
    text = _pdf_text(terminal_response.content)
    assert "no live SHAP driver exists to anchor an illustrative what-if scenario" in text


def test_missing_project_returns_404(client):
    resp = client.get(f"/projects/{UNKNOWN_PROJECT_ID}/report.pdf", params={"reporting_month": NON_TERMINAL_MONTH})
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/json")


def test_malformed_reporting_month_returns_422(client):
    resp = client.get(f"/projects/{KNOWN_PROJECT_ID}/report.pdf", params={"reporting_month": "not-a-month"})
    assert resp.status_code == 422


def test_wellformed_but_nonexistent_reporting_month_returns_404(client):
    resp = client.get(f"/projects/{KNOWN_PROJECT_ID}/report.pdf", params={"reporting_month": "1999-01"})
    assert resp.status_code == 404


def test_missing_reporting_month_param_returns_422(client):
    resp = client.get(f"/projects/{KNOWN_PROJECT_ID}/report.pdf")
    assert resp.status_code == 422


def test_error_response_never_leaks_a_raw_stack_trace(client):
    resp = client.get(f"/projects/{UNKNOWN_PROJECT_ID}/report.pdf", params={"reporting_month": NON_TERMINAL_MONTH})
    body = resp.json()
    assert "Traceback" not in str(body)
    assert "File \"" not in str(body)
