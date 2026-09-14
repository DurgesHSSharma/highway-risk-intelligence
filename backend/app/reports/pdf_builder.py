"""Phase 13: renders a `ReportData` (see app.reports.report_data) into a
genuine PDF using ReportLab/reportlab.platypus -- no jsPDF, no
html2canvas/browser-screenshot, no external PDF API. Every value rendered
here comes from the existing backend data already validated/returned by
`run_risk_summary` and the `Project`/`ProjectSnapshot` rows -- nothing is
recomputed or fabricated. A value the backend doesn't have is rendered as
"Not available", never invented or substituted.
"""

from __future__ import annotations

import io
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.reports.report_data import ReportData
from app.schemas.decision_support import DisclaimersOut
from app.schemas.simulation import SIMULATION_DISCLAIMER

NAVY = colors.HexColor("#0f2a4a")
MUTED = colors.HexColor("#5a6472")
LIGHT_ROW = colors.HexColor("#f2f5f8")
BORDER = colors.HexColor("#d5dce3")

_NA = "Not available"


def _fmt(value, suffix: str = "", digits: int = 1) -> str:
    if value is None:
        return _NA
    if isinstance(value, float):
        return f"{value:.{digits}f}{suffix}"
    return f"{value}{suffix}"


def _styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("HRITitle", parent=styles["Title"], textColor=NAVY, fontSize=18, spaceAfter=2))
    styles.add(ParagraphStyle("HRITagline", parent=styles["Normal"], textColor=MUTED, fontSize=9, spaceAfter=10))
    styles.add(ParagraphStyle("HRIMeta", parent=styles["Normal"], textColor=MUTED, fontSize=8.5))
    styles.add(
        ParagraphStyle("HRISection", parent=styles["Heading2"], textColor=NAVY, fontSize=12.5, spaceBefore=14, spaceAfter=6)
    )
    styles.add(
        ParagraphStyle("HRISubsection", parent=styles["Heading3"], textColor=NAVY, fontSize=10.5, spaceBefore=8, spaceAfter=3)
    )
    styles.add(ParagraphStyle("HRIBody", parent=styles["Normal"], fontSize=9.5, leading=13))
    styles.add(ParagraphStyle("HRIDisclaimer", parent=styles["Normal"], fontSize=7.8, leading=10.5, textColor=MUTED))
    return styles


def _kv_table(pairs: list[tuple[str, str]], col_widths=(4.5 * cm, 4.5 * cm)) -> Table:
    """Two-column key/value grid, wrapped into a 2x2-cell-per-row layout so
    long report sections stay compact (label | value | label | value)."""
    rows = []
    for i in range(0, len(pairs), 2):
        left = pairs[i]
        right = pairs[i + 1] if i + 1 < len(pairs) else ("", "")
        rows.append([left[0], left[1], right[0], right[1]])
    table = Table(rows, colWidths=[3.0 * cm, col_widths[0], 3.0 * cm, col_widths[1]])
    table.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("TEXTCOLOR", (0, 0), (0, -1), MUTED),
                ("TEXTCOLOR", (2, 0), (2, -1), MUTED),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, LIGHT_ROW]),
            ]
        )
    )
    return table


def _header(styles, data: ReportData) -> list:
    project = data.project
    generated = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z")
    return [
        Paragraph("HRI — Highway Risk Intelligence", styles["HRITitle"]),
        Paragraph("PREDICT DELAYS • CONTROL COSTS — Prototype decision-support report, not an official NHAI report.", styles["HRITagline"]),
        Paragraph(f"<b>Risk Summary Report — {project.project_id}</b>", styles["HRISection"]),
        Paragraph(
            f"{project.project_name} &middot; Reporting month {data.risk.project.reporting_month} &middot; Generated {generated}",
            styles["HRIMeta"],
        ),
        Spacer(1, 8),
    ]


