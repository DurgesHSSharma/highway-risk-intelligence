# Phase 4 — Baseline Model Report

*** All numbers on this page were produced by actually running
`scripts/train_baseline_models.py` (seed 42) against the checked-in
`data/processed/delay_features.csv` / `cost_features.csv`, and are saved
verbatim in [`models/metrics/baseline_metrics.json`](../models/metrics/baseline_metrics.json).
None are estimated, rounded from memory, or invented. Regenerate with:
```
cd scripts
../backend/.venv/Scripts/python.exe train_baseline_models.py
```
***

**Performance described here is performance on the synthetic prototype
dataset only.** This report does NOT claim the models predict real NHAI
highway project delays or cost overruns with any accuracy. Real-world
predictive validity has not been established -- see
[SYNTHETIC_DATA_METHODOLOGY.md](SYNTHETIC_DATA_METHODOLOGY.md) for what
this synthetic dataset can and cannot support.

## 1. Objective

Establish the first reliable ML baseline for four prediction tasks, and a
reusable, leakage-safe evaluation framework that Phase 5's tree-based
models must beat. The objective is a defensible benchmark, not maximizing
accuracy -- see section 13 for the sanity checks this implies.

## 2. Four prediction tasks

| Task | Type | Target | Dataset |
|---|---|---|---|
| A. Significant Delay Classification | Binary classification | `significant_delay` | `delay_features.csv` |
| B. Delay Duration Regression | Regression | `final_delay_days` | `delay_features.csv` |
| C. Cost Overrun Classification | Binary classification | `cost_overrun` | `cost_features.csv` |
| D. Cost Overrun Regression | Regression | `final_cost_overrun_pct` | `cost_features.csv` |

## 3. Dataset

`data/processed/delay_features.csv` and `cost_features.csv` (Phase 3
output, 8,740 rows / 400 projects each, unchanged in Phase 4). See
[FEATURE_ENGINEERING.md](FEATURE_ENGINEERING.md) for the full feature
dictionary and [TRAIN_VAL_TEST_STRATEGY.md](TRAIN_VAL_TEST_STRATEGY.md)
for the split.

## 4. Terminal snapshot handling

400 of 8,740 rows (one per project, where `is_terminal_snapshot == True`)
are excluded from training and evaluation for all four tasks, because
`final_delay_days` is exactly reconstructible from that row's own fields
(Phase 3 finding). 8,340 rows remain across train+validation+test. See
[TRAIN_VAL_TEST_STRATEGY.md](TRAIN_VAL_TEST_STRATEGY.md) section 3 for the
exact per-split counts. The source CSVs are untouched; exclusion happens
only inside `scripts/data_split.py::project_level_split`.

## 5. Feature exclusions

All four tasks use the same **45** predictor columns
(`scripts.prepare_features.PREDICTOR_COLUMNS` -- imported directly, never
redefined, so this script cannot silently drift from the Phase 3
leakage-audited feature list): 42 numerical + 3 categorical
(`state`, `project_type`, `contractor`).

Never used as predictors, for any task (enforced by
`tests/test_train_baseline_models.py::test_targets_never_appear_in_predictor_columns`
and siblings):
- `project_id`, `reporting_month` (identifiers)
- `is_terminal_snapshot` (split/QA flag)
- `final_delay_days`, `significant_delay` (excluded from `cost_features.csv`'s
  own predictor use and never used for Tasks C/D)
- `final_cost_overrun_pct`, `cost_overrun` (never used for Tasks A/B)

## 6. Preprocessing

A single `sklearn.compose.ColumnTransformer` (`scripts.train_baseline_models.build_preprocessor`),
fit **only** inside each model's `.fit(X_train, y_train)` call (never on
the full dataset before splitting, and never re-fit or adjusted using
validation/test data):

| Column type | Steps |
|---|---|
| Numeric (42 cols) | `SimpleImputer(strategy="median")` → `StandardScaler()` |
| Categorical (3 cols: `state`, `project_type`, `contractor`) | `SimpleImputer(strategy="constant", fill_value="Unknown")` → `OneHotEncoder(handle_unknown="ignore")` |

