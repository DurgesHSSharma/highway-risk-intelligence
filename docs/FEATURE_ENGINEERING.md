# Phase 3 — Feature Engineering

Companion to [EDA_REPORT.md](EDA_REPORT.md). Describes the leakage audit,
the feature-availability classification, the engineered/temporal features,
the missing-value and outlier strategies, and the recommended train/
validation/test split methodology for Phase 4+. The implementation is
[`scripts/prepare_features.py`](../scripts/prepare_features.py), tested by
[`tests/test_prepare_features.py`](../tests/test_prepare_features.py).

**No ML models are trained here.** This document only prepares data.

## 1. Design principles

1. **Leakage-safety is structural, not a filter.** Every engineered
   feature for row `(project_id, reporting_month=M)` is computed only from
   that project's own rows at `reporting_month <= M`. Verified by
   `test_historical_features_never_use_future_rows`, which truncates each
   project's last 2 snapshots and asserts the historical features on the
   remaining (earlier) rows are byte-identical to the untruncated run — if
   any rolling/lag feature looked ahead, truncation would change it.
2. **Document, don't silently fix or hide.** Where Phase 2's dataset
   contains a genuine artifact (the terminal-row reconstruction issue,
   the two exact-duplicate columns), it is disclosed and handled
   explicitly (a flag column, a documented column drop) rather than
   silently dropped or silently left in.
3. **No imputation, no encoding, no row-filtering baked into the ML-ready
   files.** Those are modeling-time decisions for Phase 4. Phase 3 documents
   a recommended strategy for each (sections 5-7) but the processed CSVs
   carry raw categoricals and NaNs through unchanged.
4. **Every engineered feature has a clear interpretation.** No feature was
   added "because it might help" — each one is tied to a specific EDA
   finding or an explicit example in the Phase 3 brief.

## 2. Feature availability table

Classification per column of the raw dataset
(`data/synthetic/highway_project_snapshots.csv`, 46 columns). Categories:
`SAFE_CURRENT_SNAPSHOT`, `DERIVED_FROM_CURRENT_SNAPSHOT`,
`HISTORICAL_ALLOWED`, `FUTURE_LEAKAGE`, `TARGET`, `IDENTIFIER`,
`EXCLUDE_FROM_MODEL`.

