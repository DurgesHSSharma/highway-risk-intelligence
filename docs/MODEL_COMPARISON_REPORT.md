# Phase 5 — Model Comparison Report

*** All numbers on this page were produced by actually running
`scripts/train_tree_models.py` (seed 42) against the checked-in
`data/processed/delay_features.csv` / `cost_features.csv`, using the
IDENTICAL frozen Phase 4 project-level split
(`scripts/data_split.py::project_level_split`, imported unchanged), and are
saved verbatim in
[`models/metrics/tree_metrics.json`](../models/metrics/tree_metrics.json).
Baseline numbers are unchanged from Phase 4
([`models/metrics/baseline_metrics.json`](../models/metrics/baseline_metrics.json))
plus a small set of TRAIN-split metrics computed in this phase (from the
existing frozen `models/baseline/*.joblib` artifacts, without retraining
them) purely to make the train-vs-validation-vs-test overfitting comparison
apples-to-apples across baseline/RF/XGBoost. None of these numbers are
estimated, rounded from memory, or invented. Regenerate with:
```
cd C:\Projects\highway-risk-intelligence
backend\.venv\Scripts\python.exe -m scripts.train_tree_models
```
***

**Performance described here is performance on the synthetic prototype
dataset only.** This report does NOT claim the models predict real NHAI
highway project delays or cost overruns with any accuracy. See
[SYNTHETIC_DATA_METHODOLOGY.md](SYNTHETIC_DATA_METHODOLOGY.md).

## 1. Objective

Determine, honestly, whether Random Forest and XGBoost improve on the
Phase 4 Logistic/Linear Regression baselines for the four prediction tasks,
using the exact same frozen split, features, and preprocessing definition.
The Phase 4 baseline was neither retrained nor adjusted; it is the frozen
benchmark being tested against, not a moving target.

## 2. Methodology

### 2.1 Split (reused, not reimplemented)

`scripts/data_split.py::project_level_split` is imported directly by
`scripts/train_tree_models.py` -- the split logic was never touched.
`tests/test_phase5_split_consistency.py` proves, against a persisted
snapshot of the actual Phase 4 project-ID assignment
(`tests/fixtures/phase4_frozen_split_project_ids.json`) and against
`models/metrics/baseline_metrics.json`'s own split metadata, that:

- Phase 5's train/validation/test `project_id` sets are **identical** to
  Phase 4's, dataset-for-dataset.
- Zero project overlap between any two splits.
- Zero `is_terminal_snapshot` rows in any split's modeling data.

Split sizes (unchanged from Phase 4, see
[TRAIN_VAL_TEST_STRATEGY.md](TRAIN_VAL_TEST_STRATEGY.md)): 280 train / 60
validation / 60 test projects; 5,834 / 1,234 / 1,272 rows after terminal
exclusion.

### 2.2 Features

The identical **45** predictor columns from
`scripts.prepare_features.PREDICTOR_COLUMNS` (42 numeric + 3 categorical),
imported directly -- never redefined or altered.

### 2.3 Preprocessing

The identical `ColumnTransformer` from
`scripts.train_baseline_models.build_preprocessor` (median-impute + scale
numeric; Unknown-fill + one-hot encode categorical), reused unchanged and
fit only inside each model's own `.fit(X_train, y_train)` call.

### 2.4 Models

| Task | Type | Random Forest | XGBoost |
|---|---|---|---|
| A. Significant Delay Classification | classification | `RandomForestClassifier` | `XGBClassifier` |
| B. Delay Duration Regression | regression | `RandomForestRegressor` | `XGBRegressor` |
| C. Cost Overrun Classification | classification | `RandomForestClassifier` | `XGBClassifier` |
| D. Cost Overrun Regression | regression | `RandomForestRegressor` | `XGBRegressor` |

Both use fixed `random_state=42` (`n_jobs=-1`); XGBoost classifiers use
`eval_metric="logloss"` (sklearn API default objective otherwise).

### 2.5 Hyperparameter tuning methodology

A small, **explicit** (not a grid/random search library) candidate list per
model family per task type -- 3 candidates each:

| Model family | Candidates |
|---|---|
| `RandomForestClassifier` / `RandomForestRegressor` | `{n_estimators:200,max_depth:None,min_samples_leaf:1}`, `{200,8,5}`, `{400,None,5}` |
| `XGBClassifier` / `XGBRegressor` | `{n_estimators:200,max_depth:3,learning_rate:0.1}`, `{200,5,0.05}`, `{400,3,0.05}` |

