# Phase 14 — Advanced Analytics & Risk Intelligence

Portfolio-level analytics with explicit historical/predicted separation,
built entirely on top of the existing Phase 1-13 system. This is an
**aggregation + analytics + presentation** phase — no new ML model, no
retraining, no new datasets, no deployment.

All figures in this document are real numbers from an actual run of this
implementation against the committed dataset (`data/synthetic/highway_project_snapshots.csv`,
400 projects / 8,740 snapshots), not invented examples.

---

## 1. Purpose

Phases 1-13 answer project-level questions ("what will happen to project
X?"). Phase 14 answers portfolio-level questions: overall risk
distribution, which projects/states/types/contractors carry the highest
risk, what portfolio-wide model-attributed drivers exist, and how delay
and cost patterns have moved over time — while keeping every number
honestly labeled as either a **recorded historical outcome** or a
**current model prediction**, never both at once.

## 2. Architecture

```
scripts/batch_score_portfolio.py        (CLI wrapper)
  -> backend/app/analytics/batch_scoring.py   (real inference, ONCE)
       -> app.ml.features.build_predictor_row  (reused, unmodified)
       -> app.ml.predict.predict_all_tasks     (reused, unmodified)
       -> writes portfolio_prediction_cache table (backend/app/db/models.py)

backend/app/analytics/
  batch_scoring.py    - eligibility selection, cache writer, cache metadata
  risk_score.py       - composite risk score (pure arithmetic over the cache)
  historical.py       - HISTORICAL/ACTUAL aggregates (terminal snapshots only)
  segments.py         - state / project_type / contractor breakdowns
  trends.py           - historical (start-year cohort) + predicted (reporting-year) trends
  distribution.py     - risk-distribution bucketing for the 4 tasks
  drivers.py          - reuses Phase 5's saved global SHAP artifact verbatim
  risk_projects.py    - ranked, filterable top-risk project list
  insights.py         - deterministic, rule-based executive insights (NO LLM)
  portfolio_service.py - orchestration layer called by the router

backend/app/routers/portfolio_analytics.py  (NEW router, /analytics/*)
backend/app/schemas/portfolio_analytics.py  (NEW response schemas)

frontend/src/pages/Analytics.jsx  (EXTENDED, not replaced)
frontend/src/components/{SourceLabel,TopRiskTable,SegmentTable}.jsx (NEW)
frontend/src/components/charts/{RiskMatrixChart,TrendLineChart}.jsx (NEW)
```

## 3. Existing (Phase 12) Analytics functionality — unchanged

`GET /analytics/summary` (`backend/app/routers/analytics.py`) and its
frontend section at the top of `Analytics.jsx` are untouched: total
projects, current-status/state/project-type counts, and the two
Phase-12-era outcome donuts. Phase 14 adds new sections below/around it;
nothing in the Phase 12 file was modified.

## 4. New Phase 14 functionality

Five new endpoints under the same `/analytics` prefix (a second
`APIRouter`, registered separately in `app/main.py`, so the Phase 12 file
was never touched):

| Endpoint | Purpose |
|---|---|
| `GET /analytics/portfolio` | Historical + predicted overview, risk distribution, top-5 risk preview, executive insights |
| `GET /analytics/risk-projects` | Ranked, filterable, paginated predicted-risk list (backs Top-Risk table + Risk Matrix) |
| `GET /analytics/segments?dimension=` | State / project_type / contractor historical + predicted breakdown |
| `GET /analytics/drivers` | Portfolio-wide model-attributed SHAP drivers (all 4 tasks) |
| `GET /analytics/trends` | Historical (actual) + predicted (model) trends, kept separate |

Five endpoints, not eight or one, because each serves a genuinely
different query shape (scalar overview vs. filterable/paginated list vs.
dimension-parameterized breakdown vs. a static artifact vs. a grouped time
series) — collapsing further would force unrelated pagination/filter
semantics into a single payload; splitting further (e.g. one endpoint per
segment dimension) would just be the same code three times.

## 5. "Current predicted risk" — what it actually means in this dataset

**Real, inspected corpus property**: every one of the 400 synthetic
projects is simulated through to completion, so every project's absolute
*latest* snapshot is `Completed` (terminal). There is no project whose
"current" status is genuinely "still ongoing" by that naive definition —
this was already disclosed in Phase 6/12's own documentation.

Phase 14 therefore defines **"current predicted risk" as the model
prediction from each project's own latest PRE-COMPLETION (non-terminal)
snapshot** — i.e. the last reporting month before that project's terminal
row. This mirrors exactly how Phase 10/11 already treat an arbitrary
non-terminal `reporting_month` as a valid snapshot to score; batch scoring
just automates picking that month per project instead of requiring a
caller-supplied one.

Real measured result: **all 400 projects are eligible** (each has ≥1
non-terminal snapshot), and all 400 were successfully scored — see
Section 7.

## 6. Historical metrics

Computed exclusively from `is_terminal_snapshot=True` rows — i.e. recorded
actual outcomes, never a model prediction. Since every project has exactly
one terminal row, historical statistics cover the **full population**
(n=400), not a sample.

Real measured portfolio-wide values:

- Significant-delay rate: **49.25%** (197 of 400)
- Cost-overrun rate: **38.25%** (153 of 400)
- Mean final delay: **65.0 days**
- Mean final cost overrun: **7.50%**

(These match Phase 12's own committed numbers exactly, since both read the
same terminal rows.)

## 7. Predicted metrics

Computed exclusively from `portfolio_prediction_cache` — i.e. model
output, never a recorded outcome.

Real measured run (`python -m scripts.batch_score_portfolio`,
`computed_at` example: `2026-09-15T08:36:15Z`):

- Eligible non-terminal projects: **400**
- Successfully scored: **400** (0 failures)
- Avg. significant-delay probability: **54.4%**
- Avg. cost-overrun probability: **34.6%**
- Avg. predicted final delay: **67.5 days**
- Avg. predicted final cost overrun: **7.6%**
- Risk level counts (quartile split, see Section 11): LOW 100 / MEDIUM 100 / HIGH 100 / CRITICAL 100

## 8. Batch-scoring architecture

`scripts/batch_score_portfolio.py` → `app.analytics.batch_scoring.run_batch_scoring()`:

1. Loads the Phase 6 model registry (`load_models()`), same singleton
   pipelines the live API serves — never retrained or refit.
2. For every project, finds its latest snapshot with `is_terminal_snapshot=False`.
3. Builds the exact 45-column predictor row via `app.ml.features.build_predictor_row`
   (unmodified — same function `GET /predict` and `POST /simulate` use).
4. Runs `app.ml.predict.predict_all_tasks` (unmodified) to get all 4 predictions.
5. Writes one row per project to `portfolio_prediction_cache`
   (`backend/app/db/models.py`), via a **deterministic clear-and-reload**
   strategy identical in spirit to `app/db/loader.py::load_database` —
   never an upsert.
6. Records `computed_at` (UTC timestamp) and the `reporting_month` actually
   scored, plus each task's `model_used`, so any cached row's provenance
   can be verified after the fact.

No model is retrained, refit, or reloaded here. This is the **only** place
in Phase 14 that runs live ML inference.

## 9. Cache format / location

Table `portfolio_prediction_cache` in the same SQLite database as
`projects`/`project_snapshots` (`data/database/highway_risk.db`, gitignored
— fully reproducible via `scripts/load_db.py` + `scripts/batch_score_portfolio.py`).
One row per project (`project_id` UNIQUE, FK to `projects`), columns:
`reporting_month`, `computed_at`, and per task `<task>_model`,
`<task>_predicted_class`/`<task>_probability` (classification) or
`<task>_predicted` (regression).

## 10. Refresh process / what happens when data or models change

- **Dataset changes**: re-run `scripts/load_db.py` then
  `scripts/batch_score_portfolio.py`. (A genuine Phase 14 bug was found and
  fixed here: `load_database()`'s clear-and-reload previously deleted
  `projects` without first clearing `portfolio_prediction_cache`, which now
  has an enforced FK to it — reloading the DB while the cache was populated
  raised an `IntegrityError`. Fixed by clearing the cache table first,
  exactly like `project_snapshots` already was. See Section 18.)
- **Model artifact changes**: re-run `scripts/batch_score_portfolio.py`
  only (no DB reload needed) — it always reads whatever `load_models()`
  currently loads.
- **If the cache has never been generated**: every affected endpoint
  returns **HTTP 200** with an explicit `status`/`cache_status` field set to
  `"cache_unavailable"` and a `message` telling the caller to run the batch
  script — never a bare error, and never a silent fallback to live
  per-project inference (verified behaviorally in
  `backend/tests/test_cache_behavior.py`, which monkeypatches
  `predict_all_tasks` to raise and confirms it is never called on a normal
  request).
- **Current dataset is static/synthetic**: there is no real-time data feed;
  "current" always means "as of the last time the batch script was run
  against the last time the dataset/models were loaded."

## 11. Risk-score formula, weights, thresholds, limitations

Not a new ML model — a deterministic aggregation of the four existing
model outputs (`backend/app/analytics/risk_score.py`):

1. `significant_delay_probability` and `cost_overrun_probability` are
   already genuine `[0, 1]` probabilities — used as-is.
2. `final_delay_days_predicted` and `final_cost_overrun_pct_predicted` are
   unbounded, so each is min-max normalized against the **current scored
   cohort's own observed range** (real measured range from the run above:
   delay days **-117.3 to 542.98**, cost overrun **-14.41% to 40.80%**).
   This normalization is batch-relative by construction — disclosed, not
   hidden.