def _project_info_section(styles, data: ReportData) -> list:
    p, s = data.project, data.snapshot
    pairs = [
        ("Project ID", p.project_id),
        ("Project Name", p.project_name),
        ("Highway", p.highway_number),
        ("State", p.state),
        ("Project Type", p.project_type),
        ("Contractor", p.contractor or _NA),
        ("Reporting Month", s.reporting_month),
        ("Project Status", s.project_status),
        ("Length (km)", _fmt(p.project_length_km)),
        ("Original Contract Value (Cr)", _fmt(p.original_contract_value_inr_cr, digits=0)),
        ("Planned Start", str(p.planned_start_date)),
        ("Planned Completion", str(p.planned_completion_date)),
    ]
    return [Paragraph("Project Information", styles["HRISection"]), _kv_table(pairs), Spacer(1, 4)]


def _progress_section(styles, data: ReportData) -> list:
    s = data.snapshot
    pairs = [
        ("Planned Physical Progress (%)", _fmt(s.planned_physical_progress_pct)),
        ("Actual Physical Progress (%)", _fmt(s.actual_physical_progress_pct)),
        ("Physical Progress Variance (pp)", _fmt(s.physical_progress_variance_pct)),
        ("Planned Financial Progress (%)", _fmt(s.planned_financial_progress_pct)),
        ("Actual Financial Progress (%)", _fmt(s.actual_financial_progress_pct)),
        ("Financial Progress Variance (pp)", _fmt(s.financial_progress_variance_pct)),
    ]
    return [Paragraph("Planned vs. Actual Progress", styles["HRISection"]), _kv_table(pairs), Spacer(1, 4)]


def _cost_section(styles, data: ReportData) -> list:
    s = data.snapshot
    pairs = [
        ("Planned Cost to Date (Cr)", _fmt(s.planned_cost_to_date_inr_cr)),
        ("Actual Cost to Date (Cr)", _fmt(s.actual_cost_to_date_inr_cr)),
        ("Planned Expenditure (Cr)", _fmt(s.planned_expenditure_inr_cr)),
        ("Actual Expenditure (Cr)", _fmt(s.actual_expenditure_inr_cr)),
        ("Expenditure Variance (%)", _fmt(s.expenditure_variance_pct)),
        ("Material Cost (Cr)", _fmt(s.material_cost_inr_cr)),
        ("Labour Cost (Cr)", _fmt(s.labour_cost_inr_cr)),
        ("Equipment Cost (Cr)", _fmt(s.equipment_cost_inr_cr)),
        ("Variation Cost (Cr)", _fmt(s.variation_cost_inr_cr)),
        ("Delay-Related Cost (Cr)", _fmt(s.delay_related_cost_inr_cr)),
    ]
    return [Paragraph("Cost Information", styles["HRISection"]), _kv_table(pairs), Spacer(1, 4)]


def _delay_section(styles, data: ReportData) -> list:
    s = data.snapshot
    pairs = [
        ("Land Acquisition Delay (days)", _fmt(s.land_acquisition_delay_days, digits=0)),
        ("Utility Shifting Delay (days)", _fmt(s.utility_shifting_delay_days, digits=0)),
        ("Environment Clearance Delay (days)", _fmt(s.environment_clearance_delay_days, digits=0)),
        ("Material Delay (days)", _fmt(s.material_delay_days, digits=0)),
        ("Labour Shortage Delay (days)", _fmt(s.labour_shortage_days, digits=0)),
        ("Equipment Unavailability (days)", _fmt(s.equipment_unavailability_days, digits=0)),
        ("Weather Disruption (days)", _fmt(s.weather_disruption_days, digits=0)),
        ("Traffic Diversion Delay (days)", _fmt(s.traffic_diversion_delay_days, digits=0)),
        ("Design Change Delay (days)", _fmt(s.design_change_delay_days, digits=0)),
        ("Approval Delay (days)", _fmt(s.approval_delay_days, digits=0)),
    ]
    return [Paragraph("Delay Information", styles["HRISection"]), _kv_table(pairs), Spacer(1, 4)]