Each candidate is fit on **train only** and scored on **train and
validation only**. **Test data is never touched during tuning** --
`tune_and_select()` (`scripts/train_tree_models.py`) has no `X_test`/`y_test`
parameter at all (verified by
`tests/test_train_tree_models.py::test_tune_and_select_signature_excludes_test_data`).

**Selection metric**: ROC-AUC (classification) / R² (regression) on
validation -- the same primary metrics Phase 4 highlighted.

**Selection rule** (chosen specifically so the highest raw validation score
is not blindly taken if it is clearly overfit, per Phase 5 brief section
10): among candidates whose validation score is within a small epsilon of
the best validation score (0.005 ROC-AUC / 0.01 R²), the candidate with the
smallest (train metric − validation metric) gap is selected; ties are
broken toward fewer `n_estimators`. This is a deliberate Occam's-razor tie
break, not an automatic "highest validation score wins."

24 total model fits across all tuning (3 candidates × 2 model families × 4
tasks) -- no large search, no hundreds of fits.

## 3. Validation and test results

### Task A — Significant Delay Classification

| Metric | Baseline (LogReg) | Random Forest | XGBoost |
|---|---|---|---|
| Val accuracy | 0.833 | 0.856 | 0.844 |
| Val F1 | 0.856 | 0.872 | 0.861 |
| Val ROC-AUC | 0.913 | **0.954** | 0.941 |
| Test accuracy | 0.762 | 0.807 | 0.803 |
| Test F1 | 0.751 | 0.809 | 0.802 |
| Test ROC-AUC | 0.875 | **0.915** | 0.901 |

Selected configs: RF `{n_estimators:200, max_depth:8, min_samples_leaf:5}`;
XGBoost `{n_estimators:200, max_depth:5, learning_rate:0.05}`.

**Both tree models beat the baseline on validation and test.** Random
Forest has the best test ROC-AUC (0.915 vs. baseline 0.875, +0.040) and the
smallest overfitting gap of the three model families (see section 5).

### Task B — Delay Duration Regression (days)

| Metric | Baseline (LinReg) | Random Forest | XGBoost |
|---|---|---|---|
| Val MAE | 51.33 | 40.57 | **33.58** |
| Val R² | 0.751 | 0.853 | **0.902** |
| Test MAE | 61.92 | 53.88 | **50.18** |
| Test R² | 0.492 | 0.502 | **0.571** |

Selected configs: RF `{200, 8, 5}`; XGBoost `{n_estimators:400, max_depth:3,
learning_rate:0.05}`.

**XGBoost has the best validation and test performance of the three.**
Test R² improves from 0.492 (baseline) to 0.571 (+0.079, ~16% relative).
Section 5 examines whether this reflects real signal or overfitting in
more detail — the short version is that **all three models**, including
the linear baseline, show a large validation-to-test drop on this task, so
XGBoost's edge is not obviously an overfitting artifact unique to tree
models.

### Task C — Cost Overrun Classification

| Metric | Baseline (LogReg) | Random Forest | XGBoost |
|---|---|---|---|
| Val accuracy | 0.867 | 0.860 | 0.863 |
| Val F1 | 0.851 | 0.845 | 0.849 |
| Val ROC-AUC | 0.969 | 0.965 | **0.977** |
| Test accuracy | **0.881** | 0.842 | 0.742 |
| Test F1 | **0.817** | 0.775 | 0.620 |
| Test ROC-AUC | **0.941** | 0.934 | 0.870 |

Selected configs: RF `{n_estimators:200, max_depth:None,
min_samples_leaf:1}`; XGBoost `{400, 3, 0.05}`.

**Neither tree model beats the baseline on test**, despite XGBoost having
the *highest validation* ROC-AUC of the three (0.977). At test time,
XGBoost's ROC-AUC drops to 0.870 (a 0.107 fall from validation -- the
largest validation-to-test drop of any model in this report) and Random
Forest is essentially tied with, but not better than, the baseline
(0.934 vs. 0.941). **This is reported honestly as a case where tree models
did not improve on the baseline.**

### Task D — Cost Overrun Regression (percentage points)

| Metric | Baseline (LinReg) | Random Forest | XGBoost |
|---|---|---|---|
| Val MAE | 2.78 | 3.82 | 3.36 |
| Val R² | **0.913** | 0.838 | 0.878 |
| Test MAE | **3.15** | 6.09 | 5.12 |
| Test R² | **0.905** | 0.680 | 0.749 |