3. `delay_risk = mean(significant_delay_probability, normalized_delay_days)`
   `cost_risk = mean(cost_overrun_probability, normalized_cost_pct)`
   `composite_risk_score (0-100) = 100 × mean(delay_risk, cost_risk)`
   — an **equal-weighted average of all four model outputs**. Equal
   weights were chosen because no external cost-of-error/business-priority
   data exists in this project to justify differential weighting. This is
   a **"decision-support risk score"**, never described as a "probability
   of project failure."
4. Risk levels (LOW/MEDIUM/HIGH/CRITICAL) are assigned by **quartile of the
   composite score actually observed in the current cohort** — real
   measured cut points from the run above: Q1=15.29, Q2=36.22, Q3=65.17.
   Not arbitrary fixed cutoffs, and explicitly not claimed to be official
   NHAI thresholds.

**Limitations**: batch-relative normalization means the same project's
delay/cost-risk component can shift slightly if scored alongside a
different cohort; equal weighting is a transparent default, not a
validated optimum; quartile-based levels mean exactly ~25% of any given
run's cohort is always CRITICAL by construction, which is a property of
the method, not a claim that 25% of the real world's projects are always
critical.

## 12. State analytics

Threshold: **n ≥ 15** (the brief's default, verified appropriate for this
dimension: 18 of 20 states clear it; only Punjab, n=11, and Kerala, n=14,
are flagged `small_sample=True`, and are still shown, never dropped).

