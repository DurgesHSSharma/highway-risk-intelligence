# Phase 3 — EDA Report

*** All numbers on this page were computed from the checked-in
`data/synthetic/highway_project_snapshots.csv` (seed `42`, 400 projects,
8,740 rows) by running `scripts/eda_report.py`. None are estimated or
invented. Regenerate with:
```
cd scripts
../backend/.venv/Scripts/python.exe eda_report.py
```
to reproduce every figure and plot on this page exactly. ***

This is exploratory analysis of a **SYNTHETIC** dataset (see
[SYNTHETIC_DATA_METHODOLOGY.md](SYNTHETIC_DATA_METHODOLOGY.md)). Findings
below describe patterns *in the simulation*, not real highway projects.
Relationships are described as "associated with", never "causes" — the
generator's mechanics are the only genuine causal story, and even those are
stochastic (see methodology doc section 6).

## 1. Dataset overview

| Metric | Value |
|---|---|
| Rows (snapshots) | 8,740 |
| Columns | 46 |
| Unique projects | 400 |
| Reporting-month range | 2019-02 to 2029-03 |
| Snapshots per project | mean 21.85, median 19.0, min 10, max 74 |
| `project_status` | Ongoing: 8,340 rows · Completed: 400 rows (exactly 1 per project) |

No full-row duplicates and no duplicate `(project_id, reporting_month)`
pairs (0 in both cases) — confirmed by `scripts/validate_dataset.py` and
re-confirmed here.

## 2. Missing values

| Column | % missing |
|---|---|
| `actual_financial_progress_pct` | 3.776% |
| `financial_progress_variance_pct` | 3.776% |
| `actual_expenditure_inr_cr` | 3.776% |
| `expenditure_variance_pct` | 3.776% |
| `variation_cost_inr_cr` | 3.043% |
| `equipment_unavailability_days` | 2.838% |
| `weather_disruption_days` | 2.757% |
| `contractor` | 0.915% |

All other 38 columns — including every identifier and all 4 target columns
— have 0% missing.

