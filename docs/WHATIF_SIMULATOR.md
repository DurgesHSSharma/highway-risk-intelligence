# Phase 10 — What-If Scenario Simulator

*** This phase adds **no new modeling**. It re-scores the same frozen
Phase 4/5 model artifacts (`app.ml.registry.TASK_MODEL_REGISTRY`) and the
same Phase 3 feature-engineering pipeline (`app.ml.features.build_predictor_row`)
that `GET /projects/{project_id}/predict` already uses -- nothing is
retrained, refit, or reimplemented. ***

**This is a prototype decision-support system inspired by highway
infrastructure project monitoring, built on a SYNTHETIC dataset -- it is
not an official NHAI system.** See
[SYNTHETIC_DATA_METHODOLOGY.md](SYNTHETIC_DATA_METHODOLOGY.md).

## 1. Purpose

Let a caller ask "what would the model predict for this real project
snapshot if one or more of its permitted predictor features had a
different, hypothetical value?" This is **model re-scoring under a
hypothetical assumption**, not a forecast, not a causal estimate, and not a
real-world intervention simulator. See section 15 for the exact boundary.

## 2. Endpoint

```
POST /projects/{project_id}/simulate?reporting_month=YYYY-MM
```

Request body: a flat JSON object mapping permitted predictor field names to
their new ABSOLUTE values. All existing endpoints (`GET /projects`,
`/projects/{id}`, `/projects/{id}/snapshots`, `/projects/{id}/snapshots/{month}`,
`/projects/{id}/predict`, `/documents/search`, `/documents/inconsistencies`)
are unchanged -- this phase is purely additive.

## 3. Request schema

```json
{
  "land_acquisition_delay_days": 45,
  "contractor_productivity_factor": 0.6
}
```

- Every key must be one of the 45 permitted predictor columns (section 6).
- Every value must be an ABSOLUTE value of the correct type: a real number
  (`int`/`float`, never `bool`) for a numeric predictor, a string for a
  categorical one (`state`, `project_type`, `contractor`).
- The body may be empty (`{}`) -- the simulated prediction then equals the
  baseline prediction (see `test_simulation_baseline_matches_predict_endpoint_with_no_overrides`
  in `backend/tests/test_simulation_api.py`, which uses exactly this to
  prove baseline/`GET /predict` consistency).

## 4. Response schema

```json
{
  "project_id": "HRI-0006",
  "reporting_month": "2022-12",
  "is_terminal_snapshot": false,
  "overrides": [
    {"field": "land_acquisition_delay_days", "original_value": 12.0, "simulated_value": 45.0, "delta": 33.0}
  ],
  "extrapolation_warnings": [],
  "baseline_predictions": {
    "significant_delay": {"model_used": "random_forest", "predicted_class": 0, "probability_of_significant_delay": 0.31},
    "final_delay_days": {"model_used": "xgboost", "predicted_final_delay_days": 58.2},
    "cost_overrun": {"model_used": "logistic_regression_baseline", "predicted_class": 0, "probability_of_cost_overrun": 0.22},
    "final_cost_overrun_pct": {"model_used": "linear_regression_baseline", "predicted_final_cost_overrun_pct": 6.1}
  },
  "simulated_predictions": { "...same four tasks, re-scored with the override applied..." },
  "synthetic_data_disclaimer": "... (identical text GET /predict returns) ...",
  "simulation_disclaimer": "This is a model re-scoring under a hypothetical assumption, not a prediction of what will actually happen. It is not a validated causal estimate."
}
```

The four per-task prediction objects reuse the exact Phase 6 response
schemas (`app.schemas.predictions.{SignificantDelayResult,FinalDelayDaysResult,CostOverrunResult,FinalCostOverrunPctResult}`)
-- classification tasks return `predicted_class` + a named probability
field, regression tasks return the raw numeric prediction, uncapped, same
as `GET /predict`.

## 5. Real example

Run against a real local server (`cd backend && ./.venv/Scripts/python -m uvicorn app.main:app --reload`):

```
POST /projects/HRI-0006/simulate?reporting_month=2022-12
Body: {"contractor_productivity_factor": 0.5}
```

produced (abbreviated, full run recorded in the Phase 10 completion
report):

- `baseline_predictions.final_delay_days.predicted_final_delay_days` and
  `simulated_predictions.final_delay_days.predicted_final_delay_days` differ,
  with the simulated (worsened-productivity) value never lower than the
  baseline -- consistent with the -0.685 correlation between
  `contractor_productivity_factor` and `final_delay_days` documented in
  [EDA_REPORT.md](EDA_REPORT.md).
- `overrides[0]` reports `field="contractor_productivity_factor"`, the
  real `original_value` read from that snapshot, `simulated_value=0.5`,
  and their `delta`.
- `simulation_disclaimer` is present verbatim (section 13).

## 6. Permitted predictors, and what is rejected

A permitted predictor is exactly one of the 45 columns in
`scripts.prepare_features.PREDICTOR_COLUMNS` (the same leakage-audited list
`GET /predict` builds its feature row from -- see
[FEATURE_ENGINEERING.md](FEATURE_ENGINEERING.md) section 2): 4 static
numeric, 3 categorical (`state`, `project_type`, `contractor`), 25
current/cumulative-snapshot numeric, 13 Phase-3 engineered numeric
(rolling trends, ratios, composites).