Selected configs: RF `{n_estimators:400, max_depth:None,
min_samples_leaf:5}`; XGBoost `{n_estimators:200, max_depth:3,
learning_rate:0.1}`.

**The baseline clearly and substantially outperforms both tree models**,
on validation and test alike, by the widest margin in this report (test R²
0.905 vs. 0.680 RF / 0.749 XGBoost). **This is reported honestly as a case
where tree models performed worse than the baseline**, not adjusted or
hidden.

## 4. Baseline comparison summary

| Task | Test metric | Baseline | Best tree model | Verdict |
|---|---|---|---|---|
| A (delay classification) | ROC-AUC | 0.875 | RF 0.915 | **Tree model beats baseline** |
| B (delay regression) | R² | 0.492 | XGBoost 0.571 | **Tree model beats baseline** |
| C (cost classification) | ROC-AUC | **0.941** | RF 0.934 | **Baseline remains better** |
| D (cost regression) | R² | **0.905** | XGBoost 0.749 | **Baseline remains better (by a wide margin)** |

Per Phase 5's own instruction, all three outcomes ("beats", "roughly
matches", "performs worse") were treated as equally valid going in; this is
what the executed pipeline actually produced, unadjusted.

## 5. Overfitting analysis (train vs. validation vs. test, every model)

Train-split metrics for the Phase 4 baselines were not computed in Phase 4
(only validation/test were reported there); they are computed here (from
the existing frozen `models/baseline/*.joblib` artifacts, without
retraining) solely to make this three-way comparison possible. The
baseline models/predictions themselves are unchanged.

| Task | Model | Train | Validation | Test | Train→Test gap | Relative gap |
|---|---|---|---|---|---|---|
| A (ROC-AUC) | Baseline | 0.990 | 0.913 | 0.875 | 0.116 | 11.7% |
| A (ROC-AUC) | Random Forest | 0.987 | 0.954 | 0.915 | 0.071 | **7.2%** |
| A (ROC-AUC) | XGBoost | 1.000 | 0.941 | 0.901 | 0.098 | 9.8% |
| B (R²) | Baseline | 0.866 | 0.751 | 0.492 | 0.374 | 43.2% |
| B (R²) | Random Forest | 0.913 | 0.853 | 0.502 | 0.411 | 45.0% |
| B (R²) | XGBoost | 0.951 | 0.902 | 0.571 | 0.380 | **40.0%** |
| C (ROC-AUC) | Baseline | 0.995 | 0.969 | 0.941 | 0.055 | **5.5%** |
| C (ROC-AUC) | Random Forest | 1.000 | 0.965 | 0.934 | 0.066 | 6.6% |
| C (ROC-AUC) | XGBoost | 0.999 | 0.977 | 0.870 | 0.129 | 13.0% |
| D (R²) | Baseline | 0.937 | 0.913 | 0.905 | 0.031 | **3.4%** |
| D (R²) | Random Forest | 0.983 | 0.838 | 0.680 | 0.302 | 30.8% |
| D (R²) | XGBoost | 0.933 | 0.878 | 0.749 | 0.184 | 19.8% |

**Findings:**

- **Task A**: Random Forest has the smallest absolute *and* relative
  train→test gap of the three models, in addition to the best test score
  -- a genuinely well-behaved improvement, not an overfit one.
- **Task B**: all three models -- including the plain linear baseline --
  show a large train→test drop (40-45% relative). This is the same pattern
  Phase 4 already flagged for the baseline alone; it gets *slightly worse*
  in absolute R² terms for Random Forest and XGBoost, but XGBoost's
  *relative* degradation (40.0%) is not worse than the baseline's own
  (43.2%). This points toward a property of the **test cohort itself**
  (see section 7) rather than tree-model-specific overfitting, since a
  linear model with no capacity to memorize training noise shows nearly
  the same relative collapse.
