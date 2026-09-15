"""Phase 6 database-layer tests: schema creation, CSV reconciliation,
uniqueness, loader idempotency, and orphan-row checks (brief section 21,
items 1-6)."""

from __future__ import annotations

import pandas as pd
from sqlalchemy import func, inspect, select

from app.config import REPO_ROOT
from app.db.base import engine
from app.db.loader import (
    count_duplicate_project_months,
    count_orphan_snapshots,
    load_database,
)
from app.db.models import Project, ProjectSnapshot

DATASET_CSV_PATH = REPO_ROOT / "data" / "synthetic" / "highway_project_snapshots.csv"


def test_schema_creates_expected_tables():
    table_names = set(inspect(engine).get_table_names())
    assert {"projects", "project_snapshots"}.issubset(table_names)


def test_project_snapshots_has_unique_constraint():
    constraints = inspect(engine).get_unique_constraints("project_snapshots")
    col_sets = [set(c["column_names"]) for c in constraints]
    assert {"project_id", "reporting_month"} in col_sets


def test_project_snapshots_has_foreign_key_to_projects():
    fks = inspect(engine).get_foreign_keys("project_snapshots")
    assert any(
        fk["referred_table"] == "projects" and fk["constrained_columns"] == ["project_id"]
        for fk in fks
    )


def test_project_count_matches_source_csv(db_session):
    raw = pd.read_csv(DATASET_CSV_PATH)
    expected_projects = raw["project_id"].nunique()
    actual_projects = db_session.execute(select(func.count()).select_from(Project)).scalar_one()
    assert actual_projects == expected_projects == 400


def test_snapshot_count_matches_source_csv(db_session):
    raw = pd.read_csv(DATASET_CSV_PATH)
    actual_snapshots = db_session.execute(select(func.count()).select_from(ProjectSnapshot)).scalar_one()
    assert actual_snapshots == len(raw) == 8740


def test_no_duplicate_project_month_combinations():
    assert count_duplicate_project_months() == 0


def test_no_orphan_snapshots():
    assert count_orphan_snapshots() == 0


def test_loader_is_idempotent(_phase6_test_database):
    first = _phase6_test_database
    second = load_database(DATASET_CSV_PATH)

    assert second.projects_loaded == first.projects_loaded
    assert second.snapshots_loaded == first.snapshots_loaded
    assert second.reconciled
    assert count_duplicate_project_months() == 0
    assert count_orphan_snapshots() == 0

    # Phase 14: load_database() now also clears `portfolio_prediction_cache`
    # before `projects` (FK-safety fix, see app/db/loader.py) -- this is the
    # only test in the suite that reloads the database mid-session, so it
    # must restore the cache afterward for later Phase 14 tests that expect
    # it populated (session-scoped fixture, populated once at session start).
    from app.analytics.batch_scoring import run_batch_scoring

    run_batch_scoring()


def test_loader_reconciles_with_source_csv(_phase6_test_database):
    summary = _phase6_test_database
    assert summary.excluded_rows == 0
    assert summary.reconciled