**Is the missingness informative?** Per
[SYNTHETIC_DATA_METHODOLOGY.md section 11](SYNTHETIC_DATA_METHODOLOGY.md),
this missingness is applied as an independent per-row Bernoulli draw on a
fixed list of "softer" MIS-reporting fields, not correlated with any
project trait. A direct check on `actual_financial_progress_pct` supports
this: mean `final_delay_days` on rows where it is missing is 78.6 vs 85.8
where present (row-level, target repeated across a project's rows) — a
small difference relative to `final_delay_days`'s std of 91.0, and this
column's missingness by construction has nothing to do with the eventual
outcome. **Missingness is not treated as informative here** and no
missingness-indicator features were engineered from it; see
[FEATURE_ENGINEERING.md](FEATURE_ENGINEERING.md) "Missing-value strategy"
for the documented per-column handling recommendation.

One consequence discovered while building the feature pipeline: the 10
delay-day columns are **cumulative-to-date counters** that should never
decrease within a project. Composite features that sum them
(`delay_factor_count`, `delay_factor_severity`) would spuriously *drop* in
a month where `weather_disruption_days` or `equipment_unavailability_days`
happens to be missing, if missing were treated as 0 (pandas' default
`sum(skipna=True)`). This was caught by inspecting an example project's
trajectory (`HRI`-prefixed project, months 2024-02/2024-03: raw
`weather_disruption_days` goes `43.9 -> NaN -> NaN` while all other
components hold or increase). **Fix**: both composites are `NaN` for a row
whenever any of their 10 inputs is missing, rather than silently
under-counting. See `scripts/prepare_features.py`'s `add_engineered_features`.

## 3. Duplicates and invalid values

| Check | Result |
|---|---|
| Full duplicate rows | 0 |
| Duplicate `(project_id, reporting_month)` | 0 |
| `actual_physical_progress_pct` outside [0,100] | 0 |
| Negative values in any delay-day or cost column | 0 |
| `planned_completion_date <= planned_start_date` | 0 |

No invalid values were found. This matches `validate_dataset.py`'s 18/18
passing checks (0 warnings, 0 failures) on this exact file.

## 4. Numerical distributions (row level, n=8,740 unless noted)

| Feature | Mean | Std | Min | 5% | 50% | 95% | Max |
|---|---|---|---|---|---|---|---|
| `project_length_km` | 40.28 | 25.53 | 1.00 | 3.80 | 36.64 | 91.63 | 111.07 |
| `original_contract_value_inr_cr` | 1017.96 | 976.30 | 70.48 | 169.64 | 627.70 | 3128.39 | 5093.39 |
| `planned_duration_months` | 23.95 | 11.90 | 12 | 12 | 21 | 51 | 60 |
| `actual_physical_progress_pct` | 53.16 | 29.46 | 0.77 | 7.37 | 52.93 | 99.52 | 100.00 |
| `physical_progress_variance_pct` | -4.03 | 10.42 | -42.79 | -22.94 | -2.28 | 9.89 | 16.83 |
| `contractor_productivity_factor` | 0.977 | 0.138 | 0.492 | 0.746 | 0.979 | 1.200 | 1.35 |
| `weather_disruption_days` | 41.23 | 35.56 | 0 | 2.2 | 32.5 | 112.92 | 235.8 |
| `land_acquisition_delay_days` | 14.07 | 21.68 | 0 | 0 | 4.4 | 64.73 | 137.2 |

`weather_disruption_days` runs highest of the 10 delay factors because it
accrues every month (seasonal exposure), not only on discrete occurrence
draws like the others — consistent with the generator design
(`_monsoon_factor`, methodology section 6).

`physical_progress_variance_pct` is centered slightly negative (mean
-4.03), i.e. the average snapshot is a bit behind its planned S-curve —
plausible given delay factors are net additive friction with no
"ahead-of-schedule" mechanism of comparable strength in the generator.

## 5. Target analysis (project level, n=400)

| Target | Value |
|---|---|
| `significant_delay` rate | 49.25% (197/400) |
| `cost_overrun` rate | 38.25% (153/400) |
| `final_delay_days` | mean 65.0, median 59.0, std 91.0, min -153, max 672 |
| `final_cost_overrun_pct` | mean 7.50%, median 6.78%, std 12.02%, min -16.42%, max 44.50% |
| `corr(final_delay_days, final_cost_overrun_pct)` | 0.68 |

**Negative `final_delay_days`** (52 of 400 projects, 13.0%) and
**negative `final_cost_overrun_pct`** (121 of 400, 30.3%) represent
projects that finished early / under budget. Per
`generate_dataset.py`, `final_delay_days` is simply
`(actual completion month - planned_completion_date)` and
`final_cost_overrun_pct` is `(actual final cost - contract value) /
contract value * 100` — both are unbounded-sign by construction, and a
sufficiently productive contractor / low-friction trajectory can finish
early or under budget. **These values are preserved, not clipped**, per
the Phase 2 methodology and this phase's instruction to document rather
than remove them.

Class balance for both binary targets is reasonably close to 50/50 (not
degenerate) — `validate_dataset.py`'s `target_distribution` check (which
warns below 2% or above 98%) passes cleanly.

## 6. Terminal-snapshot check (critical finding — see leakage audit, section 8)

Every project has exactly one row with `project_status == "Completed"`
(400 of 8,740 rows, 4.58%), and on every one of those rows,
`actual_physical_progress_pct == 100.0` exactly. Checking whether
`final_delay_days` can be reconstructed from that row's own
`reporting_month` and `planned_completion_date`:

```
derived_delay = (reporting_month - planned_completion_date).days
max |derived_delay - final_delay_days| across all 400 Completed rows = 0
```

**The reconstruction is exact, every time.** This is expected by
construction (`final_delay_days` literally is
`reporting_month - planned_completion_date` measured at the completion
row — see methodology section 8) but it matters for feature engineering:
see section 8 below.

## 7. Synthetic-data realism checks

Correlations below use each project's **final cumulative snapshot**
(the Completed row), since that carries the full accumulated delay/cost
history.

| Delay factor | corr with `final_delay_days` |
|---|---|
| `weather_disruption_days` | 0.383 |
| `material_delay_days` | 0.271 |
| `labour_shortage_days` | 0.267 |
| `approval_delay_days` | 0.201 |
| `equipment_unavailability_days` | 0.200 |
| `land_acquisition_delay_days` | 0.168 |
| `environment_clearance_delay_days` | 0.167 |
| `design_change_delay_days` | 0.127 |
| `utility_shifting_delay_days` | 0.091 |
| `traffic_diversion_delay_days` | 0.090 |

All 10 correlations are positive, as expected (more of any friction factor
is associated with more delay). `weather_disruption_days` is strongest,
consistent with it being the largest and most persistently-accruing
factor (see section 4).

`contractor_productivity_factor` (final snapshot) correlates **-0.685**
with `final_delay_days` and **-0.683** with `final_cost_overrun_pct` — a
strong, real, but non-deterministic relationship (contractor quality is a
latent trait that drives the AR(1) productivity process, per methodology
section 5). This is the single strongest predictor found anywhere in this
dataset and is directionally exactly what the generator's design intends.