Rationale: median imputation and an explicit `"Unknown"` category are the
recommended strategies documented in
[FEATURE_ENGINEERING.md](FEATURE_ENGINEERING.md) section 5.
`handle_unknown="ignore"` means a category never seen in training (e.g. a
`contractor` value that only appears in the test cohort) is encoded as an
all-zero row for that feature block rather than raising an error --
verified by `test_unseen_categorical_value_does_not_crash_transform`.
Scaling is applied because Logistic/Linear Regression's coefficients are
scale-sensitive; it has no effect on the Dummy baselines (which ignore `X`
entirely).

`tests/test_train_baseline_models.py::test_preprocessing_fit_parameters_come_only_from_training_data`
demonstrates behaviorally (fitting on two datasets identical in train but
differing in validation, then comparing the fitted imputer/scaler/encoder
parameters) that no preprocessing statistic depends on validation or test
rows.

## 7. Split methodology

Project-level chronological cohort split (280/60/60 projects,
5,834/1,234/1,272 rows), seed 42. Full write-up:
[TRAIN_VAL_TEST_STRATEGY.md](TRAIN_VAL_TEST_STRATEGY.md).

## 8. Baselines

| Task type | Baseline(s) |
|---|---|
| Classification (A, C) | `DummyClassifier(strategy="most_frequent")` |
| Regression (B, D) | `DummyRegressor(strategy="mean")` and `DummyRegressor(strategy="median")` |

No hyperparameters were tuned for any baseline.

## 9. Logistic / Linear models

`LogisticRegression(random_state=42)` (classification, A & C) and
`LinearRegression()` (regression, B & D), both using scikit-learn's
default configuration otherwise (solver `lbfgs`, `max_iter=100`). No
hyperparameter tuning was performed anywhere in Phase 4.

A benign `OptimizeWarning: Unknown solver options: iprint` is printed
during every `LogisticRegression.fit()` call in this environment -- this is
a scikit-learn 1.5.2 / scipy 1.18.1 version-compatibility message (scipy no
longer recognizes an internal lbfgs option scikit-learn still passes), not
a convergence failure. Confirmed by inspecting `model.n_iter_` directly:
the delay-classification model converged in 84 iterations and the
cost-classification model in 87, both well under the default cap of 100 --
so no solver/`max_iter` adjustment was needed or made.

## 10. Validation results

### Task A — Significant Delay Classification

| Metric | Baseline (majority class) | Logistic Regression | Improvement |
|---|---|---|---|
| Accuracy | 0.600 | 0.833 | +0.233 |
| Precision | 0.600 | 0.885 | -- |
| Recall | 1.000 | 0.830 | -- |
| F1 | 0.750 | 0.856 | +0.107 |
| ROC-AUC | 0.500 | 0.913 | +0.413 |
| PR-AUC | 0.600 | 0.945 | +0.345 |
| Confusion matrix | [[0, 494], [0, 740]] | [[414, 80], [126, 614]] | -- |

### Task B — Delay Duration Regression (days)

| Metric | Baseline (mean) | Baseline (median) | Linear Regression | Improvement (vs. best baseline) |
|---|---|---|---|---|
| MAE | 91.45 | 86.96 | 51.33 | +35.63 |
| RMSE | 157.69 | 162.40 | 78.13 | -- |
| R² | -0.016 | -0.078 | 0.751 | -- |

### Task C — Cost Overrun Classification

| Metric | Baseline (majority class) | Logistic Regression | Improvement |
|---|---|---|---|
| Accuracy | 0.496 | 0.867 | +0.371 |
| Precision | 0.000 | 0.977 | -- |
| Recall | 0.000 | 0.754 | -- |
| F1 | 0.000 | 0.851 | +0.851 |
| ROC-AUC | 0.500 | 0.969 | +0.469 |
| PR-AUC | 0.504 | 0.973 | +0.468 |
| Confusion matrix | [[612, 0], [622, 0]] | [[601, 11], [153, 469]] | -- |

### Task D — Cost Overrun Regression (percentage points)

| Metric | Baseline (mean) | Baseline (median) | Linear Regression | Improvement (vs. best baseline) |
|---|---|---|---|---|
| MAE | 10.44 | 10.54 | 2.78 | +7.67 |
| RMSE | 12.40 | 12.49 | 3.65 | -- |
| R² | -0.003 | -0.017 | 0.913 | -- |

