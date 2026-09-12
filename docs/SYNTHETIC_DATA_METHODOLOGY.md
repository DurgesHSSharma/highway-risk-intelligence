# Synthetic Data Methodology

Generator: [`scripts/generate_dataset.py`](../scripts/generate_dataset.py).
Output: `data/synthetic/highway_project_snapshots.csv`, labeled
`data_provenance=SYNTHETIC` on every row. This document explains how and
why, and — as important — what the result cannot be used to claim.

## 1. Why synthetic data is required

This project needs a monthly, project-level, labelled time series (features
knowable at each reporting month + an eventual outcome) to build and
demonstrate supervised ML models in Phase 3. No dataset of that shape,
covering hundreds of projects with a rich, consistent monthly schema, is
publicly available for NHAI/MoRTH highway projects.

## 2. Why public project-level monthly ML data is insufficient here

Real public sources — data.gov.in NH project lists, CAG audit reports,
parliamentary Standing Committee reports, NHAI/MoRTH annual reports, PIB
releases (see [data/documents/metadata.csv](../data/documents/metadata.csv))
— report real, useful facts, but as **aggregate statistics or point-in-time
snapshots** (e.g. "697 projects were delayed as of July 2024", "35% of
delays are attributed to land acquisition"), not as a per-project monthly
panel with a consistent feature schema across hundreds of projects. They
are a legitimate corpus for future RAG-based document Q&A and for sanity-
checking the *shape* of a synthetic distribution — not a supervised-ML
training table on their own.

## 3. How projects are generated

`sample_project_static()` draws, once per project, before any monthly
simulation: a `project_type` (weighted category), a length (gamma
distribution, type-specific mean/shape), a cost-per-km (type-specific
uniform range) combined into `original_contract_value_inr_cr`, a state
(uniform over 20 Indian states), a contractor (drawn from a fixed pool of
50 synthetic — not real — companies, each with its own fixed `quality`
trait so the same contractor's projects share a correlated performance
tendency, the way real repeat contractors would), and three **latent risk
traits** that are never written to the output but drive the monthly
simulation: `risk_propensity` (Beta(2,5) — general land/utility/clearance
friction), `supply_chain_risk` (Uniform(0.5,1.5)), and `design_maturity`
(Beta(3,3) — how settled the design is at the start).

## 4. How project duration is generated

`planned_duration_months = round(length_km / pace) + random(3..6)`, where
`pace` is a type-specific km/month rate jittered ±20%, clipped to
[12, 60] months. `planned_start_date` is randomized across a ~5.5 year
window (2019-01 to 2024-06) so reporting months span a realistic multi-year
range. This is purely a planning-stage calculation — it does not depend on
any simulated outcome.

## 5. How progress is generated

**Planned** physical/financial progress is a smoothstep S-curve
(`_planned_progress_pct`) that is a pure function of the (already-fixed)
planned schedule — slow start, fast middle, slow finish — independent of
whatever actually happens.

**Actual** progress is built forward, month by month, inside
`simulate_project()`: each month, a `contractor_productivity_factor` is
updated as an AR(1) process anchored to the contractor's `quality` trait,
then dampened by that month's new friction (delay-days added that month).
The month's progress increment is
`(100/planned_duration_months) * productivity_effective + noise`,
accumulated into `actual_physical_progress_pct` (clipped to [0,100]).
Financial progress tracks physical progress with its own slowly-drifting
ratio (billing sometimes leads, sometimes lags execution), not a fixed
multiple of it.

## 6. How delay factors are generated

Each of the 8 delay-day categories (land acquisition, utility shifting,
environment clearance, material, labour, equipment, weather, traffic,
design change, approval — 10 total, 8 "friction" categories plus design/
approval) is a **cumulative-to-date counter**. Each month, a category may
add a new increment: a Bernoulli "did an issue occur this month" draw
(probability driven by `risk_propensity`, the state's risk multiplier,
contractor quality, or project phase, depending on category) followed by
an Exponential-distributed magnitude if it did. Land/utility/environment
issues are front-loaded (more likely early in the project); design/approval
issues taper as `design_maturity` implies more settled designs over time;
weather delay is seasonal (`_monsoon_factor` multiplies exposure ~3-4x
during June-September, further scaled by a state-level monsoon-intensity
factor for higher-rainfall states); traffic diversion delay only applies
meaningfully to widening/bypass project types during active mid-project
construction. None of this is a simple `if delay > X then …` rule — every
occurrence and magnitude is a random draw shaped by continuous latent
traits, so two projects with similar traits still diverge.

## 7. How cost variables are generated

Each month's cost increment splits into: a **core execution cost**
(`contract_value * this month's progress% / 100`, adjusted by a
contractor-quality-linked cost-efficiency factor) divided across
material/labour/equipment with randomized shares (~55/25/20%, jittered);
a **variation cost** increment proportional to that month's new design/
approval-change days; and a **delay-related cost** increment proportional
to that month's total new friction-days and project size. All five cost
components are accumulated cumulatively and, by construction, sum to
`actual_cost_to_date_inr_cr` (checked in `validate_dataset.py`).

## 8. How final delay is generated

The simulation loop runs until `actual_physical_progress_pct` reaches 100%
(or a generous cap of `max(planned_duration_months * 3, 30)` months is hit,
to bound run time for extreme-tail draws). `final_delay_days` is simply the
**calendar-day difference** between the completion month reached by the
simulation and `planned_completion_date` — it falls out of the trajectory,
it is not chosen in advance and back-fitted.

## 9. How cost overrun is generated

`final_cost_overrun_pct = (final actual_cost_to_date_inr_cr - original_contract_value_inr_cr) / original_contract_value_inr_cr * 100`,
read off the same completed trajectory — again an output of the
simulation, not an input to it.

## 10. How noise/variation is introduced

Every stochastic element (Bernoulli occurrence draws, Exponential
magnitudes, AR(1) productivity/financial-ratio noise, cost-share jitter,
per-project Beta/Gamma/Uniform latent traits) uses `numpy`'s
`default_rng(seed)`. Nothing is deterministic given the traits; two
projects with identical `project_type`/`state`/`contractor` still diverge
because the per-month draws differ.

## 11. How missing values are introduced

Independent Bernoulli-per-row missingness is applied *after* generation, on
a fixed list of "softer" fields only, simulating monthly MIS reporting gaps:
`actual_financial_progress_pct` (and the three fields derived from it:
`financial_progress_variance_pct`, `actual_expenditure_inr_cr`,
`expenditure_variance_pct` — nulled together, ~4% of rows) `contractor`
(~1%), `equipment_unavailability_days` (~3%), `weather_disruption_days`
(~3%), and `variation_cost_inr_cr` (~3%). Identity columns (`project_id`,
`reporting_month`), the core `actual_physical_progress_pct` feature, and
all four target columns are never nulled.

## 12. How leakage is prevented

This is the most important property of the generator, and it is structural,
not a post-hoc filter: **the simulation only ever moves forward in time**.
A given month's feature values are a function of (a) latent traits fixed
before the simulation starts, and (b) random draws for that month and
earlier months. `final_delay_days` and `final_cost_overrun_pct` are read
off the trajectory only *after* the loop finishes — no feature is
constructed by working backward from a pre-chosen final outcome. Concretely:
delay-day and cost columns are running cumulative totals *as of that
row's reporting month*, never totals that include future months; planned-
schedule columns are pure functions of the planned dates, never of what
actually happened. `scripts/validate_dataset.py`'s
`check_leakage_correlation` additionally checks, as an automated guard, that
no single numeric feature exceeds `|correlation| > 0.95` with either
continuous target — on the current dataset the strongest such feature
(`contractor_productivity_factor`) sits at ~0.7-0.71 (see
[docs/DATASET_REPORT.md](DATASET_REPORT.md)), i.e. a real, causal, but far
from deterministic relationship.

## 13. What assumptions are made

- Construction is assumed to start exactly on `planned_start_date`
  (start-of-construction delay itself is out of scope for this MVP).
- State-level risk/monsoon multipliers
  (`STATE_RISK_MULTIPLIER`, `STATE_MONSOON_MULTIPLIER` in
  `generate_dataset.py`) are **illustrative**, loosely informed by the
  general direction of publicly reported aggregate patterns (e.g. land
  acquisition and monsoon exposure vary by region) — they are **not**
  calibrated to real per-state project data, and the code comments say so.
- Contractor names, and every cost/delay number, are entirely fictional.
- A small number of extreme-tail projects may be truncated at the
  simulation's month cap rather than running indefinitely; this is a
  documented approximation, not a hidden one.

## 14. What synthetic data cannot prove

This dataset cannot demonstrate that a model trained on it will work on
real NHAI/MoRTH projects, cannot be used to assert any real-world delay or
cost-overrun statistic, and cannot substitute for real project records in
any decision-making context. Any accuracy/F1/SHAP result produced from it
in Phase 3+ describes performance on **this synthetic simulation only**.
The tail of `final_cost_overrun_pct` in the generated data (max ~44.5%,
project-level) is narrower than some real audited extreme cases reported by
CAG (which have flagged individual projects with escalation above 50%) —
the generator was tuned for a plausible general distribution, not to
reproduce any specific extreme case.

## 15. How this should — and should not — be presented in a resume/demo

**Should**: "A prototype decision-support system inspired by highway
infrastructure project monitoring, trained on a synthetic dataset whose
generation methodology (including explicit leakage prevention) is
documented and tested." Emphasize the engineering (leakage-safe temporal
simulation, validation pipeline, honest provenance labeling) as the
demonstrable skill.

**Should not**: Never say the model "predicts real highway delays" or cite
any accuracy number as if it reflects real-world performance. Never drop
the "synthetic" qualifier when describing the dataset, even informally.
