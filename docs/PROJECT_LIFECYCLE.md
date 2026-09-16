# Phase 17B: Project Lifecycle Management

Turns the previously read-only project system (Phases 1-16: every row came
from `scripts/load_db.py` clearing and reloading the synthetic CSV) into a
lifecycle-aware system: a user can add a real project, edit it, archive/
reactivate it, and record monthly progress -- without ever risking the
existing synthetic dataset or fabricating a prediction the model can't
actually support yet.

## Schema changes (`backend/app/db/models.py`)

- `Project.is_archived: bool` (default `False`) + `Project.archived_at:
  datetime | None`. Archiving is **non-destructive**: it never deletes a
  project or any of its snapshots/predictions, it only flips this flag.
  There is no delete endpoint anywhere in this feature by design.
- `ProjectSnapshot`'s four outcome columns (`final_delay_days`,
  `significant_delay`, `final_cost_overrun_pct`, `cost_overrun`) are now
  **nullable**. The SYNTHETIC dataset always knows these (the whole
  trajectory is simulated up front), so every SYNTHETIC row -- terminal or
  not -- still has them populated exactly as before Phase 17B. A real
  USER_ENTERED project's non-terminal snapshot legitimately has no known
  final outcome yet; these stay `NULL` until the project is actually marked
  `Completed` with real recorded results.
- A DB-enforced `CheckConstraint` (`ck_terminal_outcomes_populated`) makes
  it impossible to insert a row with `is_terminal_snapshot=true` and any of
  the four outcome columns `NULL` -- a genuine invariant, not just a
  docstring promise. It cannot verify the values are *actually* recorded
  outcomes rather than a guess -- that discipline lives entirely in
  `app/projects/lifecycle.py`, the only write path for a terminal
  USER_ENTERED snapshot.
- `Project.data_provenance` (pre-existing column) is reused, not
  duplicated: `"SYNTHETIC"` for the Phase 2 dataset, `"USER_ENTERED"` for
  anything created through this feature (`app/db/models.py::
  DATA_PROVENANCE_SYNTHETIC` / `DATA_PROVENANCE_USER_ENTERED`).

Since SQLAlchemy's `create_all()` never alters an existing table, the local
`data/database/highway_risk.db` file was deleted and rebuilt fresh via
`scripts/load_db.py` + `scripts/batch_score_portfolio.py` when this schema
landed (documented here since it's a one-time step for a dev machine, not
something rerun automatically).

## Loader safety (`backend/app/db/loader.py`, `scripts/load_db.py`)

The clear-and-reload strategy `load_database()` uses was previously
unconditional: `DELETE FROM project_snapshots; DELETE FROM projects;` then
bulk-insert from the CSV. That would have silently destroyed every
USER_ENTERED project the first time anyone reran the loader (something
routine after any dataset/schema change).

Every delete in `load_database()` is now scoped to `data_provenance ==
"SYNTHETIC"` rows only -- via a subquery selecting synthetic project ids,
applied to `portfolio_prediction_cache`, `project_snapshots`, and
`projects` in that order (matching the pre-existing FK-safe delete
ordering). A USER_ENTERED project, its snapshots, and its cached
prediction are never touched, however many times the loader reruns.
`LoadSummary` gained `preserved_user_projects` / `preserved_user_snapshots`
counts so this is visible in the CLI output, not just asserted internally.

Proven by `tests/test_loader_preserves_user_projects.py`: insert a
USER_ENTERED project directly (bypassing the lifecycle API, so the
guarantee is tested independently of it), rerun the loader three times,
confirm the project survives every time and the synthetic rows are still
correctly replaced.

## Lifecycle service (`backend/app/projects/lifecycle.py`)

Typed operations, same convention as `app.simulation.service` /
`app.decision_support.synthesizer` -- typed exceptions here, HTTP
translation only in the router:

- `create_project` -- auto-generates the next `HRI-NNNN` id (max numeric
  suffix across ALL existing projects, SYNTHETIC and USER_ENTERED alike,
  so it can never collide with either) or validates a caller-supplied one
  against the same `HRI-NNNN` pattern; rejects a duplicate id (409);
  validates `planned_completion_date > planned_start_date`.
- `update_project` -- partial edit (`model_dump(exclude_unset=True)`) of
  project-level fields. `project_id` and `data_provenance` are not
  editable (neither is a field on `ProjectUpdate`).