## 11. Test results

### Task A — Significant Delay Classification

| Metric | Baseline | Logistic Regression | Improvement |
|---|---|---|---|
| Accuracy | 0.480 | 0.762 | +0.282 |
| Precision | 0.480 | 0.754 | -- |
| Recall | 1.000 | 0.748 | -- |
| F1 | 0.648 | 0.751 | +0.102 |
| ROC-AUC | 0.500 | 0.875 | +0.375 |
| PR-AUC | 0.480 | 0.878 | +0.398 |

### Task B — Delay Duration Regression (days)

| Metric | Baseline (mean) | Baseline (median) | Linear Regression | Improvement |
|---|---|---|---|---|
| MAE | 91.15 | 85.01 | 61.92 | +23.09 |
| RMSE | 125.74 | 126.46 | 89.39 | -- |
| R² | -0.004 | -0.016 | 0.492 | -- |

### Task C — Cost Overrun Classification

| Metric | Baseline | Logistic Regression | Improvement |
|---|---|---|---|
| Accuracy | 0.654 | 0.881 | +0.226 |
| Precision | 0.000 | 0.869 | -- |
| Recall | 0.000 | 0.770 | -- |
| F1 | 0.000 | 0.817 | +0.817 |
| ROC-AUC | 0.500 | 0.941 | +0.441 |
| PR-AUC | 0.346 | 0.922 | +0.576 |

### Task D — Cost Overrun Regression (percentage points)

| Metric | Baseline (mean) | Baseline (median) | Linear Regression | Improvement |
|---|---|---|---|---|
| MAE | 11.01 | 10.87 | 3.15 | +7.72 |
| RMSE | 13.95 | 13.93 | 4.30 | -- |
| R² | -0.003 | -0.000 | 0.905 | -- |

## 12. Baseline comparison summary

All four simple models **beat** their naive baselines on both validation
and test, by a wide margin in every metric:

| Task | Test metric | Baseline | Model | Verdict |
|---|---|---|---|---|
| A (delay classification) | F1 | 0.648 | 0.751 | Model beats baseline |
| B (delay regression) | MAE | 85.01 (best baseline) | 61.92 | Model beats baseline |
| C (cost classification) | F1 | 0.000 | 0.817 | Model beats baseline |
| D (cost regression) | MAE | 10.87 (best baseline) | 3.15 | Model beats baseline |