def _predictions_section(styles, data: ReportData) -> list:
    risk = data.risk
    is_actual = risk.prediction_status == "actual_outcome"
    rs = risk.risk_summary
    flow = [Paragraph("Model Prediction Outputs", styles["HRISection"])]
    for title, sentence in [
        ("Significant Delay", rs.significant_delay_summary),
        ("Delay Duration", rs.final_delay_days_summary),
        ("Cost Overrun", rs.cost_overrun_summary),
        ("Cost Overrun %", rs.final_cost_overrun_pct_summary),
    ]:
        # `sentence` already states "Recorded actual outcome (terminal
        # snapshot...)" verbatim for a terminal snapshot (see
        # app.decision_support.risk_summary._terminal_risk_summary) -- only
        # prepend a status label for the live-model-prediction case, to
        # avoid stating "recorded actual outcome" twice.
        label = "" if is_actual else "<i>(Live model prediction)</i> "
        flow.append(Paragraph(f"<b>{title}:</b> {label}{sentence}", styles["HRIBody"]))
        flow.append(Spacer(1, 2))
    flow.append(Spacer(1, 4))
    return flow


def _shap_section(styles, data: ReportData) -> list:
    risk = data.risk
    flow = [Paragraph("Current-Instance SHAP Risk Drivers", styles["HRISection"])]
    if not risk.risk_drivers:
        flow.append(Paragraph(risk.shap_skipped_reason or _NA, styles["HRIBody"]))
        return flow

    for task in risk.risk_drivers:
        flow.append(Paragraph(f"{task.label} — {task.model_used} ({task.explainer_type})", styles["HRISubsection"]))
        rows = [["Rank", "Feature", "SHAP value", "Direction", "Explanation"]]
        for d in task.top_drivers:
            rows.append([str(d.rank), d.feature, f"{d.shap_value:+.4f}", d.direction, Paragraph(d.explanation, styles["HRIBody"])])
        table = Table(rows, colWidths=[1.2 * cm, 3.3 * cm, 2.3 * cm, 2.3 * cm, 6.4 * cm])
        table.setStyle(
            TableStyle(
                [
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_ROW]),
                ]
            )
        )
        flow.append(table)
        flow.append(Spacer(1, 6))
    return flow


def _evidence_section(styles, data: ReportData) -> list:
    flow = [Paragraph("Documentary Evidence (RAG)", styles["HRISection"])]
    for item in data.risk.evidence:
        flow.append(Paragraph(f"Query: &ldquo;{item.query}&rdquo;", styles["HRISubsection"]))
        if item.not_found:
            flow.append(Paragraph("Not found in the available documents.", styles["HRIBody"]))
            continue
        flow.append(Paragraph(item.answer, styles["HRIBody"]))
        for r in item.results:
            flow.append(Paragraph(f"&bull; {r.citation()} [{r.quality_flag or 'ok'}]", styles["HRIDisclaimer"]))
        flow.append(Spacer(1, 4))
    return flow


def _inconsistencies_section(styles, data: ReportData) -> list:
    flags = data.risk.inconsistencies
    flow = [Paragraph("Potential Inconsistencies", styles["HRISection"])]
    if not flags:
        flow.append(
            Paragraph(
                "No potential inconsistencies surfaced for this evidence. This is not a claim that the "
                "underlying documents are free of inconsistencies -- only that none were flagged for the "
                "evidence retrieved here.",
                styles["HRIBody"],
            )
        )
        return flow
    for f in flags:
        flow.append(Paragraph(f.description, styles["HRIBody"]))
        flow.append(
            Paragraph(
                f"{f.document_a} p.{f.page_a} (&ldquo;{f.raw_claim_a}&rdquo;) vs. {f.document_b} p.{f.page_b} "
                f"(&ldquo;{f.raw_claim_b}&rdquo;) — confidence: {f.confidence}",
                styles["HRIDisclaimer"],
            )
        )
        flow.append(Spacer(1, 4))
    return flow


