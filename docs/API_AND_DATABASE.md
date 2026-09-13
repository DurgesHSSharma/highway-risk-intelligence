# Phase 6 — API and Database

*** Every number and behavior on this page was actually produced by running
the code in this repo (`scripts/load_db.py`, the FastAPI app under
`backend/app/`), not estimated or invented. ***

**This is a prototype decision-support system inspired by highway
infrastructure project monitoring, built on a SYNTHETIC dataset -- it is
not an official NHAI system.** See
[SYNTHETIC_DATA_METHODOLOGY.md](SYNTHETIC_DATA_METHODOLOGY.md).

## 1. Objective

Turn the Phase 2 synthetic highway-project CSV into a queryable SQLite
database, and expose it plus the already-trained Phase 4/5 models through a
FastAPI service. This phase adds **no new modeling** -- it is a data-access
and serving layer over frozen Phase 1-5 artifacts.

```
CSV -> SQLite -> SQLAlchemy -> FastAPI -> { Project CRUD, Snapshot retrieval, ML prediction }
```

## 2. Database architecture

**Engine:** SQLite (zero-cost, local, no server process). **ORM:**
SQLAlchemy 2.0. Location is configurable via `Settings.database_path`
(`backend/app/config.py`), default `data/database/highway_risk.db`
(repo-root-relative). The file matches the repository's existing `*.db`
`.gitignore` rule and is **not committed** -- it is fully reproducible from
the committed CSV via `scripts/load_db.py` in under 2 seconds, so keeping
it out of git avoids a redundant ~2-3MB binary with no review value.

SQLite disables foreign-key enforcement per connection by default;
`backend/app/db/base.py` issues `PRAGMA foreign_keys=ON` on every new
connection so the schema's FK/UNIQUE constraints are actually enforced,
not just declared.

## 3. Schema

### `projects` (400 rows -- one per `project_id`)

Columns constant within a `project_id` across all of its snapshots
(verified by inspection -- `df.groupby('project_id')[col].nunique()<=1`
for every column below, across the full 8,740-row source CSV):

| Column | Type | Notes |
|---|---|---|
| `project_id` | str, PK | e.g. `HRI-0001` |
| `data_provenance` | str | always `SYNTHETIC` in this dataset |
| `project_name`, `highway_number`, `state`, `project_type` | str | indexed (`state`, `project_type`) for the `GET /projects` filters |
| `contractor` | str, nullable | ~0.9% of projects (80/8,740 rows, but constant per project) have no recorded contractor |
| `project_length_km`, `original_contract_value_inr_cr` | float | |
| `planned_start_date`, `planned_completion_date` | date | |
| `planned_duration_months` | int | |

### `project_snapshots` (8,740 rows -- one per `(project_id, reporting_month)`)

Every other raw CSV column, because it varies by `reporting_month` within a
project. `UNIQUE(project_id, reporting_month)` and a `project_id ->
projects.project_id` foreign key are both enforced (verified in
`backend/tests/test_db_schema.py`).

Two schema decisions that deviate from the Phase 6 brief's *example* field
list, because the actual Phase 2 schema differs from the example:

- **`project_status` lives on `project_snapshots`, not `projects`.** It is
  NOT constant per project -- every project starts `"Ongoing"` and has
  exactly one terminal `"Completed"` row (verified: exactly 400 `Completed`
  rows in the source CSV, one per project). Putting a "status" column on
  `projects` would either be stale or require picking one row's value
  arbitrarily.
- **`final_delay_days`, `significant_delay`, `final_cost_overrun_pct`,
  `cost_overrun` live on `project_snapshots`, repeated on every row of a
  project**, even though they are constant per project. This mirrors the
  source CSV exactly (row-for-row, column-for-column reconciliation) and is
  what the terminal-snapshot prediction path reads directly off the
  matched row, per the brief's explicit instruction to preserve
  "target/outcome fields ... on the snapshots table."

The two exact-duplicate column pairs found during Phase 3 EDA
(`planned_expenditure_inr_cr` == `planned_cost_to_date_inr_cr`,
`expenditure_variance_pct` == `financial_progress_variance_pct`) are kept
in `project_snapshots` (unlike the Phase 3 *processed* feature files, which
drop them) -- this table's job is a faithful, reconcilable mirror of the
source CSV, not a leakage-audited model input.

Nullable columns match the source CSV's actual missingness exactly
(`contractor` 80 missing; `actual_financial_progress_pct` /
`financial_progress_variance_pct` / `actual_expenditure_inr_cr` /
`expenditure_variance_pct` 330 missing each; `variation_cost_inr_cr` 266
missing; `equipment_unavailability_days` 248 missing;
`weather_disruption_days` 241 missing). No column that is fully populated
in the source CSV was made nullable, and vice versa.