| Column | Classification | Notes |
|---|---|---|
| `data_provenance` | `EXCLUDE_FROM_MODEL` | Constant ("SYNTHETIC"), metadata only |
| `project_id` | `IDENTIFIER` | Preserved in outputs, never a model input |
| `project_name` | `EXCLUDE_FROM_MODEL` | Free-text, ~1:1 with project_id, no generalizable signal |
| `highway_number` | `EXCLUDE_FROM_MODEL` | 328 unique values / 400 projects — near-identifier cardinality, won't generalize |
| `state` | `SAFE_CURRENT_SNAPSHOT` | Known before the project starts; raw categorical, kept |
| `project_type` | `SAFE_CURRENT_SNAPSHOT` | Known before the project starts; raw categorical, kept |
| `contractor` | `SAFE_CURRENT_SNAPSHOT` | Known before the project starts; 50 unique values, raw categorical, kept (~0.9% missing) |
| `project_length_km` | `SAFE_CURRENT_SNAPSHOT` | Static, kept |
| `original_contract_value_inr_cr` | `SAFE_CURRENT_SNAPSHOT` | Static, kept |
| `planned_start_date` | `SAFE_CURRENT_SNAPSHOT` | Used to derive temporal features; not itself a model input (see below) |
| `planned_completion_date` | `SAFE_CURRENT_SNAPSHOT` | Used to derive temporal features; not itself a model input |
| `planned_duration_months` | `SAFE_CURRENT_SNAPSHOT` | Static, kept |
| `reporting_month` | `IDENTIFIER` | Preserved in outputs, drives temporal feature calc, not itself a model input |
| `months_since_start` | `SAFE_CURRENT_SNAPSHOT` | Known at that snapshot, kept |
| `project_status` | `DERIVED_FROM_CURRENT_SNAPSHOT` | Not used as a raw model input; converted to `is_terminal_snapshot` flag (see section 3) |
| `planned_physical_progress_pct` | `SAFE_CURRENT_SNAPSHOT` | Pure function of the schedule, kept |
| `actual_physical_progress_pct` | `SAFE_CURRENT_SNAPSHOT` | Known at that snapshot, kept |
| `physical_progress_variance_pct` | `DERIVED_FROM_CURRENT_SNAPSHOT` | = actual - planned ("progress_gap"); kept as-is, not recomputed under a new name |
| `planned_financial_progress_pct` | `SAFE_CURRENT_SNAPSHOT` | Kept |
| `actual_financial_progress_pct` | `SAFE_CURRENT_SNAPSHOT` | Kept (~3.8% missing) |
| `financial_progress_variance_pct` | `DERIVED_FROM_CURRENT_SNAPSHOT` | = actual - planned ("financial_progress_gap"); kept |
| `planned_expenditure_inr_cr` | `EXCLUDE_FROM_MODEL` | **Exact duplicate** of `planned_cost_to_date_inr_cr` (max abs diff 0.0) — dropped |
| `actual_expenditure_inr_cr` | `SAFE_CURRENT_SNAPSHOT` | Kept (~3.8% missing); the "billing-based" cost track |
| `expenditure_variance_pct` | `EXCLUDE_FROM_MODEL` | **Exact duplicate** of `financial_progress_variance_pct` (max abs diff 0.0) — dropped |
| `land_acquisition_delay_days` ... `approval_delay_days` (10 cols) | `SAFE_CURRENT_SNAPSHOT` | Cumulative-to-date by construction (methodology sec. 12); genuinely known at the snapshot, kept |
| `contractor_productivity_factor` | `SAFE_CURRENT_SNAPSHOT` | Current-month AR(1) value, kept. Strongest single predictor found (section 4 below) |
| `planned_cost_to_date_inr_cr` | `SAFE_CURRENT_SNAPSHOT` | Kept (canonical version of the duplicate pair) |
| `actual_cost_to_date_inr_cr` | `SAFE_CURRENT_SNAPSHOT` | Kept; the "bottom-up" cost track (distinct from `actual_expenditure_inr_cr`) |
| `material_cost_inr_cr`, `labour_cost_inr_cr`, `equipment_cost_inr_cr`, `variation_cost_inr_cr`, `delay_related_cost_inr_cr` | `SAFE_CURRENT_SNAPSHOT` | Kept (`variation_cost_inr_cr` ~3.0% missing) |
| `final_delay_days` | `TARGET` | Delay-task target; excluded as a feature from `cost_features.csv` |
| `significant_delay` | `TARGET` | Delay-task target; excluded as a feature from `cost_features.csv` |
| `final_cost_overrun_pct` | `TARGET` | Cost-task target; excluded as a feature from `delay_features.csv` |
| `cost_overrun` | `TARGET` | Cost-task target; excluded as a feature from `delay_features.csv` |

No column was classified `FUTURE_LEAKAGE` in the strict sense (a feature
built from a later reporting_month or from a final-outcome value) — the
generator's forward-only simulation (methodology sec. 12) structurally
prevents that. The one leakage-*adjacent* finding is the terminal-row
issue below, which is about trivial reconstructability, not future data.

## 3. The terminal-snapshot finding (`is_terminal_snapshot`)

See [EDA_REPORT.md section 6](EDA_REPORT.md). On the row where
`project_status == "Completed"` (exactly 1 per project, 400 of 8,740
rows), `final_delay_days` is **exactly** equal to
`(reporting_month - planned_completion_date).days` — verified over all 400
rows, max absolute difference 0. Both inputs are contemporaneous to that
row, so this is not future-information leakage, but it makes that row's
prediction task trivial (a model — or even a lookup — reproduces the
target exactly from two already-available fields).