- **Task C**: XGBoost has by far the largest gap (13.0%, roughly double the
  baseline's 5.5%) and the worst test score of the three -- a genuine
  overfitting problem specific to this model, not shared by the baseline
  or Random Forest.
- **Task D**: both tree models show a large gap (31% RF, 20% XGBoost)
  against the baseline's very small 3.4% gap -- the clearest evidence in
  this report that additional model capacity here does not help and
  measurably hurts generalization.
- **`overfitting_flag`** (train−test gap > 0.15 for the primary metric, see
  `models/metrics/tree_metrics.json`) is `True` for both Task B models and
  both Task D models, and `False` for all Task A/C tree models -- consistent
  with the pattern above.

No model was selected purely for having the highest validation score
against this evidence; see section 8.

## 6. Suspicious-performance investigation (mandatory checks, brief section 12)

Warning thresholds: classification ROC-AUC > 0.95, regression R² > 0.85.
**7 of the 8 trained tree models cross one of these thresholds on
validation and/or test** (`suspicious_performance_flag: true` in
`models/metrics/tree_metrics.json` for: Task A RF, Task B RF, Task B
XGBoost, Task C RF, Task C XGBoost, Task D XGBoost; only Task A XGBoost and
Task D RF do not).

All required checks were performed for every flagged model:

1. **Project overlap**: re-verified zero train/validation/test project
   overlap for both datasets (`tests/test_phase5_split_consistency.py::test_zero_project_overlap_between_splits`).
2. **Terminal snapshot contamination**: re-verified zero
   `is_terminal_snapshot=True` rows in any split's modeling data
   (`test_zero_terminal_snapshots_in_modeling_data`).
3. **Feature importance** (Gini/gain, `top_feature_importances` in
   `tree_metrics.json`) and **4. SHAP** (see
   [SHAP_EXPLAINABILITY_REPORT.md](SHAP_EXPLAINABILITY_REPORT.md)) were
   inspected for every flagged model.
5. **Single-feature dominance check**: the single most important feature
   never exceeds ~50% of total importance in any model (Random Forest,
   Task B: `contractor_productivity_factor` at 49.9% -- the highest
   concentration observed). No model is driven by one feature to the
   near-exclusion of all others.
6. **Legitimacy check**: the dominant features across every flagged model
   are `contractor_productivity_factor` and `cost_tracking_gap_inr_cr` --
   both raw/engineered features already leakage-audited in Phase 3/4, with
   a maximum Pearson correlation of 0.697 against any target (well under
   the 0.95 leakage threshold; re-confirmed unchanged since the underlying
   45 predictors and targets have not changed since Phase 4).
7. **Synthetic-generator consistency**: this matches Phase 2's documented
   design -- `contractor_productivity_factor` is a per-project AR(1) latent
   trait that mechanistically drives both progress and cost trajectories
   through a shared channel (see
   [SYNTHETIC_DATA_METHODOLOGY.md](SYNTHETIC_DATA_METHODOLOGY.md) and
   [BASELINE_MODEL_REPORT.md](BASELINE_MODEL_REPORT.md) section 13, where
   the identical mechanism was already found and disclosed for the linear
   baselines).
8. **Conclusion: Verified legitimate synthetic-data signal.** No new
   leakage was introduced or discovered by moving to tree-based models; the
   strong performance is a continuation of the already-disclosed Phase 4
   finding, not a new artifact.

**One additional, distinct finding surfaced only by the tree models**: for
Task B's XGBoost model, the top global feature by Gini/gain importance is
**`categorical__state_Karnataka`** (15.8%), not `contractor_productivity_factor`
(7.5%) -- a different pattern from every other flagged model. Because
`state` has ~30+ categories one-hot encoded over only 280 training
projects, a handful of projects from one state can dominate a specific
split of a specific tree. This is plausibly a **high-cardinality/low-count
one-hot artifact** contributing to (not solely explaining) XGBoost's
overfitting gap on this task, rather than a new form of leakage --
`state` was already audited as a legitimate, non-target-derived raw
categorical column in Phase 3. It reinforces Phase 3's existing documented
recommendation (never applied, out of scope for both Phase 4 and 5) to
evaluate frequency/target encoding as an alternative to one-hot for
`state`/`contractor`.

## 7. Delay-regression cohort diagnostic (brief section 13, exploratory only)

Phase 4 found `final_delay_days` test R² (0.492) below validation R²
(0.751); Phase 5's tree models show the same pattern, slightly amplified
(validation up to 0.902, test only up to 0.571). This section checks
whether an obvious cohort-composition difference explains it. **This
diagnostic does not feed back into the split, model selection, or feature
set in any way** -- it is exploratory only, computed by
`scripts/train_tree_models.py::diagnose_delay_regression_cohorts` and saved
in `models/metrics/tree_metrics.json` under `delay_regression_cohort_diagnostic`.

| | Train (n=280) | Validation (n=60) | Test (n=60) |
|---|---|---|---|
| `project_length_km` mean (std) | 32.7 (21.3) | 30.2 (21.9) | 31.6 (23.2) |
| `original_contract_value_inr_cr` mean (std) | 728.4 (752.4) | 684.3 (707.9) | 750.2 (673.2) |
| `final_delay_days` mean (std) | 65.4 (86.2) | 69.0 (105.6) | 59.3 (98.4) |
| `final_delay_days` median | 60.5 | 61.0 | 45.0 |
| Top project type | Road Widening (2-4 lane), 27.5% | Road Widening (2-4 lane), 28.3% | Road Widening (2-4 lane), 23.3% |

Project size (length, contract value) and project-type mix are broadly
comparable across all three splits -- no dramatic shift. `final_delay_days`
distributions are also broadly comparable (means within ~10 days of each
other, similar spread), though the test median (45.0 days) is somewhat
lower than train/validation (~60-61 days), and each split's state mix
differs (expected with ~30+ states spread across only 60-280 projects per
split, not itself informative).

**Conclusion: no reliable cohort-composition explanation was established.**
The most plausible explanation, given section 5's finding that even the
linear baseline shows a comparable relative train→test drop on this
specific task, is ordinary sampling variance in a 60-project test cohort
combined with this task's inherent difficulty (delay duration in days has
much higher relative variance than the percentage-point cost target),
rather than a specific, identifiable distributional shift this analysis can
point to. This is stated explicitly per the brief's instruction to say so
when no reliable explanation can be found, rather than to guess.

