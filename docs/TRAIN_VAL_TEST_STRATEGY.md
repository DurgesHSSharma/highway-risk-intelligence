# Phase 4 — Train / Validation / Test Strategy

Companion to [BASELINE_MODEL_REPORT.md](BASELINE_MODEL_REPORT.md). Describes
the leakage-safe split methodology implemented in
[`scripts/data_split.py`](../scripts/data_split.py) and tested by
[`tests/test_data_split.py`](../tests/test_data_split.py). All numbers below
come from actually running `scripts.data_split` and
`scripts.train_baseline_models` against the checked-in
`data/processed/delay_features.csv` / `cost_features.csv` (seed 42);
none are estimated.

## 1. Dataset used

`data/processed/delay_features.csv` and `data/processed/cost_features.csv`
(8,740 rows each, 400 projects, built by Phase 3's
`scripts/prepare_features.py` from `data/synthetic/highway_project_snapshots.csv`).
Both files share identical `project_id`/`reporting_month`/predictor/
`is_terminal_snapshot` columns and therefore produce byte-identical split
assignments (verified: the split metadata computed independently from each
file is identical).

## 2. Why a project-level split is mandatory

`final_delay_days`, `significant_delay`, `final_cost_overrun_pct`, and
`cost_overrun` are constant across every snapshot row of a given
`project_id` (Phase 2/3 finding, re-verified by
`test_targets_values_match_source` and `validate_dataset.py`'s
`check_target_consistency_within_project`). A row-level random split, or
even a naive global-calendar cutoff, would place different monthly
snapshots of the *same* project into both train and test -- since the
target is identical across all of that project's rows, the model would
have effectively already seen the test row's answer during training via an
earlier snapshot of the same project. This is why `project_level_split`
guarantees, and `test_no_project_appears_in_more_than_one_split` /
`test_project_level_grouping_preserved_at_row_level` verify:

```
TRAIN projects ∩ VALIDATION projects = ∅
TRAIN projects ∩ TEST projects = ∅
VALIDATION projects ∩ TEST projects = ∅
```

## 3. Terminal snapshot exclusion

Phase 3 found that the one `project_status == "Completed"` row per project
(400 of 8,740 rows) makes `final_delay_days` exactly reconstructible from
that row's own `reporting_month - planned_completion_date` (max abs diff =
0 across all 400 terminal rows), making prediction trivial on those rows.
`project_level_split` drops `is_terminal_snapshot == True` rows from all
three splits by default (`exclude_terminal=True`), after project
assignment -- it never changes which split a project's *other* rows sit
in, it only removes that project's single terminal row from the modeling
data. The source datasets are untouched; the rows are excluded only at
split time.

| | Rows | Projects represented |
|---|---|---|
| Terminal rows excluded, train | 280 | 280 (1 per project) |
| Terminal rows excluded, validation | 60 | 60 (1 per project) |
| Terminal rows excluded, test | 60 | 60 (1 per project) |
| **Total excluded** | **400** | **400** |
| Remaining rows (all 3 splits) | 8,340 | 400 |

## 4. Split assignment rule (data-driven, not assumed)

Before choosing a rule, the actual data was inspected:

- `planned_start_date` for the 400 projects spans **2019-01-01 to
  2024-06-01**, distributed across years as 2019=76, 2020=65, 2021=76,
  2022=69, 2023=72, 2024=42 (partial year) -- a reasonably even
  year-over-year spread, not a single narrow cluster or a long tail that
  would make a chronological cut degenerate.
- `planned_start_date` has **month-level granularity**: only 65 unique
  values across 400 projects, with up to 15 projects sharing the exact
  same start month.
- Snapshots per project range from 10 to 74 (mean 21.85, median 19.0); no
  project's simulation hit the internal month cap (Phase 3 finding), so no
  trajectory is right-censored.

**Chosen rule**: a **project-level chronological cohort split**. All 400
projects are ordered by `planned_start_date`; ties on an identical start
month are broken by a seeded random draw (`np.random.default_rng(seed=42)`,
drawn once per project in alphabetical `project_id` order so the result
does not depend on input row order). The earliest 70% of projects
(by count) are assigned to train, the next 15% to validation, and the
most-recently-started 15% to test.

**Why chronological rather than a purely random 70/15/15 project split**:
the intended use case (see Phase 4 brief section 9) is "predict a
project's eventual outcome using only information available today, for a
project not yet seen." Holding out the most-recently-started cohort as
test simulates that scenario more realistically than a random shuffle of
projects across the same 2019-2024 window would. A quick data check (not
guessed) confirmed this doesn't produce a degenerate split -- see class
balance below. No target/outcome value was used to decide any project's
split membership; assignment is based solely on `planned_start_date`.

**Why not a naive global-calendar `reporting_month` cutoff**: a project's
`reporting_month` values span its own multi-year lifetime (e.g. one
project ranges from 2023-04 to 2026-01), so a single global calendar
cutoff would still split one project's own snapshots across train and
test -- the same project-level leakage described in section 2. Ordering
by `planned_start_date` (a single fixed, pre-project value) and assigning
each project's *entire* row set to one split avoids this entirely.

