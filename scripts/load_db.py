"""Phase 6: load the Phase 2 synthetic dataset into the SQLite database.

Reads data/synthetic/highway_project_snapshots.csv and populates the
`projects` / `project_snapshots` tables (schema: backend/app/db/models.py).
Idempotent -- safe to run more than once; each run clears and reloads both
tables from the CSV (see backend/app/db/loader.py for the strategy
rationale) rather than upserting, so re-running never creates duplicates.

Phase 17B: this only ever clears/reloads `data_provenance == "SYNTHETIC"`
rows. Any USER_ENTERED project created through the app's project lifecycle
API is preserved untouched -- safe to run this after adding real projects.

Usage (from repo root, using the existing backend/.venv):
    ./backend/.venv/Scripts/python.exe -m scripts.load_db

Or (matching the `cd scripts` convention used by the Phase 2/3 scripts):
    cd scripts
    ../backend/.venv/Scripts/python.exe load_db.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"

# The SQLAlchemy models/engine/loader live under backend/app so the API and
# this loader share exactly one definition of the schema -- never redefine
# it here. backend/ is not on sys.path when this script is run from the
# repo root or from scripts/, so it must be added explicitly.
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import settings  # noqa: E402
from app.db.base import make_engine  # noqa: E402
from app.db.loader import (  # noqa: E402
    LoadSummary,
    count_duplicate_project_months,
    count_orphan_snapshots,
    load_database,
)

DEFAULT_CSV_PATH = REPO_ROOT / "data" / "synthetic" / "highway_project_snapshots.csv"


def _print_summary(summary: LoadSummary, orphans: int, duplicates: int) -> None:
    print(f"Source CSV: {summary.source_csv_path}")
    print(f"  rows: {summary.source_row_count:,}")
    print(f"  unique projects: {summary.source_unique_projects:,}")
    print(f"  unique (project_id, reporting_month) pairs: {summary.source_unique_project_month_pairs:,}")
    print()
    print("Loaded into database (SYNTHETIC rows only):")
    print(f"  projects: {summary.projects_loaded:,}")
    print(f"  project_snapshots: {summary.snapshots_loaded:,}")
    print()
    print("Preserved USER_ENTERED rows (never touched by this loader):")
    print(f"  projects: {summary.preserved_user_projects:,}")
    print(f"  project_snapshots: {summary.preserved_user_snapshots:,}")
    print()
    if summary.excluded_rows:
        print(f"EXCLUDED {summary.excluded_rows} source row(s): {summary.excluded_reason}")
    else:
        print("Excluded rows: 0")
    print(f"Orphan snapshots (project_id with no matching project): {orphans}")
    print(f"Duplicate (project_id, reporting_month) pairs: {duplicates}")
    print()
    ok = summary.reconciled and orphans == 0 and duplicates == 0
    print("RECONCILIATION: " + ("PASS -- database matches source CSV exactly." if ok else "FAIL -- see counts above."))
    if not ok:
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV_PATH)
    parser.add_argument(
        "--database-path",
        type=Path,
        default=None,
        help="Override the SQLite file path (defaults to Settings.database_path).",
    )
    args = parser.parse_args()

    engine = make_engine(f"sqlite:///{args.database_path.resolve().as_posix()}") if args.database_path else None
    if engine is None:
        print(f"Loading into {settings.database_file_path}")
    else:
        print(f"Loading into {args.database_path}")

    summary = load_database(args.csv, bind=engine)
    orphans = count_orphan_snapshots(bind=engine)
    duplicates = count_duplicate_project_months(bind=engine)
    _print_summary(summary, orphans, duplicates)


if __name__ == "__main__":
    main()