- `archive_project` / `reactivate_project` -- idempotent, non-destructive.
- `add_monthly_snapshot` -- the one operation with real business rules:
  1. The four actual-outcome fields are **required** when
     `project_status="Completed"` and **forbidden** otherwise (a plain
     monthly update can never carry them -- enforced here, not just by the
     nullable column).
  2. Once a project has a terminal snapshot, no further monthly update is
     accepted (mirrors the synthetic dataset's own "exactly one terminal
     row per project" invariant that the rest of this app already assumes
     everywhere -- analytics, decision support, etc.).
  3. Duplicate `(project_id, reporting_month)` -> 409 (the existing
     `UNIQUE` constraint backs this up at the DB level too).
  4. `physical_progress_variance_pct` / `financial_progress_variance_pct`
     are derived (`actual - planned`), never asked of the caller.
     `planned_expenditure_inr_cr` / `expenditure_variance_pct` are the
     schema's pre-existing exact-duplicate columns (see
     `app/db/models.py`) -- populated from the single caller-supplied
     `planned_cost_to_date_inr_cr` / the derived financial variance,
     never asked for twice.
  5. Rejected on an archived project (reactivate first).

## API (`backend/app/routers/project_lifecycle.py`)

```
POST   /projects                          create
PATCH  /projects/{project_id}             edit
POST   /projects/{project_id}/archive
POST   /projects/{project_id}/reactivate
POST   /projects/{project_id}/snapshots   monthly progress update
```

A separate router object from the pre-existing read-only
`app/routers/projects.py`, same convention Phase 14 already used for
`portfolio_analytics.py` alongside `analytics.py`. `reporting_month`
reuses `app.validation.MONTH_PATTERN` -- no second regex defined.

`GET /projects` (pre-existing, unmodified endpoint) gained one additive,
optional `is_archived` filter and switched its status-join from INNER to
LEFT OUTER: a just-created project has zero snapshots until its first
monthly update, and was previously invisible in the list (the inner join
silently excluded it) until then.

## Insufficient-data prediction behavior

`GET /projects/{id}/predict` already raised `FeatureConstructionError` ->
HTTP 422 when a full feature row couldn't be built (Phase 6). That's now
surfaced as `prediction_status="insufficient_data"` with HTTP 200 instead
-- an expected data-completeness state (most commonly a very new project),
never a client error and never a fabricated prediction. All four task
results come back empty (`SignificantDelayResult()` etc. with every field
`None`). `prediction_status` is now `Literal["actual_outcome",
"model_prediction", "insufficient_data"]`; the existing two values are
completely unchanged for every pre-existing caller.

In practice this state is rare once a snapshot exists: a single real
monthly update already supplies every one of the 45 predictor columns
(`app.ml.features.build_predictor_row`'s rolling features use
`min_periods=1`), so the genuinely common "insufficient data" case is a
project with **zero** snapshots at all -- which still 404s at
`GET /predict` exactly as before (a snapshot for the requested month truly
doesn't exist, which is different from "a snapshot exists but can't yield
a full feature row").

`GET /risk-summary`, `GET /decision-intelligence`, and `POST /simulate`
were deliberately **not** changed to the same 200/insufficient_data
contract in this phase -- they still return their existing 422 on the same
underlying error. The frontend never routes to those richer pages from a
project with no snapshots yet (the Project Details page's own
insufficient-data empty state is the gate), so the existing 422 there
remains a correct "expected 4xx for an expected error" response; extending
the richer contract to those endpoints is future scope, not silently
dropped.

## Frontend

- `pages/ProjectForm.jsx` (routes `/projects/new`, `/projects/:id/edit`) --
  shared create/edit form.
- `pages/Projects.jsx` -- "Add Project" button, an Active/Archived
  "Lifecycle" filter, and per-row Edit/Archive/Reactivate actions.
- `pages/ProjectDetails.jsx` -- Edit/Archive/Reactivate buttons, an
  archived badge, and `components/MonthlySnapshotForm.jsx` (toggleable,
  reused from both the normal snapshot card and the insufficient-data
  empty state).
- `components/StateViews.jsx::EmptyState`/`AsyncSection` gained an
  optional `action` / `emptyAction` node so the insufficient-data state can
  carry an "Add Monthly Update" call to action -- additive, every existing
  caller is unaffected.
- `api/client.js` gained `apiPatch` (the only new verb needed).

## Known limitations

- No authentication (unchanged from Phase 16 -- explicitly deferred,
  still a local single-user MVP). These are the first mutating endpoints
  in the app, but they carry the same posture as everything else.
- Portfolio analytics / Decision Intelligence context lag a newly added
  project until `scripts/batch_score_portfolio.py` is rerun manually --
  the same pre-existing, disclosed limitation Phase 14 already documents
  for the synthetic data, now also reachable via this feature.
- `state` / `project_type` are free-text on create/edit (not restricted to
  the values already present in the corpus), so a new project can
  introduce a state or type with no historical peers to compare against in
  Analytics/Decision Intelligence -- an honest consequence of not
  inventing a closed enum the brief didn't ask for, not a bug.