`is_terminal_snapshot` is stored (not computed at query time) as
`project_status == "Completed"`, identical to the Phase 3 definition in
`scripts/prepare_features.py`.

Full column list: [`backend/app/db/models.py`](../backend/app/db/models.py).

## 4. Loading process

`scripts/load_db.py` (thin CLI) delegates to `backend/app/db/loader.py`'s
`load_database()`, the single source of truth for the load logic (shared
with the test suite, so tests exercise the exact same code path as
production).

**Strategy: deterministic clear-and-reload, not upsert.** Every run
deletes all `project_snapshots` then all `projects` rows inside one
transaction, then reinserts everything fresh from the CSV. For a dataset
this size (400 projects / 8,740 rows) this is simpler and has fewer
failure modes than a column-by-column upsert diff, and is trivially
idempotent by construction: running it twice yields byte-identical row
counts every time (verified in `tests/test_load_db.py` and
`backend/tests/test_db_schema.py::test_loader_is_idempotent`).

Verified with the real dataset (`scripts/load_db.py` output, current run):

```
Source CSV rows: 8,740 | unique projects: 400 | unique (project,month) pairs: 8,740
Loaded: projects=400, project_snapshots=8,740
Excluded rows: 0
Orphan snapshots: 0
Duplicate (project_id, reporting_month) pairs: 0
RECONCILIATION: PASS
```

No source row was excluded for any reason -- every raw CSV column maps
directly onto either table.

Run it:
```
./backend/.venv/Scripts/python.exe -m scripts.load_db
```

## 5. Endpoints

All under the existing FastAPI app (`backend/app/main.py`) -- no second
app was created.

| Method | Path | Purpose |
|---|---|---|
| GET | `/projects` | Paginated project list; filters: `state`, `project_type`, `project_status` |
| GET | `/projects/{project_id}` | Project detail |
| GET | `/projects/{project_id}/snapshots` | All snapshots, ordered by `reporting_month` ascending |
| GET | `/projects/{project_id}/snapshots/{reporting_month}` | One snapshot |
| GET | `/projects/{project_id}/predict?reporting_month=YYYY-MM` | ML prediction or actual outcome (see [MODEL_SERVING.md](MODEL_SERVING.md)) |

### Pagination

`GET /projects` returns `{items, page, page_size, total}`. `page_size`
defaults to `Settings.default_page_size` (20) and is capped at
`Settings.max_page_size` (100).

### Filters and the `current_status` field

Every `ProjectOut` includes a computed `current_status`: the
`project_status` of that project's most-recent snapshot (max
`reporting_month` -- safe to compare as a string since `"YYYY-MM"` sorts
lexicographically the same as chronologically). `project_status` is not a
stored `projects` column (see section 3), so this is computed via a join
against a per-project `MAX(reporting_month)` subquery
(`app/routers/projects.py::_current_status_subquery`), not duplicated
data that could go stale.

**Known data characteristic, not a bug:** every project in this synthetic
dataset is simulated all the way through to completion, so every project's
*current_status* is `"Completed"`. Filtering `project_status=Ongoing`
correctly returns zero projects today; the filter logic itself is
verified against a project's actual per-snapshot status history.

### Error handling

- Unknown `project_id` on any endpoint -> `404` with a message naming the
  project.
- Unknown `reporting_month` for a known project -> `404` with a message
  naming both.
- Neither case reaches a `500` (covered by
  `backend/tests/test_projects_api.py`).

## 6. Prediction behavior summary

See [MODEL_SERVING.md](MODEL_SERVING.md) for the full model-serving
design. In short: terminal snapshots (`is_terminal_snapshot=true`) return
the recorded actual outcomes with `is_model_prediction=false`;
non-terminal snapshots run all four Phase 5 recommended models and return
`is_model_prediction=true`, always with a synthetic-data disclaimer.

## 7. Missing-feature behavior

Ordinary missingness in numeric predictor columns (e.g.
`actual_financial_progress_pct`, ~3.8% missing) is passed straight through
as `NaN` to the model's own saved `SimpleImputer` -- the API never invents
a replacement value. If a valid feature row genuinely cannot be
constructed, the endpoint returns `422` with a message describing what
could not be built (`backend/app/ml/features.py::FeatureConstructionError`),
never a `500` and never a silently-guessed prediction. Tested in
`backend/tests/test_missing_feature_handling.py`.