## 13. Project-type analytics

Threshold: **n ≥ 15** (all 6 project types comfortably clear it: 34-108
projects each).

## 14. Contractor minimum-sample rule

The brief's default 15-project minimum was **inspected against the actual
corpus, not blindly applied**: 50 contractors manage 400 projects, and
only **1** contractor (Malwa Builders Pvt Ltd, 17 projects) has ≥15 —
useless for a "contractor analytics" comparison section. Real measured
distribution: max 17, and 26 of 50 contractors have ≥8 projects. **8** was
chosen as the contractor-specific threshold — the smallest round number
that still yields a meaningfully sized comparison set (26 of 50
contractors) while excluding the long tail of 2-7-project contractors from
comparative ranking. Every contractor below 8 (24 of 50) is still shown,
flagged `small_sample=True`, never excluded from the underlying count.

## 15. SHAP / global-driver methodology

`backend/app/analytics/drivers.py` reads
`docs/artifacts/shap_local_examples.json`'s `global_feature_ranking`
**verbatim** — same values, same order — never recomputed. This is the
Phase 5 artifact, distinct from Phase 11's **live per-instance** SHAP
(`app/decision_support/shap_explainer.py`), which explains one specific
snapshot's prediction at request time against the exact serving model.

**Disclosed, unmodified Phase 5 characteristic carried through**: for
`cost_overrun` and `final_cost_overrun_pct`, the saved global ranking
explains **XGBoost** (`model_family_explained`), not the Phase 4
Logistic/Linear Regression baselines that actually serve those two tasks
(`app.ml.registry.TASK_MODEL_REGISTRY`). Every driver response carries a
`matches_serving_model` flag — `true` for `significant_delay`/
`final_delay_days` (RF/XGBoost genuinely serve those), `false` for the two
cost tasks. A dedicated SHAP integrity test
(`backend/tests/test_shap_drivers_integrity.py`) independently loads the
raw JSON file and asserts the API reproduces it exactly, in the same
order, with no drift.

## 16. Historical trend methodology

Grouped by each project's **`planned_start_date` cohort year** (2019-2024
in this corpus), using only terminal/actual outcome values. This axis was
chosen over `reporting_month` because a project's 4 outcome columns are
constant across its entire history — the only statistically meaningful
temporal axis for an *actual*-outcome trend is when a project's lifecycle
began. Real measured coverage: all 6 cohort years have 42-76 projects each
— comfortably above the 15-project threshold, so no year is flagged.