**Handling**: `prepare_features.py` keeps all 8,740 rows (does not drop
the Completed rows) and adds a boolean `is_terminal_snapshot` column.
**Recommendation for Phase 4**: filter `is_terminal_snapshot == False`
before training or evaluating the delay/cost-overrun prediction models,
since forecasting an outcome that has already occurred in that same row is
not a genuine forecasting task. If a "nowcast at completion" scenario is
ever wanted, it should be a clearly-labeled separate evaluation slice, not
mixed into the main train/test metrics.

## 4. Engineered features

All computed in `scripts/prepare_features.py::add_engineered_features`.

| Feature | Formula | Interpretation | Classification |
|---|---|---|---|
| `expenditure_gap_inr_cr` | `actual_expenditure_inr_cr - planned_cost_to_date_inr_cr` | Absolute-currency schedule-cost gap (billing-based) | `DERIVED_FROM_CURRENT_SNAPSHOT` |
| `cost_tracking_gap_inr_cr` | `actual_expenditure_inr_cr - actual_cost_to_date_inr_cr` | Divergence between the two independent cost tracks (billing-based vs bottom-up cost components); mean -39.7, std 122.8 in the checked-in data | `DERIVED_FROM_CURRENT_SNAPSHOT` |
| `delay_factor_count` | count of the 10 delay-day columns > 0 | Breadth of currently-active risk factors (0-10) | `DERIVED_FROM_CURRENT_SNAPSHOT`; `NaN` if any input missing (section 5) |
| `delay_factor_severity` | sum of the 10 delay-day columns | Total accumulated friction-days | `DERIVED_FROM_CURRENT_SNAPSHOT`; `NaN` if any input missing (section 5) |
| `project_age_ratio` | `months_since_start / planned_duration_months` | Schedule position; >1 means already past the planned duration | `SAFE_CURRENT_SNAPSHOT` |
| `months_to_planned_completion` | `planned_duration_months - months_since_start` | Months of schedule remaining (can be negative) | `SAFE_CURRENT_SNAPSHOT` |
| `schedule_pressure` | `(100 - actual_physical_progress_pct) / max(months_to_planned_completion, 1)` | Required monthly progress pace to still finish on time; spikes when overdue | `DERIVED_FROM_CURRENT_SNAPSHOT` |
| `progress_efficiency` | `actual_physical_progress_pct / max(planned_physical_progress_pct, 1e-6)`, capped at 5.0 | >1 ahead of schedule, <1 behind | `DERIVED_FROM_CURRENT_SNAPSHOT` |
| `cost_growth_rate` | `actual_cost_to_date_inr_cr / max(planned_cost_to_date_inr_cr, 1e-6)`, capped at 5.0 | >1 spending faster than planned pace | `DERIVED_FROM_CURRENT_SNAPSHOT` |
| `recent_progress_trend_3m` | trailing 3-month rolling mean of month-over-month progress increment | Recent execution pace | `HISTORICAL_ALLOWED` |
| `recent_cost_trend_3m` | trailing 3-month rolling mean of month-over-month cost increment | Recent spending pace | `HISTORICAL_ALLOWED` |
| `consecutive_underperforming_months` | running count of consecutive months where the progress increment was below the flat expected increment (`100/planned_duration_months`), reset on a month that meets it | Persistence of underperformance | `HISTORICAL_ALLOWED` |
| `recent_adverse_events_3m` | trailing 3-month rolling count of months where total delay-day severity increased | Recent frequency of new friction events | `HISTORICAL_ALLOWED` |
| `is_terminal_snapshot` | `project_status == "Completed"` | QA/split-aid flag, not a predictive feature (section 3) | `DERIVED_FROM_CURRENT_SNAPSHOT` |

**Not engineered as new columns**: `progress_gap` and
`financial_progress_gap` are conceptually identical to the already-present
`physical_progress_variance_pct` and `financial_progress_variance_pct`
(same formula, same values) — creating literal duplicate columns under
new names would itself be a meaningless/redundant feature, so the existing
raw columns are used directly instead (see the feature-availability table,
section 2).

### `progress_efficiency` / `cost_growth_rate` capping

