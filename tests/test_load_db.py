"""Phase 6 loader tests, run at the repo root (mirrors the existing
tests/test_validate_dataset.py convention): uses a small synthetic dataset
generated on the fly, loaded into a throwaway temp SQLite file, so this
test never touches the real data/database/highway_risk.db.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import scripts.load_db  # noqa: F401  (adds backend/ to sys.path as a side effect)
from scripts.generate_dataset import generate_dataset

from app.db.base import make_engine  # noqa: E402
from app.db.loader import (  # noqa: E402
    count_duplicate_project_months,
    count_orphan_snapshots,
    load_database,
)


@pytest.fixture()
def small_csv(tmp_path: Path) -> Path:
    df = generate_dataset(n_projects=15, seed=7)
    csv_path = tmp_path / "small_snapshots.csv"
    df.to_csv(csv_path, index=False)
    return csv_path


@pytest.fixture()
def temp_engine(tmp_path: Path):
    db_path = tmp_path / "loader_test.db"
    return make_engine(f"sqlite:///{db_path.as_posix()}")


def test_load_database_reconciles_with_source_csv(small_csv: Path, temp_engine):
    raw = pd.read_csv(small_csv)
    summary = load_database(small_csv, bind=temp_engine)

    assert summary.projects_loaded == raw["project_id"].nunique()
    assert summary.snapshots_loaded == len(raw)
    assert summary.excluded_rows == 0
    assert summary.reconciled


def test_load_database_is_idempotent(small_csv: Path, temp_engine):
    first = load_database(small_csv, bind=temp_engine)
    second = load_database(small_csv, bind=temp_engine)

    assert first.projects_loaded == second.projects_loaded
    assert first.snapshots_loaded == second.snapshots_loaded
    assert count_duplicate_project_months(bind=temp_engine) == 0
    assert count_orphan_snapshots(bind=temp_engine) == 0


def test_load_database_no_orphan_snapshots(small_csv: Path, temp_engine):
    load_database(small_csv, bind=temp_engine)
    assert count_orphan_snapshots(bind=temp_engine) == 0


def test_load_database_missing_csv_raises_clear_error(tmp_path: Path, temp_engine):
    missing = tmp_path / "does_not_exist.csv"
    with pytest.raises(FileNotFoundError):
        load_database(missing, bind=temp_engine)
