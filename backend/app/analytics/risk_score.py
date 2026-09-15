"""Phase 14 composite decision-support risk score.

NOT a new ML model -- a deterministic, transparent aggregation of the four
existing Phase 6 model outputs already sitting in
`portfolio_prediction_cache` (see app/analytics/batch_scoring.py). Never
trained, tuned, or fit to any target; purely arithmetic.

Design (see docs/ADVANCED_ANALYTICS.md "Risk score formula" for the full
rationale, incl. real measured quartile boundaries from an actual run):

1. The two classification tasks (`significant_delay`, `cost_overrun`)
   already output genuine [0, 1] probabilities -- used AS-IS, never
   rescaled (rescaling a probability would distort its meaning).
2. The two regression tasks (`final_delay_days`, `final_cost_overrun_pct`)
   are unbounded, so each is min-max normalized to [0, 1] against the
   CURRENT scored cohort's own observed min/max (real measured range,
   inspected before this module was written -- see the module docstring in
   app/analytics/batch_scoring.py and docs/ADVANCED_ANALYTICS.md). This
   normalization is batch-relative by construction: a project's normalized
   delay/cost-risk component depends on the min/max of the cohort it was
   scored alongside. Disclosed as a limitation, not hidden.
3. `delay_risk` = mean(significant_delay_probability, normalized final_delay_days)
   `cost_risk`  = mean(cost_overrun_probability, normalized final_cost_overrun_pct)
   `composite_risk_score` (0-100) = 100 * mean(delay_risk, cost_risk)
   i.e. an EQUAL-weighted average of all four model outputs. Equal
   weighting was chosen because no external cost-of-error/business-priority
   data exists in this project to justify differential weights -- this is
   a decision-support heuristic, not a statistically validated risk model,
   and is never described as a "probability of project failure".
4. Risk levels (LOW/MEDIUM/HIGH/CRITICAL) are assigned by QUARTILE of the
   composite_risk_score distribution actually observed in the current
   cohort (Q1/Q2/Q3 split into four equal-population bands) -- not
   arbitrary fixed cutoffs, and not claimed to be official NHAI thresholds.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Literal

RiskLevel = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]


@dataclass(frozen=True)
class NormalizationRange:
    task_key: str
    observed_min: float
    observed_max: float

    def normalize(self, value: float) -> float:
        span = self.observed_max - self.observed_min
        if span == 0:
            return 0.5
        return (value - self.observed_min) / span


@dataclass(frozen=True)
class RiskScoreResult:
    project_id: str
    delay_risk: float  # 0-1
    cost_risk: float  # 0-1
    composite_risk_score: float  # 0-100
    risk_level: RiskLevel


@dataclass(frozen=True)
class RiskScoreCohortMetadata:
    cohort_size: int
    final_delay_days_range: NormalizationRange
    final_cost_overrun_pct_range: NormalizationRange
    level_thresholds: dict[str, float]  # {"q1": ..., "q2": ..., "q3": ...} composite_risk_score cut points


def _quartile_cutpoints(scores: list[float]) -> tuple[float, float, float]:
    """`statistics.quantiles` requires >=2 data points. A cohort this small
    only arises in degenerate/test scenarios -- the real dataset always has
    hundreds of eligible projects -- but must not crash: with fewer than 2
    scores, every cut point collapses to the single available value, which
    deterministically assigns LOW to every row (score <= q1 always) rather
    than raising."""
    if len(scores) < 2:
        v = scores[0] if scores else 0.0
        return v, v, v
    q1, q2, q3 = statistics.quantiles(scores, n=4, method="inclusive")
    return q1, q2, q3


def _assign_level(score: float, q1: float, q2: float, q3: float) -> RiskLevel:
    if score <= q1:
        return "LOW"
    if score <= q2:
        return "MEDIUM"
    if score <= q3:
        return "HIGH"
    return "CRITICAL"


def compute_portfolio_risk_scores(
    cache_rows: list,
) -> tuple[list[RiskScoreResult], RiskScoreCohortMetadata | None]:
    """`cache_rows` are `PortfolioPredictionCache` ORM rows (or any object
    with the same attribute names). Returns (per-project results, cohort
    metadata) -- metadata is None only when `cache_rows` is empty."""
    if not cache_rows:
        return [], None

    delay_days_values = [r.final_delay_days_predicted for r in cache_rows]
    cost_pct_values = [r.final_cost_overrun_pct_predicted for r in cache_rows]

    delay_days_range = NormalizationRange("final_delay_days", min(delay_days_values), max(delay_days_values))
    cost_pct_range = NormalizationRange("final_cost_overrun_pct", min(cost_pct_values), max(cost_pct_values))

    provisional: list[tuple[str, float, float, float]] = []
    for r in cache_rows:
        norm_delay_days = delay_days_range.normalize(r.final_delay_days_predicted)
        norm_cost_pct = cost_pct_range.normalize(r.final_cost_overrun_pct_predicted)
        sig_prob = r.significant_delay_probability if r.significant_delay_probability is not None else float(
            r.significant_delay_predicted_class
        )
        cost_prob = r.cost_overrun_probability if r.cost_overrun_probability is not None else float(
            r.cost_overrun_predicted_class
        )
        delay_risk = (sig_prob + norm_delay_days) / 2.0
        cost_risk = (cost_prob + norm_cost_pct) / 2.0
        composite = 100.0 * (delay_risk + cost_risk) / 2.0
        provisional.append((r.project_id, delay_risk, cost_risk, composite))

    scores = sorted(p[3] for p in provisional)
    q1, q2, q3 = _quartile_cutpoints(scores)

    results = [
        RiskScoreResult(
            project_id=project_id,
            delay_risk=delay_risk,
            cost_risk=cost_risk,
            composite_risk_score=composite,
            risk_level=_assign_level(composite, q1, q2, q3),
        )
        for project_id, delay_risk, cost_risk, composite in provisional
    ]

    metadata = RiskScoreCohortMetadata(
        cohort_size=len(cache_rows),
        final_delay_days_range=delay_days_range,
        final_cost_overrun_pct_range=cost_pct_range,
        level_thresholds={"q1": q1, "q2": q2, "q3": q3},
    )
    return results, metadata
