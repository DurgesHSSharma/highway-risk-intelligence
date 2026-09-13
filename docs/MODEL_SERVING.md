# Phase 6 — Model Serving

*** This page describes how already-trained Phase 4/5 artifacts are
served. No model was retrained, tuned, or modified in Phase 6 -- all
performance numbers referenced here are Phase 4/5's, reproduced from
[BASELINE_MODEL_REPORT.md](BASELINE_MODEL_REPORT.md) and
[MODEL_COMPARISON_REPORT.md](MODEL_COMPARISON_REPORT.md), not remeasured. ***

## 1. Task -> model mapping

Verified against the actual `docs/MODEL_COMPARISON_REPORT.md` section 8
("Recommended model per task"), not assumed from the Phase 6 brief's
expected values (which happen to match exactly):

| Task | Target column | Recommended model | Artifact path |
|---|---|---|---|
| A. Delay classification | `significant_delay` | **Random Forest** | `models/random_forest/delay_classification_random_forest.joblib` |
| B. Delay regression | `final_delay_days` | **XGBoost** | `models/xgboost/delay_regression_xgboost.joblib` |
| C. Cost classification | `cost_overrun` | **Phase 4 baseline (Logistic Regression)** | `models/baseline/cost_classification_logistic_regression.joblib` |
| D. Cost regression | `final_cost_overrun_pct` | **Phase 4 baseline (Linear Regression)** | `models/baseline/cost_regression_linear_regression.joblib` |

This is the ONE auditable mapping (`backend/app/ml/registry.py::TASK_MODEL_REGISTRY`)
-- no endpoint hard-codes a model choice separately, and no model is
selected dynamically at request time or by "highest metric."

Reasons (from MODEL_COMPARISON_REPORT.md section 8, reproduced verbatim in
spirit):
- **A:** Random Forest beat the Phase 4 baseline (test ROC-AUC 0.915 vs.
  0.875) with the smallest train/test gap of the three models.
- **B:** XGBoost beat the Phase 4 baseline (test R² 0.571 vs. 0.492);
  its relative overfitting is not worse than the baseline's own on this
  task.
- **C:** Neither tree model beat the Phase 4 Logistic Regression baseline
  on test (RF ties, XGBoost is worse with the largest overfitting gap in
  the report for a classifier).
- **D:** The Phase 4 Linear Regression baseline substantially outperforms
  both tree models (test R² 0.905 vs. RF 0.680 / XGBoost 0.749) --
  the clearest "baseline remains better" result Phase 5 found.

## 2. Startup loading (no request-time retraining)

`app/main.py`'s `lifespan` handler calls `app.ml.registry.load_models()`
once, at process startup:

- Every artifact in `TASK_MODEL_REGISTRY` is `joblib.load()`ed exactly
  once and cached in a module-level dict.
- Nothing is fit, refit, or retrained. No imputer/scaler/encoder is
  reconstructed -- the saved `sklearn.pipeline.Pipeline` objects already
  contain the exact fitted preprocessing from Phase 4 (`build_preprocessor`
  in `scripts/train_baseline_models.py`, reused unchanged by Phase 5's tree
  models).
- **Fail loudly:** if any registered artifact file is missing,
  `load_models()` raises `ModelArtifactMissingError` and FastAPI aborts
  startup with a traceback naming exactly which artifact is missing and
  where it was expected. Verified for real (not just unit-tested): a
  Phase 6 verification run temporarily removed
  `models/random_forest/delay_classification_random_forest.joblib` and
  confirmed `uvicorn` refuses to start, printing that exact path, before
  the artifact was restored.
- There is no fallback to another model, no silent substitution, and no
  fabricated prediction if loading fails.

