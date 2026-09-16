"""Phase 13 PDF report endpoint:
GET /projects/{project_id}/report.pdf?reporting_month=YYYY-MM.

Genuine backend-generated PDF (ReportLab/reportlab.platypus -- no jsPDF, no
html2canvas, no browser screenshot-to-PDF, no external PDF API). Built from
`app.reports.report_data.build_report_data`, which reuses the exact same
`app.decision_support.synthesizer.run_risk_summary` function the existing
`GET /projects/{id}/risk-summary` endpoint calls -- the PDF and the
on-screen Reports/AI Risk Summary pages are backed by the same data/
services, never a second prediction/SHAP/RAG pipeline. See
docs/PHASE_13.md.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.ml.features import FeatureConstructionError
from app.reports.pdf_builder import build_report_pdf
from app.reports.report_data import ProjectNotFoundError, SnapshotNotFoundError, build_report_data
from app.validation import MONTH_DESCRIPTION, MONTH_PATTERN

router = APIRouter(prefix="/projects", tags=["reports"])


@router.get("/{project_id}/report.pdf")
def get_project_report_pdf(
    project_id: str,
    reporting_month: str = Query(..., pattern=MONTH_PATTERN, description=MONTH_DESCRIPTION),
    db: Session = Depends(get_db),
) -> Response:
    try:
        data = build_report_data(db, project_id, reporting_month)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SnapshotNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FeatureConstructionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    pdf_bytes = build_report_pdf(data)
    filename = f"{project_id}_{reporting_month}_HRI_report.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
