"""Phase 16 production-readiness tests: consistent `reporting_month`
validation across every router that accepts it.

Before this phase, only `reports.py` validated the `reporting_month` format
at the request layer (via a FastAPI `Query(..., pattern=...)`); `predictions.py`,
`simulation.py`, `decision_support.py`, and `decision_intelligence.py` each
accepted a bare `str`, so a malformed value fell through to a 404
("no snapshot found") instead of a 422 ("malformed input"). `reports.py`'s
own original pattern (`^\\d{4}-\\d{2}$`) was also looser than intended,
accepting an out-of-range month like "2025-13". All six usages (five
routers' query params + `projects.py`'s snapshot path param) now share one
pattern from `app.validation.MONTH_PATTERN`. See docs/PRODUCTION_READINESS.md.
"""

from __future__ import annotations

import pytest

KNOWN_PROJECT_ID = "HRI-0006"
NON_TERMINAL_MONTH = "2022-12"

INVALID_MONTHS = [
    "2025",
    "2025-9",
    "2025/09",
    "abc",
    "2025-99",
    "2025-00",
    "2025-13",
    "",
]


@pytest.mark.parametrize("reporting_month", INVALID_MONTHS)
def test_predict_rejects_malformed_reporting_month(client, reporting_month):
    resp = client.get(f"/projects/{KNOWN_PROJECT_ID}/predict", params={"reporting_month": reporting_month})
    assert resp.status_code == 422


@pytest.mark.parametrize("reporting_month", INVALID_MONTHS)
def test_simulate_rejects_malformed_reporting_month(client, reporting_month):
    resp = client.post(
        f"/projects/{KNOWN_PROJECT_ID}/simulate",
        params={"reporting_month": reporting_month},
        json={},
    )
    assert resp.status_code == 422


@pytest.mark.parametrize("reporting_month", INVALID_MONTHS)
def test_risk_summary_rejects_malformed_reporting_month(client, reporting_month):
    resp = client.get(f"/projects/{KNOWN_PROJECT_ID}/risk-summary", params={"reporting_month": reporting_month})
    assert resp.status_code == 422


@pytest.mark.parametrize("reporting_month", INVALID_MONTHS)
def test_decision_intelligence_rejects_malformed_reporting_month(client, reporting_month):
    resp = client.get(
        f"/projects/{KNOWN_PROJECT_ID}/decision-intelligence", params={"reporting_month": reporting_month}
    )
    assert resp.status_code == 422


@pytest.mark.parametrize("reporting_month", INVALID_MONTHS)
def test_report_pdf_rejects_malformed_reporting_month(client, reporting_month):
    resp = client.get(f"/projects/{KNOWN_PROJECT_ID}/report.pdf", params={"reporting_month": reporting_month})
    assert resp.status_code == 422


@pytest.mark.parametrize(
    "reporting_month",
    # Excludes "" (collapses the path segment entirely) and "2025/09" (a
    # literal "/" splits into two path segments, so it 404s at routing --
    # never reaches this endpoint's Path() validation at all; neither case
    # is a validation gap, just a different URL shape).
    [m for m in INVALID_MONTHS if m and "/" not in m],
)
def test_snapshot_path_param_rejects_malformed_reporting_month(client, reporting_month):
    resp = client.get(f"/projects/{KNOWN_PROJECT_ID}/snapshots/{reporting_month}")
    assert resp.status_code == 422


def test_predict_still_accepts_wellformed_reporting_month(client):
    resp = client.get(f"/projects/{KNOWN_PROJECT_ID}/predict", params={"reporting_month": NON_TERMINAL_MONTH})
    assert resp.status_code == 200


def test_snapshot_path_param_still_accepts_wellformed_reporting_month(client):
    resp = client.get(f"/projects/{KNOWN_PROJECT_ID}/snapshots/{NON_TERMINAL_MONTH}")
    assert resp.status_code == 200
