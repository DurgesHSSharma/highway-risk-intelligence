"""Phase 14 independent math verification (brief section 35): at least two
analytics calculations, independently recomputed with pandas directly over
data/synthetic/highway_project_snapshots.csv, compared against the live
API response. This test does NOT call any app.analytics.* function for the
"expected" side -- only raw pandas over the source CSV -- so it is a
genuine independent check, not a tautological re-run of the same code.
"""

from __future__ import annotations

import pandas as pd
import pytest

from app.config import REPO_ROOT

DATASET_CSV_PATH = REPO_ROOT / "data" / "synthetic" / "highway_project_snapshots.csv"


def _one_row_per_project() -> pd.DataFrame:
    """Every outcome/state/type/contractor column is constant per
    project_id (see app/db/models.py docstring) -- taking the first row per
    project is a safe way to get exactly one row per project regardless of
    row order."""
    df = pd.read_csv(DATASET_CSV_PATH)
    return df.drop_duplicates(subset="project_id", keep="first")


def test_madhya_pradesh_historical_significant_delay_rate_matches_independent_pandas_computation(client):
    projects = _one_row_per_project()
    mp = projects[projects["state"] == "Madhya Pradesh"]
    assert len(mp) > 0
    expected_rate = mp["significant_delay"].mean()
    expected_count = len(mp)

    resp = client.get("/analytics/segments", params={"dimension": "state"})
    body = resp.json()
    entry = next(e for e in body["entries"] if e["value"] == "Madhya Pradesh")

    assert entry["historical"]["project_count"] == expected_count
    assert entry["historical"]["significant_delay_rate"] == pytest.approx(expected_rate, rel=1e-9)


def test_bridge_project_type_historical_mean_cost_overrun_pct_matches_independent_pandas_computation(client):
    projects = _one_row_per_project()
    bridges = projects[projects["project_type"] == "Bridge/ROB/Flyover"]
    assert len(bridges) > 0
    expected_mean_cost_overrun = bridges["final_cost_overrun_pct"].mean()
    expected_count = len(bridges)

    resp = client.get("/analytics/segments", params={"dimension": "project_type"})
    body = resp.json()
    entry = next(e for e in body["entries"] if e["value"] == "Bridge/ROB/Flyover")

    assert entry["historical"]["project_count"] == expected_count
    assert entry["historical"]["mean_final_cost_overrun_pct"] == pytest.approx(expected_mean_cost_overrun, rel=1e-9)


def test_portfolio_overview_mean_final_delay_days_matches_independent_pandas_computation(client):
    """A second, portfolio-wide independent check (not per-segment): the
    overall historical mean final delay days, computed straight from the
    CSV, must match the API's overview exactly."""
    projects = _one_row_per_project()
    expected_mean_delay = projects["final_delay_days"].mean()

    resp = client.get("/analytics/portfolio")
    hist = resp.json()["historical"]
    assert hist["mean_final_delay_days"] == pytest.approx(expected_mean_delay, rel=1e-9)