## 5. Split sizes

| Split | Projects | Rows (post-terminal-exclusion) | `planned_start_date` range | `reporting_month` range |
|---|---|---|---|---|
| Train | 280 | 5,834 | 2019-01-01 to 2022-11-01 | 2019-02 to 2028-01 |
| Validation | 60 | 1,234 | 2022-11-01 to 2023-08-01 | 2022-12 to 2028-12 |
| Test | 60 | 1,272 | 2023-09-01 to 2024-06-01 | 2023-10 to 2029-02 |
| **Total** | **400** | **8,340** | 2019-01-01 to 2024-06-01 | 2019-02 to 2029-02 |

(`reporting_month` ranges overlap across splits because a project's
snapshots run for years after its start date -- this is expected and
harmless: it is `planned_start_date`, not `reporting_month`, that
determines split membership, and no project's own rows are ever split
across two groups.)

## 6. Class distribution per split (row-level, after terminal exclusion)

| Target | Train (n=5,834) | Validation (n=1,234) | Test (n=1,272) |
|---|---|---|---|
| `significant_delay` (0/1) | 2,585 / 3,249 (55.7% positive) | 494 / 740 (60.0% positive) | 662 / 610 (48.0% positive) |
| `cost_overrun` (0/1) | 3,565 / 2,269 (38.9% positive) | 612 / 622 (50.4% positive) | 832 / 440 (34.6% positive) |

No split has a degenerate (near-0% or near-100%) positive rate for either
binary target, so ROC-AUC/PR-AUC are computable everywhere in this run
(see [BASELINE_MODEL_REPORT.md](BASELINE_MODEL_REPORT.md)). `project_level_split`
and the training script check `nunique() < 2` per split and would report
AUC metrics as `null` with an explicit reason if this were ever not the
case (see `tests/test_train_baseline_models.py::test_roc_auc_reported_as_unavailable_when_split_has_one_class`).

## 7. Reproducibility

- **Seed**: 42 (`scripts.data_split.DEFAULT_SEED`), used only to break ties
  among projects sharing an identical `planned_start_date` month.
- **Determinism**: `assign_project_splits` sorts projects alphabetically by
  `project_id` before drawing tie-break values from a seeded
  `numpy.random.Generator`, so the result is independent of the input
  DataFrame's row order (verified by
  `test_assignment_independent_of_input_order`). Running the full pipeline
  twice produces identical project assignments, identical row assignments,
  and identical metadata (verified by `test_split_is_deterministic`, which
  asserts full DataFrame equality, not just row counts).
- **Dataset version**: `data/synthetic/highway_project_snapshots.csv`
  (seed 42, 400 projects, 8,740 rows -- unchanged since Phase 2) via
  `data/processed/{delay,cost}_features.csv` (unchanged since Phase 3).

## 8. Leakage safeguards implemented

1. Project-level grouping (section 2), enforced by an internal assertion in
   `project_level_split` and independently checked by
   `test_no_project_appears_in_more_than_one_split` and
   `test_project_level_grouping_preserved_at_row_level`.
2. Terminal snapshot exclusion (section 3), checked by
   `test_no_terminal_snapshot_in_any_split`.
3. Split assignment uses only `planned_start_date` -- never a target/outcome
   column -- checked by construction (`assign_project_splits` never reads
   any target column) and by the fact that `assign_project_splits` accepts
   only a list of `project_id`s, not the feature table.
4. All preprocessing (imputation, scaling, one-hot encoding) is fit only
   inside each model's `.fit(X_train, y_train)` call -- see
   [BASELINE_MODEL_REPORT.md](BASELINE_MODEL_REPORT.md) section
   "Preprocessing" and
   `tests/test_train_baseline_models.py::test_preprocessing_fit_parameters_come_only_from_training_data`,
   which demonstrates behaviorally (not just by code inspection) that
   injecting an extreme value into validation-only rows does not change the
   fitted imputer/scaler statistics.
5. No target from one task ever appears as a predictor for another task
   (inherited from Phase 3's `delay_features.csv` / `cost_features.csv`
   separation; re-checked by `test_targets_never_appear_in_predictor_columns`).

## 9. Limitations

- The chronological-cohort rule is a **cohort-level** split (whole projects
  ordered by start date), not a strict global time-based holdout on
  `reporting_month` -- a project that started early but is still reporting
  snapshots in 2028 remains in train, and the test set's `reporting_month`
  values overlap with train's. This is intentional (section 2) but means
  this is not a pure "train on the past, test on the future" backtest in
  calendar-month terms; it is a "train on earlier-started projects, test on
  later-started projects" split.
- With only 400 projects, validation/test cohorts of 60 projects each are
  modest in absolute size; per-split class-balance and metric estimates
  (section 6, and the baseline report) carry meaningful sampling noise.
- This entire split operates on a **synthetic** dataset (see
  [SYNTHETIC_DATA_METHODOLOGY.md](SYNTHETIC_DATA_METHODOLOGY.md)); the
  split methodology itself is dataset-agnostic and reusable, but the
  reported class-balance/date-range numbers describe this specific
  synthetic run, not real highway projects.
