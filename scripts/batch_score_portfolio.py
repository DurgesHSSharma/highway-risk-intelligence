"""Phase 14: batch-score every eligible non-terminal project's latest
snapshot through the Phase 6 model registry and write the results to the
`portfolio_prediction_cache` table (schema: backend/app/db/models.py).

This is the ONLY place portfolio analytics ever runs live ML inference --
GET /analytics/* endpoints read this cache, never scoring per request (see
docs/ADVANCED_ANALYTICS.md "Batch scoring architecture"). Re-run this
script whenever the underlying dataset or model artifacts change; it is
idempotent (clear-and-reload, same convention as scripts/load_db.py).

Usage (from repo root, using the existing backend/.venv):
    ./backend/.venv/Scripts/python.exe -m scripts.batch_score_portfolio

Requires the database to already be loaded (scripts/load_db.py) and the
Phase 4/5 model artifacts to be present (they are committed to git).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.analytics.batch_scoring import BatchScoringSummary, run_batch_scoring  # noqa: E402
from app.config import settings  # noqa: E402
from app.ml.registry import load_models  # noqa: E402


def _print_summary(summary: BatchScoringSummary) -> None:
    print(f"Database: {settings.database_file_path}")
    print(f"computed_at: {summary.computed_at.isoformat()}Z")
    print()
    print(f"Total projects in database: {summary.total_projects:,}")
    print(f"Eligible non-terminal projects (have >=1 non-terminal snapshot): {summary.eligible_projects:,}")
    print(f"Successfully scored: {summary.scored_projects:,}")
    print(f"Failed to score: {len(summary.failures):,}")
    if summary.failures:
        print()
        print("Failures (never fabricated -- excluded from the cache instead):")
        for f in summary.failures:
            print(f"  - {f.project_id} @ {f.reporting_month}: {f.reason}")
    print()
    if summary.eligible_projects == 0:
        print(
            "No eligible non-terminal projects found in the current dataset. "
            "Portfolio predicted-risk analytics will report as unavailable "
            "until at least one project has a non-terminal snapshot."
        )
    ok = summary.scored_projects == summary.eligible_projects
    print("RESULT: " + ("PASS -- every eligible project was scored." if ok else "PARTIAL -- see failures above."))


def main() -> None:
    print("Loading Phase 4/5 model artifacts...")
    load_models()
    print("Running batch scoring...")
    summary = run_batch_scoring()
    _print_summary(summary)


if __name__ == "__main__":
    main()