def _scenario_section(styles, data: ReportData) -> list:
    risk = data.risk
    flow = [Paragraph("Illustrative What-If Scenario", styles["HRISection"])]
    if risk.scenario is None:
        flow.append(Paragraph(risk.scenario_skipped_reason or _NA, styles["HRIBody"]))
        return flow

    sc = risk.scenario
    flow.append(
        Paragraph(
            f"{sc.label} — <b>{sc.field}</b> moved to its training-partition mean ({sc.reference_value:.3f}).",
            styles["HRIBody"],
        )
    )
    rows = [["Metric", "Baseline", "Simulated"]]
    base, sim = sc.baseline_predictions, sc.simulated_predictions
    rows.append(
        [
            "Delay probability",
            _fmt(base["significant_delay"].probability_of_significant_delay, digits=3),
            _fmt(sim["significant_delay"].probability_of_significant_delay, digits=3),
        ]
    )
    rows.append(
        [
            "Delay days",
            _fmt(base["final_delay_days"].predicted_final_delay_days),
            _fmt(sim["final_delay_days"].predicted_final_delay_days),
        ]
    )
    rows.append(
        [
            "Cost overrun probability",
            _fmt(base["cost_overrun"].probability_of_cost_overrun, digits=3),
            _fmt(sim["cost_overrun"].probability_of_cost_overrun, digits=3),
        ]
    )
    rows.append(
        [
            "Cost overrun %",
            _fmt(base["final_cost_overrun_pct"].predicted_final_cost_overrun_pct),
            _fmt(sim["final_cost_overrun_pct"].predicted_final_cost_overrun_pct),
        ]
    )
    table = Table(rows, colWidths=[6 * cm, 4 * cm, 4 * cm])
    table.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_ROW]),
            ]
        )
    )
    flow.append(table)
    flow.append(Spacer(1, 3))
    flow.append(Paragraph(SIMULATION_DISCLAIMER, styles["HRIDisclaimer"]))
    return flow


def _disclaimers_section(styles) -> list:
    d = DisclaimersOut()
    flow = [Paragraph("Disclaimers", styles["HRISection"])]
    for text in [
        d.system_identity,
        d.ml_limitation,
        d.causality_limitation,
        d.scenario_limitation,
        d.evidence_limitation,
        d.inconsistency_limitation,
        d.synthetic_data_disclaimer,
    ]:
        flow.append(Paragraph(text, styles["HRIDisclaimer"]))
        flow.append(Spacer(1, 3))
    return flow


def build_report_pdf(data: ReportData) -> bytes:
    """Renders `data` into a complete PDF document and returns the raw PDF
    bytes. Terminal snapshots render recorded actual outcomes (never a
    forward-looking prediction) because `data.risk` already encodes that
    distinction via `prediction_status`/`risk_drivers`/`scenario` being
    empty/None -- this function only renders what's there, it never decides
    terminal-vs-live itself."""
    styles = _styles()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=1.8 * cm,
        rightMargin=1.8 * cm,
        topMargin=1.6 * cm,
        bottomMargin=1.6 * cm,
        title=f"HRI Risk Summary Report — {data.project.project_id}",
        author="HRI — Highway Risk Intelligence",
    )

    story: list = []
    story += _header(styles, data)
    story += _project_info_section(styles, data)
    story += _progress_section(styles, data)
    story += _cost_section(styles, data)
    story += _delay_section(styles, data)
    story += _predictions_section(styles, data)
    story += _shap_section(styles, data)
    story += _evidence_section(styles, data)
    story += _inconsistencies_section(styles, data)
    story += _scenario_section(styles, data)
    story += _disclaimers_section(styles)

    doc.build(story)
    return buffer.getvalue()
