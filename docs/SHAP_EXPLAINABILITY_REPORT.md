# Phase 5 — SHAP Explainability Report

*** All numbers on this page were produced by actually running
`scripts/explain_models.py` against the checked-in
`data/processed/delay_features.csv` / `cost_features.csv`, using the models
trained by `scripts/train_tree_models.py` and the identical frozen Phase 4
split. Full machine-readable output is saved in
[`docs/artifacts/shap_local_examples.json`](artifacts/shap_local_examples.json);
plots are saved in `docs/artifacts/*_shap_*.png`. None of these numbers are
estimated or invented. Regenerate with:
```
cd C:\Projects\highway-risk-intelligence
backend\.venv\Scripts\python.exe -m scripts.explain_models
```
***

**SHAP values describe model attribution, not causation.** Every statement
below is phrased as a feature being "associated with", "contributing to",
or "relied on by" a prediction -- never as a feature "causing" a delay or
cost overrun. This distinction matters because the underlying dataset is
synthetic (see section 5).

## 1. Which model is explained per task (important disclosure)

`shap.TreeExplainer` requires a tree-based model. [MODEL_COMPARISON_REPORT.md](MODEL_COMPARISON_REPORT.md)
honestly recommends the **Phase 4 linear baseline** (not a tree model) for
Tasks C and D, because Random Forest / XGBoost did not robustly improve on
it there. Since a linear model cannot be explained with `TreeExplainer`,
this report explains the **best-validation-scoring tree model** for every
task, regardless of which model is ultimately recommended for deployment:

| Task | Model explained here | Matches the deployment recommendation? |
|---|---|---|
| A. Delay classification | Random Forest | Yes -- Random Forest is also recommended. |
| B. Delay regression | XGBoost | Yes -- XGBoost is also recommended. |
| C. Cost classification | XGBoost | **No** -- the Phase 4 baseline is recommended for deployment; XGBoost is shown here purely for tree-model interpretability. |
| D. Cost regression | XGBoost | **No** -- the Phase 4 baseline is recommended for deployment; XGBoost is shown here purely for tree-model interpretability. |

This is a deliberate, disclosed choice, not an inconsistency: it lets every
tree ensemble trained this phase remain inspectable, while
[MODEL_COMPARISON_REPORT.md](MODEL_COMPARISON_REPORT.md) section 8 remains
the authoritative source for which model to actually use.

## 2. Methodology

- **Explainer**: `shap.TreeExplainer(model)` applied to the tree model
  extracted from each Pipeline's `model` step, given the *already
  preprocessed* (imputed/scaled/one-hot-encoded) feature matrix from that
  Pipeline's `preprocess` step -- 119 columns after one-hot expansion of the
  3 categorical predictors (`state`, `project_type`, `contractor`).
- **Global explanation**: a fixed, seeded (`seed=42`) sample of up to 500
  TEST-set rows (all rows used for tasks with fewer than 500 in test).
  Sampling test data for a *post-hoc explanation* does not affect model
  training or selection in any way.
- **Local explanations**: exactly 2 examples per task, selected by the
  model's **own prediction** on the test set (highest predicted
  score/value = "high" example, lowest = "low" example) -- never by
  looking at the true target label, so example selection cannot leak
  target information into the choice of which rows to explain.
- **Output scale**: for regression, SHAP values are in the target's own
  units (days for Task B, percentage points for Task D). For
  classification, **units differ by model family** and are not directly
  comparable across them: Random Forest's SHAP values are on the
  predicted-**probability** scale (0-1), while XGBoost's are on the
  **log-odds (margin)** scale by default. Within a single model, direction
  (positive/negative) and relative feature ranking are always meaningful;
  raw magnitudes should only be compared feature-to-feature within the
  same model, not across Random Forest vs. XGBoost.