Resource note: each of the 4 artifacts is loaded exactly once for the life
of the process (not once per request, and not duplicated across workers
beyond what `uvicorn`'s worker count implies) -- relevant on this
project's resource-constrained dev machine, since the two Random-Forest
cost-task artifacts are 12-31MB each.

## 3. Preprocessing reuse

Every artifact is a complete `Pipeline([("preprocess", ColumnTransformer(...)), ("model", ...)])`.
The API always calls `.predict()` / `.predict_proba()` on the whole
pipeline with a raw (unscaled, unencoded, NaN-containing-where-applicable)
1-row `DataFrame` of the 45 `PREDICTOR_COLUMNS`
(`scripts/prepare_features.PREDICTOR_COLUMNS`, imported directly -- never
redefined in the backend). The pipeline's own fitted
`SimpleImputer`/`StandardScaler`/`OneHotEncoder` do all the preprocessing;
the API performs none itself. Verified behaviorally, not just by
inspection, by `backend/tests/test_prediction_consistency.py`, which
loads each artifact independently with `joblib.load` and confirms its
prediction on the same feature row matches the API's response exactly
(classification: identical predicted class and probability; regression:
identical value within floating-point tolerance).

## 4. Feature reconstruction for prediction

The 45 predictor columns include 13 engineered features (rolling 3-month
trends, ratios, cumulative delay-factor composites, etc. -- see
`docs/FEATURE_ENGINEERING.md`) that Phase 3 computed once over the *full*
CSV. At prediction time there is no "full CSV" for a single request, so
`app/ml/features.py::build_predictor_row` reconstructs them by:

1. Pulling the target project's own snapshot history from the database, up
   to and including the requested `reporting_month`.
2. Calling `scripts.prepare_features.add_engineered_features` on exactly
   that prefix -- the same Phase 3 function, never reimplemented.

This is safe because every engineered feature in that function is a
per-project rolling/diff/ratio computation over rows at or before the
current one (Phase 3's own leakage-safety design principle); truncating a
project's history to a prefix reproduces the exact same value at the
target row as running it over the full file. Verified directly:
`backend/tests/test_prediction_consistency.py::test_feature_row_matches_phase3_precomputed_features`
compares the on-the-fly reconstruction against Phase 3's own
`data/processed/delay_features.csv` row and requires an exact match.

## 5. Classification outputs

For `significant_delay` and `cost_overrun`, the response includes both the
predicted class and an explicitly-named probability field -- never an
ambiguous generic `probability`:

- `probability_of_significant_delay` -- P(`significant_delay == 1`)
- `probability_of_cost_overrun` -- P(`cost_overrun == 1`)

The "probability of class 1" column is looked up via the pipeline's own
`classes_` attribute (`[0, 1]` for both classifiers, confirmed by
inspection), not assumed to be a fixed array index.

## 6. Regression outputs

`final_delay_days` -> `predicted_final_delay_days`;
`final_cost_overrun_pct` -> `predicted_final_cost_overrun_pct`. Raw model
output, cast to `float`; **no clamping is applied** (e.g. a predicted delay
is not floored at 0) because Phase 4/5's training methodology applied
none, and inventing a new post-processing rule in Phase 6 would create a
train/serve mismatch.

## 7. Terminal snapshot policy

If the requested snapshot's `is_terminal_snapshot` is `true`, **no model
is invoked at all**. The response returns the four recorded outcome
columns directly from that database row, with:

```json
{"prediction_status": "actual_outcome", "is_model_prediction": false,
 "explanation": "This snapshot is terminal; recorded final outcomes are
  returned instead of model predictions."}
```

This exists because `final_delay_days` is exactly reconstructible from
`reporting_month - planned_completion_date` on a terminal row (a Phase 3
finding) -- presenting that as a "prediction" would be misleading.

## 8. Model limitations (carried over from Phase 4/5, unchanged)

- **Synthetic data only.** Every non-terminal prediction response includes
  a disclaimer stating the model was trained on this project's SYNTHETIC
  dataset and does not represent real NHAI predictive accuracy, production
  readiness, or government validation.
- Tasks A and B (delay) beat the Phase 4 baseline; Tasks C and D (cost) do
  not -- Phase 6 serves the Phase 5 report's actual recommendation per
  task rather than "always use the newer model."
- Missing-feature handling relies entirely on the saved pipeline's own
  imputer; see [API_AND_DATABASE.md](API_AND_DATABASE.md) section 7.