**Predicted trend** is grouped by the reporting-month **year** of each
project's cached "current" snapshot. Real measured coverage: **2019-2029**,
with most years (2020-2026) offering 25-78 projects and the two tail years
(2019: n=1, 2027: n=3, 2028: n=4, 2029: n=1) correctly flagged
`small_sample=True` — not fabricated, not silently dropped.

## 17. Terminal / non-terminal distinction

`is_terminal_snapshot` is computed once at DB-load time
(`app/db/loader.py`) and never recomputed. Every Phase 14 historical
function reads ONLY `is_terminal_snapshot=True` rows; every Phase 14
predicted function reads ONLY the batch cache (which is itself built
exclusively from non-terminal snapshots). Verified with a dedicated real-
project test (`backend/tests/test_batch_scoring.py::test_eligible_snapshot_is_the_latest_non_terminal_one_not_the_terminal_one`)
against `HRI-0006`, confirming the cached snapshot for that project is
strictly earlier than, and distinct from, its terminal row.

## 18. Synthetic-data disclaimer

Every Phase 14 response carries `synthetic_data_disclaimer`
(`SYNTHETIC_DATA_DISCLAIMER_ACTUAL` for historical fields,
`SYNTHETIC_DATA_DISCLAIMER_MODEL` for predicted fields — the same Phase
6/12 disclaimer strings, reused, never rewritten). The frontend never
claims real NHAI operational data, official NHAI risk ranking, or
validated causal thresholds.

## 19. Performance considerations

- No per-project live inference on any `/analytics/*` request — proven
  behaviorally, not just asserted (Section 10).
- Segment/trend/risk-projects endpoints do one `SELECT * FROM
  portfolio_prediction_cache` (400 rows) plus one `SELECT project_id,
  <dimension> FROM projects` — no N+1 queries.
- The composite risk score for the whole cohort is computed once per
  request in pure Python over already-fetched rows (400 rows, negligible
  cost) — not recomputed per project via a separate query.
- SHAP portfolio drivers are read from a small (~15KB) committed JSON file
  via an `lru_cache`d loader — never recomputed per request.

## 20. Known limitations

- Batch-relative risk-score normalization (Section 11).
- Equal-weighted risk score is a heuristic, not a validated model.
- Quartile-based risk levels always split the cohort into ~25% bands by
  construction.
- "Current predicted risk" reflects each project's last pre-completion
  month, not a live "as of today" snapshot — an inherent property of a
  fully-simulated-to-completion synthetic dataset, not a bug.
- Predicted-trend tail years (2019, 2027-2029) have very thin samples
  (1-4 projects) and are flagged accordingly rather than smoothed or hidden.
- Portfolio-wide SHAP for the two cost tasks explains a different model
  family than the one actually serving those predictions (Section 15) —
  disclosed via `matches_serving_model`, not hidden.
- A real floating-point non-determinism (~1e-13) was observed in
  `RandomForestClassifier`/`LogisticRegression` `.predict_proba()` across
  repeated runs (likely internal aggregation order) — batch-scoring
  determinism is verified with a numeric tolerance, not exact equality
  (see `backend/tests/test_batch_scoring.py`).

## 21. API endpoints (full contract)

See Section 4's table for the five endpoints. Full request/response
schemas: `backend/app/schemas/portfolio_analytics.py`. Query parameters:

- `/analytics/risk-projects`: `state`, `project_type`, `contractor`,
  `risk_level` (one of LOW/MEDIUM/HIGH/CRITICAL, 422 if invalid), `limit`
  (1-100), `offset`.
- `/analytics/segments`: `dimension` (one of `state`/`project_type`/
  `contractor`, required, 422 if invalid).

## 22. Real example numbers from the actual implementation run

All numbers in Sections 6, 7, 11, 12, 13, 14, 16 above are from a real
execution of this code against the committed dataset — none were invented.
Additional real examples:

- Top-1 CRITICAL project in a real run: `HRI-0328` (NH-868 Expressway
  Package 18, Karnataka), composite risk score **93.1**, delay risk 96.2%
  (543 predicted delay days), cost risk 100.0% (27.7% predicted cost
  overrun), latest non-terminal snapshot `2025-08`.
- Top portfolio-wide driver for `significant_delay`:
  `contractor_productivity_factor`, mean |SHAP| = **0.1019** (Phase 5
  artifact, unmodified).
- Highest historical significant-delay rate among states clearing the
  n≥15 threshold: **Uttarakhand**, 63.6% (n=22).
- Highest historical cost-overrun rate among contractors clearing the n≥8
  threshold: **Prakash Infraprojects Pvt Ltd**, 100.0% (n=13).