Everything else is rejected with **HTTP 422** and every invalid field name
listed (never silently dropped), each tagged with why (`app.simulation.overrides.classify_invalid_field`):

| Rejected field(s) | Reason tag |
|---|---|
| `project_id`, `reporting_month` | `identifier` |
| `final_delay_days`, `significant_delay`, `final_cost_overrun_pct`, `cost_overrun` | `target_column` |
| `is_terminal_snapshot` | `terminal_flag` |
| `project_status`, `data_provenance`, `project_name`, `highway_number`, `planned_start_date`, `planned_completion_date` | `excluded_from_model` |
| `planned_expenditure_inr_cr`, `expenditure_variance_pct` (Phase 3's confirmed exact-duplicate columns) | `excluded_from_model_exact_duplicate` |
| any other unrecognized field | `unknown_field` |

A wrong-type value on an otherwise-permitted field (e.g. a string on a
numeric predictor) is rejected the same way, tagged `wrong_type_expected_number`
/ `wrong_type_expected_string`.

Example 422 body:

```json
{
  "detail": {
    "message": "One or more override fields are not permitted predictor fields.",
    "invalid_fields": [{"field": "project_id", "reason": "identifier"}]
  }
}
```

## 7. Absolute-override design

Every override value is the complete new value the caller wants that
feature to hold -- there is no delta/relative syntax
(`"+20"`, `"-10"`, `"increase by 20"`). This is not special-cased: a
numeric predictor's override is type-checked as a real `int`/`float`, so a
delta-style string like `"+20"` is structurally rejected as
`wrong_type_expected_number`, the same path as any other wrong-type value
(`app.simulation.overrides.validate_override_fields`, exercised by
`test_validate_override_fields_rejects_delta_style_string_for_a_numeric_field`).

## 8. Why delta syntax is not accepted

An absolute value is unambiguous and trivially auditable in the response
(`original_value` / `simulated_value` / `delta` are all reported, so the
caller can always reconstruct what changed). A relative/delta syntax would
require parsing free-form expressions, deciding what "+20" composes with if
sent twice, and silently depending on which baseline it was computed
against -- all avoidable complexity the Phase 10 brief explicitly excludes.

## 9. Model registry reuse

No second model registry exists. `app.simulation.service.run_simulation`
calls `app.ml.features.build_predictor_row` (identical to `GET /predict`)
for the baseline row, then `app.ml.predict.predict_all_tasks` -- a helper
extracted in this phase from the router code `GET /predict` used to inline,
now shared by both endpoints -- for both the baseline and simulated rows.
`predict_all_tasks` calls `app.ml.registry.get_model`, which only ever
returns a pipeline that `app.ml.registry.load_models` loaded once at
startup. No model is loaded, fit, or reloaded per request, and no
alternate model-loading path exists for simulation.
`backend/tests/test_simulation_api.py::test_simulation_baseline_matches_independent_artifact_inference`
independently reloads each saved `.joblib` artifact with `joblib.load` and
confirms the simulation endpoint's baseline predictions match exactly
(Test 7 in section 14).

## 10. Terminal snapshot restriction

`POST /projects/{project_id}/simulate` returns **HTTP 422** if the
requested snapshot's `is_terminal_snapshot` is `true`, before any override
is even validated.

## 11. Why terminal snapshots are prohibited

Phase 3 found that on a terminal (`project_status == "Completed"`) row,
`final_delay_days` is exactly reconstructible from that same row's
`reporting_month - planned_completion_date` (max abs diff `0` across all
400 terminal rows -- see [FEATURE_ENGINEERING.md](FEATURE_ENGINEERING.md)
section 3). A terminal snapshot's feature row already encodes the known
final outcome; simulating a hypothetical override from it would not
isolate the override's effect from that already-known result, and the
"prediction" would be misleading in the same way `GET /predict` already
avoids for terminal rows (section 7 of
[MODEL_SERVING.md](MODEL_SERVING.md)). The error response tells the caller
to select an earlier, non-terminal snapshot instead.

## 12. Training-range calculation

`scripts/compute_training_ranges.py` computes the observed min/max of every
NUMERIC permitted predictor **only from the Phase 4 TRAINING partition**
(never validation, test, the full dataset, or a live snapshot), by calling
`scripts.data_split.project_level_split` unchanged with its own defaults
(seed 42, 70/15/15, terminal snapshots excluded) against
`data/processed/delay_features.csv` -- the identical split every Phase 4/5
model was actually trained on. Categorical predictors are excluded (section
14). Output is committed at `models/metrics/training_feature_ranges.json`
(same committed-artifact convention as `baseline_metrics.json` /
`tree_metrics.json`), with `run_metadata` documenting the exact source file,
split parameters, and row/project counts used, and loaded once at startup
by `app.ml.training_ranges.load_training_ranges` (fails loudly if the
artifact is missing, exactly like a missing model artifact). Regenerate
with:

```bash
./backend/.venv/Scripts/python.exe -m scripts.compute_training_ranges
```

## 13. Extrapolation warning

For every overridden NUMERIC field, if the new value falls outside
`[training_min, training_max]`, the response's `extrapolation_warnings`
list includes an entry naming the field, the value, the training bounds,
and: *"Model behavior outside its observed training distribution is less
reliable."* This is a **warning, not a rejection** -- the simulation still
executes and returns full predictions. Categorical predictors
(`state`, `project_type`, `contractor`) are never extrapolation-checked; an
unfamiliar category is instead handled by the saved pipeline's own
`OneHotEncoder(handle_unknown="ignore")` (all-zero encoding for that
column, the same behavior `GET /predict` already relies on for any
missing/unseen categorical value).

## 14. Mandatory disclaimer

Every successful (`HTTP 200`) simulation response includes, verbatim and
unconditionally:

> "This is a model re-scoring under a hypothetical assumption, not a
> prediction of what will actually happen. It is not a validated causal
> estimate."

`app.schemas.simulation.SIMULATION_DISCLAIMER` is a `str` class default on
`SimulationResponse` (not something a caller can omit or override), and
`backend/tests/test_simulation_api.py::test_successful_simulation_always_includes_mandatory_disclaimer`
/ `test_disclaimer_also_present_with_zero_overrides` verify it is present
byte-for-byte on both a with-override and a zero-override request.

## 15. What this simulator is NOT

- **Not a forecast.** It does not predict what will actually happen to the
  real project.
- **Not a causal estimate.** The Phase 4/5 models are correlational,
  trained on a SYNTHETIC dataset (see
  [SYNTHETIC_DATA_METHODOLOGY.md](SYNTHETIC_DATA_METHODOLOGY.md)); an
  observed association (e.g. `contractor_productivity_factor`'s -0.685
  correlation with `final_delay_days`, [EDA_REPORT.md](EDA_REPORT.md)) is
  not evidence that changing one feature *causes* the predicted outcome to
  change by that amount.
- **Not a real-world intervention simulator.** Overriding one feature does
  **not** automatically change other features that would plausibly move
  together in reality. For example, increasing
  `land_acquisition_delay_days` does not automatically simulate
  corresponding changes in `contractor_productivity_factor`,
  `actual_expenditure_inr_cr`, material availability, weather, or any other
  correlated factor -- every non-overridden feature is held exactly at its
  real recorded value (Test 5, section 14). The result is therefore a
  **model scenario**, not a realistic intervention forecast.

## 16. Directional sanity-check result

`backend/tests/test_simulation_api.py::test_worsening_contractor_productivity_does_not_decrease_predicted_delay`
overrides `contractor_productivity_factor` to `0.5` (inside the Phase 4
training range `[0.498, 1.35]`, so the check is isolated from any
extrapolation effect) on a real non-terminal snapshot (`HRI-0006`,
`2022-12`) and asserts `simulated_predictions.final_delay_days` is never
lower than `baseline_predictions.final_delay_days`. This direction is
sensible because `contractor_productivity_factor` correlates **-0.685**
with `final_delay_days` ([EDA_REPORT.md](EDA_REPORT.md) section "Findings")
and was Phase 5's strongest SHAP-attributed predictor across tasks
([SHAP_EXPLAINABILITY_REPORT.md](SHAP_EXPLAINABILITY_REPORT.md)) -- lower
productivity is associated with more delay, never less. No exact
prediction number is asserted, and no other task's output is assumed to
move in a particular direction (per the Phase 10 brief -- these are
independent learned model outputs).

## 17. Limitations

- **Synthetic data only.** Every simulation response carries the same
  `synthetic_data_disclaimer` text `GET /predict` returns for a
  non-terminal snapshot.
- **No feature-interaction modeling.** See section 15 -- overriding one
  feature never cascades into any other feature.
- **Engineered (Phase 3) predictor columns can be overridden directly.**
  13 of the 45 permitted predictors (e.g. `project_age_ratio`,
  `schedule_pressure`, `delay_factor_count`) are themselves derived from
  raw columns. Overriding one of these directly does not recompute it from
  a hypothetical raw input, and overriding a raw column it derives from
  does not recompute the derived column -- each of the 45 predictor columns
  is treated as an independent override target, consistent with section 15's
  "no automatic feature interaction" scope. Recomputing derived features
  from raw overrides would require new preprocessing logic, explicitly
  out of scope for Phase 10.
- **Extrapolation bounds are per-feature, univariate.** A combination of
  several individually in-range overrides can still describe a
  jointly-implausible/out-of-distribution scenario that this check does
  not detect (it does not model feature covariance).
- **Categorical overrides are not checked against the pipeline's actually-seen
  training categories.** An unrecognized category is accepted (it is a
  syntactically valid string) and silently one-hot-encoded to all zeros by
  the pipeline's `handle_unknown="ignore"` `OneHotEncoder` -- the same
  behavior `GET /predict` already has for any snapshot carrying an
  unfamiliar category, not a new Phase 10 behavior.
- **No model retraining, tuning, or new preprocessing was added in this
  phase** -- by design (see section 9).
