"""Shared Phase 6 test fixtures.

Tests must never touch the real `data/database/highway_risk.db` used by a
locally running API -- `DATABASE_PATH` is pointed at a throwaway temp file
*before* `app.config` (and therefore the app's SQLAlchemy engine) is first
imported by any test module, since pydantic-settings reads env vars once at
`Settings()` construction. This module is a conftest.py, so pytest imports
it before collecting sibling test files, which is early enough.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TEST_DB_DIR = Path(tempfile.mkdtemp(prefix="hri_phase6_test_db_"))
os.environ["DATABASE_PATH"] = str(_TEST_DB_DIR / "test_highway_risk.db")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import REPO_ROOT, settings  # noqa: E402
from app.db.loader import load_database  # noqa: E402
from app.main import app  # noqa: E402
from app.ml.registry import load_models  # noqa: E402

DATASET_CSV_PATH = REPO_ROOT / "data" / "synthetic" / "highway_project_snapshots.csv"


@pytest.fixture(scope="session", autouse=True)
def _phase6_test_database():
    """Loads the real Phase 2 CSV into the temp SQLite DB, and loads the
    real Phase 4/5 model artifacts, exactly once for the whole test
    session -- never per test (resource-conscious: some RF artifacts are
    12-31MB)."""
    assert "test" in str(settings.database_file_path).lower(), (
        "Refusing to run Phase 6 tests against a non-test database path: "
        f"{settings.database_file_path}"
    )
    summary = load_database(DATASET_CSV_PATH)
    load_models()
    yield summary


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(scope="session")
def db_session():
    from app.db.base import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