Both ratios use a schedule/cost-to-date value in the denominator that is
near zero in a project's first 1-2 months, which explodes the ratio (raw,
uncapped values up to ~41.75 and ~42.45 respectively were observed). This
is a numerical-stability artifact of the ratio construction, not a
raw-data outlier (see [EDA_REPORT.md section 9](EDA_REPORT.md)), so both
are capped at `RATIO_CAP = 5.0` — affecting 273 rows (3.1%) for
`progress_efficiency` and 292 rows (3.3%) for `cost_growth_rate` in the
checked-in dataset. This is a feature-engineering stability decision
specific to these two derived ratios, disclosed here rather than silently
applied.

### `delay_factor_count` / `delay_factor_severity` and missingness

These 10 source columns are cumulative-to-date counters that should never
decrease within a project. Summing them with pandas' default
`skipna=True` (treating a missing value as 0) would make the composite
spuriously *decrease* whenever `weather_disruption_days` or
`equipment_unavailability_days` goes missing for a month — an artifact
caught during Phase 3 development by inspecting an example project's
trajectory (see [EDA_REPORT.md section 2](EDA_REPORT.md)). **Fix**: both
composites are `NaN` for a row whenever any of their 10 inputs is missing
(8,258 of 8,740 rows have both, i.e. ~5.5% are `NaN`), rather than a
silently-wrong lower number.

## 5. Missing-value strategy (documented, not applied in Phase 3)

| Column(s) | Missingness mechanism | Recommended Phase 4 strategy |
|---|---|---|
| `actual_financial_progress_pct`, `financial_progress_variance_pct`, `actual_expenditure_inr_cr` | Independent per-row MIS-reporting gap (~3.8%), nulled together | Forward-fill within `project_id` (these are progress-tracking values for a time series — the last known value is a better estimate than 0 or the column median) with a `_was_missing` indicator flag if a model benefits from it; do not fill with 0 (0 has a real meaning — no progress — and would be wrong here) |
| `variation_cost_inr_cr` | Independent per-row gap (~3.0%) | Median imputation is reasonable (it's one of five additive cost components; forward-fill is also defensible since it's cumulative) — either is a modeling-time choice, not a Phase 3 one |
| `equipment_unavailability_days`, `weather_disruption_days` | Independent per-row gap (~2.8%, ~2.8%) | Forward-fill within `project_id` (cumulative counters — same reasoning as above); this also naturally fixes the `delay_factor_count`/`severity` `NaN`s described in section 4 once applied |
| `contractor` | Independent per-row gap (~0.9%) | Fill with an explicit `"Unknown"` category, not the mode — 0 has no meaning for a categorical and imputing the mode would fabricate a specific contractor's identity for a row where it is genuinely unknown |
| `expenditure_gap_inr_cr`, `cost_tracking_gap_inr_cr` | Inherit missingness from `actual_expenditure_inr_cr` | Same as that source column |
| `delay_factor_count`, `delay_factor_severity` | Inherit missingness (any of 10 inputs missing) | Resolved automatically if the per-column forward-fill above is applied before recomputing these composites |

Phase 3 deliberately does **not** apply any of the above — the processed
CSVs carry the NaNs through unchanged, per instruction and per the
principle that model-specific preprocessing (e.g. fitting an imputer only
on a training fold) belongs in Phase 4 to avoid train/test leakage through
a globally-fit imputer.

## 6. Outlier strategy

See [EDA_REPORT.md section 9](EDA_REPORT.md) for the concrete numbers.
Summary of the policy applied: **no row was removed from the ML-ready
datasets for being an outlier.** All extreme values found (project size,
contract value, `final_delay_days`, `final_cost_overrun_pct`) were
classified `plausible` given infrastructure projects' legitimately
heavy-tailed delay/cost behavior, and none were classified `invalid`. The
only capping applied anywhere is the `progress_efficiency`/
`cost_growth_rate` ratio cap (section 4), which is a numerical-stability
fix for a derived feature, not a raw-data edit.

## 7. Categorical features

`state` (20 values), `project_type` (6 values), `contractor` (50 values)
are kept as raw strings in both processed CSVs — **not** one-hot encoded
in Phase 3, per instruction. Recommended Phase 4 encoding:

