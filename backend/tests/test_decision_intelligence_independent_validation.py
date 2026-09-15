"""Phase 15 independent math validation (master-prompt section 30):
recomputes real values from RAW data sources the app itself did not
produce (the committed CSV, the raw SHAP artifact JSON) rather than
calling the implementation under test and comparing it to itself.

- Peer historical rate: recomputed directly from
  data/synthetic/highway_project_snapshots.csv via pandas (never via
  app.analytics.segments.segment_report).
- Driver alignment: the live SHAP result is obtained by calling
  app.decision_support.shap_explainer.explain_instance directly (the
  already-independently-tested Phase 11 explainer, not
  app.decision_intelligence.driver_alignment), and the portfolio artifact
  is read with a raw `json.load` over docs/artifacts/shap_local_examples.json
  (never via app.analytics.drivers.portfolio_drivers), then the two are
  compared with the SAME `driver_identity` reduction the implementation
  uses (reusing that shared utility is legitimate -- it is the concept
  under test, not a shortcut around independent verification).
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from app.config import REPO_ROOT
from app.decision_intelligence.driver_alignment import compute_driver_alignment
from app.decision_intelligence.portfolio_context import get_peer_context
from app.decision_support.shap_explainer import driver_identity, explain_instance
from app.ml.features import build_predictor_row

CSV_PATH = REPO_ROOT / "data" / "synthetic" / "highway_project_snapshots.csv"
SHAP_ARTIFACT_PATH = REPO_ROOT / "docs" / "artifacts" / "shap_local_examples.json"

NON_TERMINAL_PROJECT_ID = "HRI-0006"
NON_TERMINAL_MONTH = "2022-12"


# --- 1. Peer historical rate, recomputed from the raw CSV ---


def test_peer_state_historical_rate_matches_raw_csv_independent_computation(db_session, _phase14_batch_scoring):
    df = pd.read_csv(CSV_PATH)
    terminal = df[df["project_status"] == "Completed"]

    target_state = "Telangana"
    state_rows = terminal[terminal["state"] == target_state]
    expected_n = len(state_rows)
    expected_delay_rate = state_rows["significant_delay"].mean()
    expected_cost_rate = state_rows["cost_overrun"].mean()

    peers = get_peer_context(db_session, state=target_state, project_type="Greenfield Highway", contractor=None)
    state_entry = peers["state"]

    assert state_entry.status == "ok"
    assert state_entry.segment.historical.project_count == expected_n
    assert state_entry.segment.historical.significant_delay_rate == pytest.approx(expected_delay_rate, abs=1e-9)
    assert state_entry.segment.historical.cost_overrun_rate == pytest.approx(expected_cost_rate, abs=1e-9)


def test_peer_contractor_historical_rate_matches_raw_csv_independent_computation(db_session, _phase14_batch_scoring):
    """`contractor` is a project-level STATIC field (see
    docs/API_AND_DATABASE.md 'Schema decisions'): the app resolves it from
    each project's first CSV row (app.db.loader.load_database uses
    `groupby("project_id").first()`), not from the terminal row alone. A
    real, disclosed synthetic-data quirk (project HRI-0084) has a NaN
    `contractor` value specifically on its OWN terminal row while its
    earlier rows correctly carry it -- so this independent recomputation
    must resolve `contractor` per-project the same documented way (first
    non-missing row), never by reading the terminal row's own contractor
    field directly, to be a correct independent check rather than an
    artifact of a naive CSV read."""
    df = pd.read_csv(CSV_PATH)
    project_contractor = df.sort_values("reporting_month").groupby("project_id", sort=False)["contractor"].first()

    target_contractor = "Malwa Builders Pvt Ltd"
    target_project_ids = set(project_contractor[project_contractor == target_contractor].index)

    terminal = df[df["project_status"] == "Completed"]
    rows = terminal[terminal["project_id"].isin(target_project_ids)]
    expected_n = len(rows)
    expected_delay_rate = rows["significant_delay"].mean()

    peers = get_peer_context(db_session, state="Telangana", project_type="Greenfield Highway", contractor=target_contractor)
    entry = peers["contractor"]

    assert entry.status == "ok"
    assert entry.segment.historical.project_count == expected_n
    assert entry.segment.historical.significant_delay_rate == pytest.approx(expected_delay_rate, abs=1e-9)


def test_portfolio_wide_historical_rate_matches_raw_csv_independent_computation(db_session, _phase14_batch_scoring):
    """Cross-checks app.analytics.historical.historical_overview (reused,
    unchanged, by app.decision_intelligence.recommendations) against a raw
    pandas computation over the full corpus."""
    from app.analytics.historical import historical_overview

    df = pd.read_csv(CSV_PATH)
    terminal = df[df["project_status"] == "Completed"]
    expected_delay_rate = terminal["significant_delay"].mean()
    expected_cost_rate = terminal["cost_overrun"].mean()
    expected_n = len(terminal)

    hist = historical_overview(db_session)
    assert hist.completed_project_count == expected_n
    assert hist.significant_delay_rate == pytest.approx(expected_delay_rate, abs=1e-9)
    assert hist.cost_overrun_rate == pytest.approx(expected_cost_rate, abs=1e-9)


# --- 2. Driver alignment for a real project, independently assembled ---


def test_driver_alignment_for_real_project_independently_assembled(db_session, _phase14_batch_scoring):
    # Independent live SHAP: call the Phase 11 explainer directly, not
    # through app.decision_intelligence at all.
    X = build_predictor_row(db_session, NON_TERMINAL_PROJECT_ID, NON_TERMINAL_MONTH)
    live_significant_delay = explain_instance("significant_delay", X)
    live_top = live_significant_delay.top_drivers[0]

    # Independent portfolio artifact: raw json.load, not
    # app.analytics.drivers.portfolio_drivers().
    with open(SHAP_ARTIFACT_PATH, encoding="utf-8") as f:
        raw_artifact = json.load(f)
    portfolio_ranking = raw_artifact["delay_classification"]["global_feature_ranking"]
    portfolio_top_raw = portfolio_ranking[0]["feature"]
    from app.decision_support.shap_explainer import clean_feature_name

    portfolio_top_cleaned = clean_feature_name(portfolio_top_raw)

    expected_live_identity = driver_identity(live_top.feature, live_top.raw_feature)
    expected_portfolio_identity = driver_identity(portfolio_top_cleaned, portfolio_top_raw)
    expected_agreement = expected_live_identity == expected_portfolio_identity

    # Now compare against the actual implementation's output for the same
    # real project/snapshot/task.
    from app.analytics.drivers import portfolio_drivers

    live_all = [explain_instance(t, X) for t in ("significant_delay", "final_delay_days", "cost_overrun", "final_cost_overrun_pct")]
    alignment = compute_driver_alignment(live_all, portfolio_drivers())
    sig_alignment = next(a for a in alignment if a.task_key == "significant_delay")

    assert sig_alignment.live_top_driver_identity == expected_live_identity
    assert sig_alignment.portfolio_top_driver_identity == expected_portfolio_identity
    assert sig_alignment.agreement == expected_agreement

    # Real, documented finding (see docs/ADVANCED_ANALYTICS.md and
    # docs/DECISION_SUPPORT.md): for HRI-0006/2022-12 the live top driver is
    # progress_efficiency, while the portfolio-wide top driver is
    # contractor_productivity_factor -- these genuinely differ, so
    # agreement is expected to be False for this specific real example.
    assert live_top.feature == "progress_efficiency"
    assert portfolio_top_cleaned == "contractor_productivity_factor"
    assert expected_agreement is False