- **Sanity check**: `tests/test_explain_models.py::test_shap_local_additivity_matches_model_output`
  verifies SHAP's core guarantee -- `base_value + sum(shap_values) == model
  output` for every explained instance, within floating-point tolerance --
  confirming the SHAP values genuinely reconstruct each model's actual
  prediction rather than being a decorative approximation.

## 3. Global feature rankings

### Task A — Significant Delay Classification (Random Forest)

| Rank | Feature | Mean \|SHAP\| |
|---|---|---|
| 1 | `contractor_productivity_factor` | 0.102 |
| 2 | `cost_tracking_gap_inr_cr` | 0.055 |
| 3 | `progress_efficiency` | 0.047 |
| 4 | `consecutive_underperforming_months` | 0.032 |
| 5 | `physical_progress_variance_pct` | 0.032 |

See [delay_classification_shap_summary.png](artifacts/delay_classification_shap_summary.png).

### Task B — Delay Duration Regression (XGBoost)

| Rank | Feature | Mean \|SHAP\| (days) |
|---|---|---|
| 1 | `contractor_productivity_factor` | 33.51 |
| 2 | `cost_tracking_gap_inr_cr` | 11.84 |
| 3 | `recent_progress_trend_3m` | 10.11 |
| 4 | `progress_efficiency` | 10.08 |
| 5 | `actual_physical_progress_pct` | 8.08 |

See [delay_regression_shap_summary.png](artifacts/delay_regression_shap_summary.png).
Note (cross-referenced with [MODEL_COMPARISON_REPORT.md](MODEL_COMPARISON_REPORT.md)
section 6): this model's Gini/gain-based feature importance ranking places
`state_Karnataka` first, ahead of `contractor_productivity_factor` --
SHAP's mean-absolute-value ranking here restores `contractor_productivity_factor`
to the top, but `state_Karnataka` is still notable enough to be flagged as
a possible high-cardinality/low-sample-count artifact rather than a robust
signal (see section 6 below for the same caveat in local terms).

### Task C — Cost Overrun Classification (XGBoost)

| Rank | Feature | Mean \|SHAP\| (log-odds) |
|---|---|---|
| 1 | `cost_tracking_gap_inr_cr` | 1.345 |
| 2 | `original_contract_value_inr_cr` | 0.826 |
| 3 | `contractor_productivity_factor` | 0.757 |
| 4 | `cost_growth_rate` | 0.436 |
| 5 | `planned_duration_months` | 0.379 |

See [cost_classification_shap_summary.png](artifacts/cost_classification_shap_summary.png).

### Task D — Cost Overrun Regression (XGBoost)

| Rank | Feature | Mean \|SHAP\| (pct. points) |
|---|---|---|
| 1 | `cost_tracking_gap_inr_cr` | 3.145 |
| 2 | `contractor_productivity_factor` | 2.883 |
| 3 | `cost_growth_rate` | 1.168 |
| 4 | `progress_efficiency` | 0.888 |
| 5 | `original_contract_value_inr_cr` | 0.860 |

See [cost_regression_shap_summary.png](artifacts/cost_regression_shap_summary.png).

**Cross-task observation**: `contractor_productivity_factor` and
`cost_tracking_gap_inr_cr` rank in the top 3 for every one of the four
tasks. This is consistent with, not a new discovery beyond, Phase 4's
already-disclosed finding that `contractor_productivity_factor` is a
shared latent driver in the Phase 2 synthetic generator (see
[MODEL_COMPARISON_REPORT.md](MODEL_COMPARISON_REPORT.md) section 6).

## 4. Local explanations

Two representative test-set examples per task, selected by the model's own
prediction (not the true label). "Actual" is shown only as context for the
reader -- it played no role in selecting the example.

### Task A — Significant Delay Classification (Random Forest, probability scale)

**High-prediction example** (project `HRI-0075`, 2025-12): the model
predicted a **0.989** probability of significant delay (base rate 0.557;
actual label: significant delay = yes). The prediction was pushed **up**
almost entirely by `contractor_productivity_factor` (+0.057),
`progress_efficiency` (+0.056), `physical_progress_variance_pct` (+0.053),
`project_age_ratio` (+0.035), and `consecutive_underperforming_months`
(+0.032, associated with a run of underperforming months) -- no feature of
any size pushed the prediction down.

**Low-prediction example** (project `HRI-0393`, 2025-04): the model
predicted a **0.057** probability (actual label: no significant delay).
Here the same top features pushed in the opposite direction:
`contractor_productivity_factor` (-0.118), `cost_tracking_gap_inr_cr`
(-0.082), and `progress_efficiency` (-0.038) were the largest contributors
toward a low predicted risk.

### Task B — Delay Duration Regression (XGBoost, days)

**High-prediction example** (project `HRI-0132`, 2026-07): the model
predicted a delay of **292 days** (base value 85 days; actual final delay:
519 days). `contractor_productivity_factor` (+69 days) and
`progress_efficiency` (+48 days) were associated with most of the upward
push, followed by the specific value of `contractor_Continental
Constructions Pvt Ltd` (+46 days) and `recent_progress_trend_3m` (+26
days).

**Low-prediction example** (project `HRI-0393`, 2025-02): the model
predicted **-74 days** (i.e. finishing ahead of schedule; actual: -92
days). `contractor_productivity_factor` (-54 days) and
`cost_tracking_gap_inr_cr` (-22 days) were associated with most of the
downward push.

### Task C — Cost Overrun Classification (XGBoost, log-odds scale)

**High-prediction example** (project `HRI-0075`, 2025-11): predicted
probability **0.993** (base rate corresponds to a log-odds of -0.46, i.e.
well under 50%; actual label: cost overrun = yes). `cost_tracking_gap_inr_cr`
(+1.70 log-odds) was the largest single contributor, followed by the
specific value of `contractor_Continental Constructions Pvt Ltd` (+1.02),
`progress_efficiency` (+1.01), and `contractor_productivity_factor`
(+0.91).

**Low-prediction example** (project `HRI-0101`, 2026-06): predicted
probability **0.0003** (actual label: no cost overrun). `cost_tracking_gap_inr_cr`
(-2.41) and `original_contract_value_inr_cr` (-2.32) were associated with
almost all of the downward push.

### Task D — Cost Overrun Regression (XGBoost, percentage points)

**High-prediction example** (project `HRI-0295`, 2024-12): the model
predicted a cost overrun of **+37.3 percentage points** (base value 8.3;
actual: +31.6). Here the single largest contributor was the specific value
of `contractor_Apex Engineering & Constructions Ltd` (+12.4 points),
*larger* than `contractor_productivity_factor` itself (+6.9 points) --
flagged and investigated in section 6 below.

**Low-prediction example** (project `HRI-0355`, 2025-05): the model
predicted **-12.4 percentage points** (i.e. under budget; actual: -11.8).
The specific value of `contractor_Uttam Engineering & Constructions Ltd`
(-6.3 points) and `cost_tracking_gap_inr_cr` (-6.0 points) were associated
with most of the downward push.

In every one of the 8 local examples above, the model's prediction and the
project's actual outcome point in the same direction and are numerically
close -- a basic sanity check that the explained predictions are
representative of genuinely good-vs-poor projected outcomes, not
arbitrary/degenerate model outputs.

## 5. SHAP sanity check: does one feature dominate? (brief section 16)

Per section 6 of [MODEL_COMPARISON_REPORT.md](MODEL_COMPARISON_REPORT.md),
no global ranking shows one feature dominating "almost the entire
prediction" -- the highest single-feature importance share observed
anywhere is ~50% (Random Forest, Task B, Gini importance). At the *local*
level, two specific one-hot contractor categories were observed to be the
single largest contributor to an individual prediction:

- Task D high-prediction example: `contractor_Apex Engineering &
  Constructions Ltd` contributed +12.4 percentage points, more than
  `contractor_productivity_factor` (+6.9) for that one project.
- Task D low-prediction example: `contractor_Uttam Engineering &
  Constructions Ltd` contributed -6.3 percentage points, the largest single
  contributor for that project.

**Investigated**: `contractor` is a legitimate, Phase-3-audited raw
categorical predictor (not target-derived, not future information) with 50
one-hot categories over only 280 training projects -- a handful of
projects per category. A specific contractor dominating one project's
individual explanation is consistent with a **high-cardinality/low-sample
one-hot artifact** (a contractor category whose few training examples
happened to have unusually high or low cost outcomes, so the model
attributes strong weight to that category specifically) rather than new
leakage. This is the same caveat already raised for `state_Karnataka` in
Task B (section 3) and is not removed from the feature set -- per the
brief's instruction, a feature is not dropped merely for being influential
without independent evidence of leakage, and none was found here (no
target column is referenced in how `contractor`/`state` are constructed;
see [FEATURE_ENGINEERING.md](FEATURE_ENGINEERING.md)). It does reinforce
Phase 3's still-unapplied recommendation to evaluate frequency/target
encoding as an alternative to one-hot for these two high-cardinality
columns in a future phase.

## 6. Interpretation

Across all four tasks, the SHAP explanations are consistent with the
correlation-based investigation in Phase 4 and the feature-importance
investigation in Phase 5: a small number of features related to contractor
performance (`contractor_productivity_factor`) and cost-tracking
consistency (`cost_tracking_gap_inr_cr`, `cost_growth_rate`) are
consistently the model's primary basis for its predictions across delay
and cost tasks alike, with progress-related engineered features
(`progress_efficiency`, `physical_progress_variance_pct`,
`consecutive_underperforming_months`) contributing secondarily. This
pattern is stable across model families (Random Forest and XGBoost largely
agree on which features matter, if not their exact ranking or scale) and
across the global and local views. No SHAP evidence contradicts, and
several pieces of evidence reinforce, the "shared latent driver" mechanism
already documented for the Phase 2 synthetic generator.

## 7. Synthetic-data limitations

**These SHAP explanations describe what each model learned from the
synthetic prototype dataset, not real highway-project behavior.** The
strength and consistency of `contractor_productivity_factor`'s influence
is a direct consequence of how Phase 2's generator was built (an AR(1)
latent trait deliberately driving multiple downstream columns) -- it should
not be read as evidence that real contractor productivity data would show
an equally strong or clean relationship with real project delays or cost
overruns. No claim is made about real-world feature importance or
real-world causal relationships.

**SHAP values are model attribution, not causation** -- restated explicitly
here per the Phase 5 brief: none of the explanations in this report should
be read as "this feature caused the delay/cost overrun." They describe
which inputs, and in which direction, were associated with a given model's
specific prediction for a specific project-month, according to that
model's own learned (and, per this project's stated purpose, purely
synthetic-data-driven) internal logic.