- `project_type` (6 values), `state` (20 values): one-hot or ordinal
  encoding is fine at this cardinality; fit the encoder on the training
  fold only.
- `contractor` (50 values, ~0.9% missing): one-hot would add 50 sparse
  columns for a 400-project dataset; frequency encoding or a
  target/mean encoding (fit strictly on the training fold, to avoid
  leaking test-set contractor performance into the encoding) is
  recommended instead.

`highway_number` and `project_name` are excluded entirely (section 2) —
too high-cardinality relative to the dataset to generalize.

## 8. Recommended train/validation/test split strategy (not implemented — Phase 4)

**The key constraint**: `final_delay_days`, `significant_delay`,
`final_cost_overrun_pct`, `cost_overrun` are *constant across every
snapshot of a project* (by construction — see
`validate_dataset.py::check_target_consistency_within_project`). This has
a consequence beyond the terminal-row issue in section 3:

- A **naive row-level random split** would put different months of the
  *same project* into both train and test. Since the target is identical
  across all of that project's rows, the model would effectively have
  already seen the exact test-row's answer during training (via an
  earlier snapshot of the same project) — leakage.
- A **naive global-calendar temporal split** (e.g. "train on
  reporting_month < 2024-01, test on reporting_month >= 2024-01") does
  not fix this either: a project whose lifetime straddles the cutoff would
  contribute early rows to train and later rows (same constant target) to
  test — the same project-level leakage.

**Recommendation**: split by **project group first** — every row of a
given `project_id` must land entirely in one split (e.g. scikit-learn's
`GroupShuffleSplit`/`GroupKFold` keyed on `project_id`). This is the
mandatory constraint. On top of that, a **temporal cohort stratification**
is recommended for realism: group projects by `planned_start_date` cohort
and hold out the most-recently-started cohort of projects as the test set,
to simulate "predicting for new projects not yet seen," rather than a
purely random project split. Combine both: group by `project_id`
(mandatory, prevents target leakage), stratify/order the group assignment
by `planned_start_date` (recommended, for realistic evaluation).

Independently of the split, section 3's recommendation still applies:
exclude `is_terminal_snapshot == True` rows from both the training and
evaluation sets used for the forecasting task.

**No split is implemented in Phase 3** — no model is trained, per
instruction. This section documents the methodology for Phase 4 to apply.

## 9. Output files

| File | Rows | Columns | Predictor columns | Target columns | Notes |
|---|---|---|---|---|---|
| `data/processed/delay_features.csv` | 8,740 | 50 | 45 (3 categorical + 42 numerical, see section 2/4) + `is_terminal_snapshot` flag + 2 identifiers | `final_delay_days`, `significant_delay` | `final_cost_overrun_pct`/`cost_overrun` excluded |
| `data/processed/cost_features.csv` | 8,740 | 50 | same 45 + `is_terminal_snapshot` flag + 2 identifiers | `final_cost_overrun_pct`, `cost_overrun` | `final_delay_days`/`significant_delay` excluded |

Both preserve `project_id` and `reporting_month`, contain no duplicate
`(project_id, reporting_month)` pairs, and are fully reproducible from the
raw synthetic dataset via:

```
cd scripts
../backend/.venv/Scripts/python.exe prepare_features.py
```

## 10. Limitations

- No model has been trained against these features; predictive value of
  any individual engineered feature is only supported by the correlation
  evidence in [EDA_REPORT.md](EDA_REPORT.md), not by an actual model
  evaluation (deferred to Phase 4+ by instruction).
- The missing-value and outlier strategies above are **recommendations**,
  not implemented preprocessing — the processed CSVs intentionally carry
  raw categoricals and NaNs through unchanged.
- `contractor`'s ~0.9% missingness is left as `NaN` (categorical) in the
  processed files, per section 5 — no `"Unknown"` fill has been applied
  yet.
- This entire pipeline operates on a synthetic dataset; see
  [SYNTHETIC_DATA_METHODOLOGY.md](SYNTHETIC_DATA_METHODOLOGY.md) section
  14 for what cannot be claimed from it.
