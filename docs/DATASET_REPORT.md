# Dataset Report

*** All numbers on this page were calculated from the checked-in
`data/synthetic/highway_project_snapshots.csv` (seed `42`, 400 projects) by
running the commands below — none are estimated or invented. Regenerate
with `cd scripts && ../backend/.venv/Scripts/python.exe generate_dataset.py`
and re-run `validate_dataset.py` to reproduce this report's figures exactly. ***

**This is a SYNTHETIC dataset.** See
[docs/SYNTHETIC_DATA_METHODOLOGY.md](SYNTHETIC_DATA_METHODOLOGY.md) for how
it was generated and [data/README.md](../data/README.md) for provenance.
It is not real NHAI/MoRTH project data and must never be presented as such.

## Dimensions

| Metric | Value |
|---|---|
| Rows (snapshots) | 8,740 |
| Columns | 46 |
| Unique projects | 400 |
| Reporting-month range | 2019-02 to 2029-03 |
| Snapshots per project | mean 21.85, median 19, min 10, max 74 |

## Feature groups (46 columns)

- **Project information (14)**: `data_provenance`, `project_id`,
  `project_name`, `highway_number`, `state`, `project_type`, `contractor`,
  `project_length_km`, `original_contract_value_inr_cr`,
  `planned_start_date`, `planned_completion_date`,
  `planned_duration_months`, `reporting_month`, `months_since_start`,
  `project_status`
- **Progress information (9)**: planned/actual/variance for physical and
  financial progress %, plus planned/actual expenditure and its variance
- **Delay risk factors (11)**: 10 delay-day/factor columns +
  `contractor_productivity_factor`
- **Cost information (7)**: planned/actual cost-to-date plus 5 cost
  components (material, labour, equipment, variation, delay-related)
- **Targets (4)**: `final_delay_days`, `significant_delay`,
  `final_cost_overrun_pct`, `cost_overrun`

## Target definitions

- `significant_delay = final_delay_days > 60` (documented MVP threshold
  from the Phase 2 spec).
- `cost_overrun = final_cost_overrun_pct > 10.0` — a materiality threshold
  chosen for this prototype to flag any cost escalation beyond a modest
  margin; not calibrated to a specific official audit rule.

## Target distributions (project level, n=400)

| Target | Value |
|---|---|
| `significant_delay` rate | 49.25% (197/400 projects) |
| `cost_overrun` rate | 38.25% (153/400 projects) |
| `final_delay_days` | mean 65.0, median 59.0, std 91.0, min -153, max 672 |
| `final_cost_overrun_pct` | mean 7.50%, median 6.78%, std 12.02%, min -16.42%, max 44.50% |

Negative `final_delay_days`/`final_cost_overrun_pct` values represent
projects that finished early / under budget — included deliberately so the
targets aren't artificially one-sided.

## Missing-value summary (only columns with any missingness)

| Column | % missing |
|---|---|
| `actual_financial_progress_pct` | 3.78% |
| `financial_progress_variance_pct` | 3.78% |
| `actual_expenditure_inr_cr` | 3.78% |
| `expenditure_variance_pct` | 3.78% |
| `variation_cost_inr_cr` | 3.04% |
| `equipment_unavailability_days` | 2.84% |
| `weather_disruption_days` | 2.76% |
| `contractor` | 0.92% |

All other 38 columns, including every identity and target column, have 0%
missing (enforced by `validate_dataset.py`'s
`check_no_missing_in_identity_and_targets`).

## `project_status` distribution (row level)

| Status | Rows |
|---|---|
| Ongoing | 8,340 |
| Completed | 400 (exactly one final row per project) |

## `project_type` distribution (project level)

| Type | Projects |
|---|---|
| Road Widening (2 to 4 lane) | 108 |
| Road Widening (4 to 6 lane) | 87 |
| Greenfield Highway | 65 |
| Bypass/Ring Road | 65 |
| Bridge/ROB/Flyover | 41 |
| Expressway | 34 |

## `state` distribution (project level)

Ranges from Madhya Pradesh (31 projects) down to Punjab (11 projects)
across all 20 states in the generator's state list; full 20-state
breakdown is reproducible via
`df.groupby('project_id').first()['state'].value_counts()`.

## Delay-risk factor summary (final snapshot per project, cumulative days)

| Factor | Mean | Median | Max |
|---|---|---|---|
| land_acquisition_delay_days | 16.8 | 8.9 | 137.2 |
| utility_shifting_delay_days | 10.2 | 5.4 | 75.1 |
| environment_clearance_delay_days | 5.0 | 0.0 | 125.5 |
| material_delay_days | 12.9 | 8.6 | 96.9 |
| labour_shortage_days | 5.6 | 2.8 | 45.8 |
| equipment_unavailability_days | 3.7 | 1.1 | 32.6 |
| weather_disruption_days | 64.6 | 55.7 | 235.8 |
| traffic_diversion_delay_days | 3.7 | 1.9 | 22.4 |
| design_change_delay_days | 9.5 | 2.9 | 109.7 |
| approval_delay_days | 10.7 | 4.8 | 108.4 |

`weather_disruption_days` runs highest because it accrues every month
(seasonal, not occurrence-gated) across a multi-year project life, unlike
the occurrence-gated categories above it.

## Key project-level summary statistics

| Field | Mean | Median | Min | Max |
|---|---|---|---|---|
| project_length_km | 32.2 | 28.8 | 1.0 | 111.1 |
| planned_duration_months | 19.7 | 17.0 | 12 | 60 |

(`original_contract_value_inr_cr` ranges widely by project type — bridges
are short but expensive per km, expressways are long and expensive per km;
see `scripts/generate_dataset.py`'s `PROJECT_TYPE_PARAMS` for the exact
per-type cost-per-km ranges used.)

## Validation results

Running `scripts/validate_dataset.py` against this file:

```
Summary: 18 passed, 0 warnings, 0 failed
```

All structural (required columns, no duplicate snapshots, ID formats),
range (percentages in [0,100], no negative delay-days/costs), consistency
(variance = actual - planned; cost components sum to total; targets
constant within a project; target columns match their documented
threshold definitions), and the automated leakage-correlation heuristic
(no feature exceeds `|corr| > 0.95` against either continuous target;
strongest observed is `contractor_productivity_factor` at ~0.71 against
`final_cost_overrun_pct`, a real but non-deterministic relationship) pass.

## Limitations

- Synthetic data (see the boxed warning above and
  [SYNTHETIC_DATA_METHODOLOGY.md](SYNTHETIC_DATA_METHODOLOGY.md) section 14
  for exactly what this cannot prove).
- Construction-start delay is out of scope — the simulation assumes actual
  start = planned start.
- State/monsoon risk multipliers are illustrative, not calibrated to real
  per-state project outcomes.
- The cost-overrun tail is narrower than some real audited extreme cases
  (CAG has flagged individual projects above 50% escalation); this
  generator was tuned for a plausible general distribution, not to
  reproduce any specific real extreme case.
- A small number of extreme-tail projects may be truncated at the
  simulation's month cap (`planned_duration_months * 3`, floor 30 months)
  rather than running indefinitely.