## 8. Recommended model per task

| Task | Recommended model | Reason |
|---|---|---|
| A. Delay classification | **Random Forest** | Best test ROC-AUC (0.915 vs. 0.875 baseline) *and* the smallest train→test gap of the three models (7.2% relative) -- an improvement that is not bought with extra overfitting. |
| B. Delay regression | **XGBoost** | Best validation and test R² (0.571 test, +0.079 over baseline); its relative train→test degradation (40.0%) is not worse than the baseline's own (43.2%) on this specific task, so the "clearly overfit" exclusion in the brief does not apply comparatively -- all models struggle similarly here (section 7). |
| C. Cost classification | **Phase 4 baseline (Logistic Regression)** | Neither tree model beats it on test (RF ties at best, XGBoost is clearly worse and has the largest overfitting gap in this report for a classifier). Simpler, robust, and already well-calibrated. |
| D. Cost regression | **Phase 4 baseline (Linear Regression)** | Substantially and unambiguously outperforms both tree models on validation and test, with a far smaller train→test gap (3.4% vs. 20-31%). The clearest "baseline remains better" result in this report. |

This selection deliberately does **not** default to "tree model is more
sophisticated, therefore better" -- 2 of 4 tasks keep the Phase 4 baseline,
consistent with the brief's explicit instruction that all three outcomes
(beats/matches/underperforms) were valid going in.

## 9. Limitations

- Validation/test cohorts remain small (60 projects, ~1,250 rows each);
  point estimates carry meaningful sampling noise, as in Phase 4.
- Hyperparameter tuning was deliberately light (3 explicit candidates per
  model family per task, selected on validation only); a larger search was
  out of scope for this phase and might change which configuration is
  selected, though the qualitative baseline-vs-tree conclusions above are
  unlikely to reverse given the size of the observed gaps.
- The Task B cohort diagnostic (section 7) could not identify a specific
  cause for the validation-to-test gap; this remains an open question for
  a future phase with either more data or a different validation strategy
  (e.g. repeated/k-fold project-level cross-validation to quantify cohort
  variance directly).
- `contractor`/`state` one-hot encoding (50 and ~30+ categories
  respectively) was not revisited this phase despite the finding in
  section 6 that it plausibly contributes to XGBoost's Task B overfitting;
  Phase 3's frequency/target-encoding recommendation remains unapplied.
- These results describe a **synthetic, mechanistically-generated**
  dataset only (see [SYNTHETIC_DATA_METHODOLOGY.md](SYNTHETIC_DATA_METHODOLOGY.md)).
  The strength of the cost-task relationships (section 6) is a property of
  how the Phase 2 generator was built and must not be extrapolated to real
  NHAI project data.

## 10. Synthetic-data disclaimer

**Every number in this report describes performance on the synthetic
prototype dataset.** No claim is made or implied that any of these models
predict real NHAI highway project delays or cost overruns with the
accuracy shown here. Real-world predictive validity has not been
established and is out of scope for this project (see
[SYNTHETIC_DATA_METHODOLOGY.md](SYNTHETIC_DATA_METHODOLOGY.md) section 14).