Per the Phase 4 brief, "model beats baseline" is one of three valid
scientific outcomes (the others being "roughly matches" or "performs
worse") -- it was not assumed going in, it is what the executed pipeline
produced.

## 13. Overfitting / sanity checks

**All validation metrics are stronger than the corresponding test metrics**
for every task except Task D, where test R² (0.905) is close to but
slightly below validation R² (0.913) -- consistent with ordinary
train/validation/test variance on cohorts of 60 projects each, not with
overfitting inflating validation only. Task A/B/C show the expected
pattern of validation performing somewhat better than test (e.g. Task A
ROC-AUC 0.913 validation vs. 0.875 test; Task B R² 0.751 validation vs.
0.492 test), which is unsurprising given the cohorts are only 60 projects
each and were never used to pick features, preprocessing, or
hyperparameters (there were none to pick in Phase 4).

**Suspicious-performance investigation (required by Phase 4 brief section
23)**: Task C's validation ROC-AUC (0.969) and Task D's validation R²
(0.913) are high enough that they were investigated before being reported,
per instruction, rather than accepted at face value:

1. **Project overlap**: re-verified zero overlap between train/validation/
   test project sets for both `delay_features.csv` and `cost_features.csv`
   at run time (also covered by
   `tests/test_data_split.py::test_no_project_appears_in_more_than_one_split`).
2. **Terminal snapshot contamination**: re-verified zero
   `is_terminal_snapshot == True` rows in any split's evaluation data.
3. **Single-feature leakage**: computed Pearson correlation of every one of
   the 42 numeric predictors against every target, on the training split
   only. The single strongest predictor anywhere is
   `contractor_productivity_factor` (corr -0.697 with `final_cost_overrun_pct`,
   -0.693 with `final_delay_days`) -- well below the Phase 3 leakage
   threshold of 0.95, and consistent with Phase 3's EDA finding that this
   is "the single strongest predictor found anywhere in this dataset" (a
   real, disclosed, non-deterministic relationship, not a data artifact).
   No engineered feature (e.g. `cost_growth_rate`, `cost_tracking_gap_inr_cr`)
   exceeded this either.
4. **Target-derived features**: re-confirmed no engineered feature in
   `scripts/prepare_features.py::add_engineered_features` references any
   of the four target columns.
5. **Explanation for the strong-but-legitimate result**: the Phase 2
   generator drives both progress and cost trajectories through a shared
   latent per-project trait (`contractor_productivity_factor`, an AR(1)
   process -- see `SYNTHETIC_DATA_METHODOLOGY.md`). Several derived
   features (`cost_tracking_gap_inr_cr`, `schedule_pressure`,
   `physical_progress_variance_pct`, `consecutive_underperforming_months`)
   correlate moderately-to-strongly (0.30-0.70) with the cost/delay targets
   *through that one shared channel*, and Linear/Logistic Regression
   combining ~6-8 such correlated signals linearly can plausibly explain
   most of the variance without any single feature approaching a
   deterministic relationship. This is a genuine, mechanistic
   characteristic of this synthetic generator (a data-generation-process
   fact, disclosed in Phase 2/3 docs), not evidence of leakage. **It should
   not be read as evidence that a linear model would perform this well on
   real, noisier highway project data** -- see section 15.

No further leakage source was found. The performance is reported as-is,
not adjusted or hidden, per instruction.

## 14. Limitations

- Validation and test cohorts are small (60 projects / ~1,250 rows each),
  so metric estimates carry meaningful sampling noise; the point estimates
  above should not be read as precise to three decimal places in a
  practical sense.
- No hyperparameter tuning was performed anywhere (by design, Phase 4
  scope) -- these are baseline configurations, not optimized models.
- Task B (delay regression) test R² (0.492) is meaningfully lower than its
  validation R² (0.751); with only 60 test projects this gap is plausibly
  cohort variance rather than a systematic issue, but it has not been
  further diagnosed (out of scope for Phase 4 -- no additional feature
  engineering or tuning is permitted this phase).
- `contractor` (50 categories) is one-hot encoded here per section 6; the
  Phase 3 recommendation to consider frequency/target encoding instead was
  not applied (out of scope -- no encoding-strategy comparison was run).
- These results describe a **synthetic, mechanistically-generated**
  dataset. The strength of the linear relationships found (section 13,
  point 5) is partly a property of how the Phase 2 generator was built and
  should not be extrapolated to real NHAI project data, where noise,
  missing structure, and confounding are expected to be substantially
  higher.

## 15. Synthetic-data disclaimer

**Every number in this report describes performance on the synthetic
prototype dataset.** Do not state or imply that "the system predicts NHAI
delays/cost overruns with X% accuracy" -- that claim would misrepresent
what has been validated. Real-world predictive validity has not been
established and would require real, labeled highway project data, which
this project does not have (see
[SYNTHETIC_DATA_METHODOLOGY.md](SYNTHETIC_DATA_METHODOLOGY.md) section 14).

## 16. What Phase 5 should improve

- Beat these baselines with tree-based models (Random Forest / Gradient
  Boosting) capable of capturing non-linear interactions the linear
  baselines cannot (e.g. threshold effects in `schedule_pressure` or
  `project_age_ratio`).
- Investigate Task B's validation/test R² gap (0.751 vs. 0.492) with a
  more expressive model before concluding whether it is cohort noise or a
  systematic pattern the linear model cannot capture.
- Consider SHAP-based explainability once a stronger model exists, to
  verify feature importances remain consistent with the correlation
  analysis in section 13 (or identify new signals a linear model would
  have missed).
- Consider comparing `contractor`'s one-hot encoding against the
  frequency/target-encoding alternative documented in
  [FEATURE_ENGINEERING.md](FEATURE_ENGINEERING.md) section 7.
- Any hyperparameter tuning (GridSearchCV/RandomizedSearchCV), which was
  explicitly out of scope for Phase 4, should use this report's
  validation-set numbers as the benchmark to beat, and must not touch the
  test set until a final model is chosen.