**`project_type` vs targets** (project-level means):

| project_type | final_delay_days | final_cost_overrun_pct |
|---|---|---|
| Expressway | 88.7 | 4.2% |
| Road Widening (4 to 6 lane) | 79.8 | 9.4% |
| Bridge/ROB/Flyover | 72.7 | 7.8% |
| Greenfield Highway | 63.0 | 6.6% |
| Bypass/Ring Road | 55.2 | 7.8% |
| Road Widening (2 to 4 lane) | 49.8 | 7.2% |

Expressways show the highest average delay but the lowest average cost
overrun — plausible given they have the slowest planned pace (`pace=1.8`
km/month in `PROJECT_TYPE_PARAMS`, the slowest of all 6 types) making
schedule slip more likely, while their cost structure is dominated by
large, relatively predictable per-km costs.

**`state` vs `significant_delay` rate** does *not* cleanly track the
generator's `STATE_RISK_MULTIPLIER` ranking (e.g. Bihar is set to 1.25x
risk but observed at 52.0%, below several states set lower, like Telangana
at 0.95x but observed at 63.2%). With only 11-31 projects per state, this
is consistent with sampling noise dominating a real but modest per-state
signal — exactly what
[SYNTHETIC_DATA_METHODOLOGY.md section 13](SYNTHETIC_DATA_METHODOLOGY.md)
already discloses ("state/monsoon multipliers are illustrative... not
calibrated to real per-state project data"). This is noted as a
**limitation**, not a bug: state should be used as a raw categorical
predictor, not read as a calibrated regional risk ranking.

**Project size vs cost/delay behavior**: `project_length_km` correlates
+0.14 with `final_delay_days` (larger projects modestly more delay-prone)
but -0.08 with `final_cost_overrun_pct`; `original_contract_value_inr_cr`
shows a similar pattern (+0.20 delay, -0.09 cost overrun). Larger/costlier
projects are *slightly* more exposed to schedule slip but not to
proportional cost escalation in this simulation — plausible since delay
friction (land/utility/weather days) scales with project footprint while
`final_cost_overrun_pct` is a *percentage* of a contract value that itself
scales with size.

**Design/approval delay vs cost**: `design_change_delay_days` correlates
+0.16 and `approval_delay_days` +0.14 with `final_cost_overrun_pct`
(row-level, ongoing snapshots) — weak-to-moderate and directionally
correct, consistent with the generator routing design/approval days into
`variation_cost_inr_cr` (methodology section 7).

## 8. Leakage audit summary

Full feature-by-feature classification is in
[FEATURE_ENGINEERING.md](FEATURE_ENGINEERING.md) section "Feature
availability table". Headline findings:

1. **No raw feature exceeds the automated `|corr| > 0.95` leakage
   threshold** against either continuous target (`validate_dataset.py`'s
   `check_leakage_correlation`; strongest is `contractor_productivity_factor`
   at ~0.71 using all rows, ~0.68-0.71 at the final snapshot — real,
   substantial, not deterministic).
2. **The 400 terminal (`Completed`) snapshots make `final_delay_days`
   exactly, deterministically reconstructible** from that row's own
   `reporting_month` and `planned_completion_date` (section 6). This is
   *not* future-information leakage (both inputs are contemporaneous to
   that row) but it makes prediction trivial on those specific rows.
   **Decision**: these rows are kept (not dropped) in the ML-ready
   datasets and flagged with a new `is_terminal_snapshot` column, so
   Phase 4 can explicitly exclude them from training/evaluation of a
   genuine forecasting task rather than have them silently vanish or
   silently inflate apparent accuracy.
3. **Two exact-duplicate raw columns**: `planned_expenditure_inr_cr` ==
   `planned_cost_to_date_inr_cr` (max abs diff 0.0) and
   `expenditure_variance_pct` == `financial_progress_variance_pct` (max
   abs diff 0.0). One of each pair is dropped in the ML-ready datasets to
   avoid meaningless duplicated/collinear columns.
4. **All 4 target columns** (`final_delay_days`, `significant_delay`,
   `final_cost_overrun_pct`, `cost_overrun`) are constant across every
   snapshot of a project (by construction — verified by
   `validate_dataset.py`'s `check_target_consistency_within_project`) and
   must never appear as a predictor for the *other* task (e.g.
   `final_cost_overrun_pct` must not be a feature when predicting
   `final_delay_days`) since both are equally "future" relative to any
   pre-completion snapshot. Enforced structurally in
   `scripts/prepare_features.py` (`delay_features.csv` carries only the
   delay targets, `cost_features.csv` only the cost targets) and checked
   by `tests/test_prepare_features.py::test_targets_correctly_separated_no_cross_task_leakage`.
5. **No project hit the simulation's month cap** (`planned_duration_months
   * 3`, floor 30) — 0 of 400 projects were truncated, so there is no
   hidden right-censoring in `final_delay_days`/`final_cost_overrun_pct`.

## 9. Outlier findings

| Check | Result | Classification |
|---|---|---|
| `project_length_km` > 150 | 0 | n/a |
| Top `original_contract_value_inr_cr` | 5,093 cr (HRI-0028) | Plausible — a large Expressway-class project |
| Top `final_delay_days` | 672 (HRI-0272) | Plausible — extreme tail of a heavy-tailed friction process, not a caps hit |
| Bottom `final_delay_days` | -153 (HRI-0158) | Plausible — low-friction, high-productivity trajectory |
| Top `final_cost_overrun_pct` | 44.50% (HRI-0132) | Plausible, but narrower than some real audited extremes (CAG has flagged >50% on individual projects) — a documented generator limitation, not a data error |
| Bottom `final_cost_overrun_pct` | -16.42% (HRI-0213) | Plausible under-budget outcome |

No values were classified as **invalid** and none were removed. This
matches the project's stated outlier policy: infrastructure projects can
legitimately have unusual delays/costs, and only clearly-invalid values
(none found) would be removed.

`progress_efficiency` and `cost_growth_rate` (engineered ratios, see
[FEATURE_ENGINEERING.md](FEATURE_ENGINEERING.md)) do produce extreme
values (up to ~42x) in a project's first 1-2 months when the planned-pct
denominator is near zero — this is a **numerical-stability artifact of
the ratio construction**, not a raw-data outlier, and is handled by
capping (documented separately, not conflated with the raw-data outlier
policy above).

## 10. Temporal behavior

- `months_since_start` ranges 1-74; `project_age_ratio` (=
  `months_since_start / planned_duration_months`) ranges 0.017 to 1.556
  across ongoing snapshots — 652 of 8,340 ongoing rows (7.8%) already have
  `project_age_ratio > 1`, i.e. the project is still running past its
  originally planned completion date.
- `progress_increment` (month-over-month change in
  `actual_physical_progress_pct`, computed with a strictly backward-looking
  `diff()` per project) is never negative (min 0.0 across 8,340 ongoing
  rows) — consistent with `generate_dataset.py` clamping
  `actual_increment = max(0.0, ...)`.
- No project's simulation hit the month cap (section 8, point 5) — the
  full observed trajectory for every project is genuine, not truncated.

## 11. Limitations (carried over and Phase-3-specific)

- This is a **SYNTHETIC** dataset; see
  [SYNTHETIC_DATA_METHODOLOGY.md section 14](SYNTHETIC_DATA_METHODOLOGY.md)
  for what it cannot prove. Every finding above describes the simulation,
  not real highway projects.
- State/monsoon risk multipliers are illustrative and, as shown in section
  7, the small per-state sample (11-31 projects) means observed rates
  don't cleanly track the input multipliers — a real limitation of using
  `state` as a calibrated risk signal here.
- `progress_efficiency`/`cost_growth_rate` are unstable in a project's
  first 1-2 months (near-zero-denominator ratios); capped at 5.0 in the
  ML-ready datasets (see FEATURE_ENGINEERING.md).
- `delay_factor_count`/`delay_factor_severity` are `NaN` (not a
  silently-wrong number) for the ~5.5% of rows where a component delay-day
  column is missing that month — see section 2.
- The cost-overrun tail (max ~44.5%) is narrower than some real audited
  extremes reported by CAG (>50% on individual projects) — a known,
  disclosed generator limitation (methodology section 14), not corrected
  here since Phase 3 must not change Phase 2's methodology without a
  genuine defect, and none was found.

## 12. Plots

Saved under `docs/artifacts/` (regenerate via `scripts/eda_report.py`):

- `target_distributions.png` — `final_delay_days` and `final_cost_overrun_pct` histograms
- `missingness.png` — % missing by column
- `progress_gap_distribution.png` — `physical_progress_variance_pct`, ongoing snapshots
- `delay_factor_correlations.png` — each delay factor's correlation with `final_delay_days`
- `project_duration_distribution.png` — `planned_duration_months`
- `cost_vs_delay.png` — `final_cost_overrun_pct` vs `final_delay_days` scatter
