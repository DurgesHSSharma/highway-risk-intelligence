"""Phase 14 portfolio-level predicted-risk distributions for the four
Phase 6 prediction tasks. Built entirely from `portfolio_prediction_cache`
(app/analytics/batch_scoring.py) -- never live per-project inference.

Two different, explicitly documented bucketing strategies are used
(section 12 of the Phase 14 brief: "do not invent arbitrary business
meanings for buckets"):

- The two classification tasks already output a genuine [0, 1]
  probability -- bucketed into four FIXED, equal-width 0.25 bands
  (0-25% / 25-50% / 50-75% / 75-100%), a standard probability-banding
  convention, not tuned to this project's data.
- The two regression tasks are unbounded, so their buckets are the
  QUARTILE boundaries (Q1/Q2/Q3) of the values actually observed in the
  CURRENT scored cohort -- the same data-driven boundary style
  app/analytics/risk_score.py already uses for risk levels, with real
  numeric edges reported alongside each bucket rather than an invented
  round-number scale.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import PortfolioPredictionCache

PROBABILITY_BUCKET_EDGES = [0.0, 0.25, 0.5, 0.75, 1.0]
PROBABILITY_BUCKET_LABELS = ["0-25%", "25-50%", "50-75%", "75-100%"]
QUARTILE_BUCKET_LABELS = ["Q1 (lowest)", "Q2", "Q3", "Q4 (highest)"]


@dataclass(frozen=True)
class BucketCount:
    label: str
    lower: float
    upper: float
    count: int


@dataclass(frozen=True)
class TaskDistribution:
    task_key: str
    bucket_strategy: str  # "fixed_probability_bands" | "cohort_quartiles"
    buckets: list[BucketCount]
    raw_values: list[float]


def _bucket_fixed(values: list[float]) -> list[BucketCount]:
    counts = [0] * len(PROBABILITY_BUCKET_LABELS)
    for v in values:
        idx = min(int(v / 0.25), 3) if v < 1.0 else 3
        counts[idx] += 1
    return [
        BucketCount(label=PROBABILITY_BUCKET_LABELS[i], lower=PROBABILITY_BUCKET_EDGES[i], upper=PROBABILITY_BUCKET_EDGES[i + 1], count=counts[i])
        for i in range(4)
    ]


def _bucket_quartile(values: list[float]) -> list[BucketCount]:
    if not values:
        return []
    sorted_vals = sorted(values)
    q1, q2, q3 = statistics.quantiles(sorted_vals, n=4, method="inclusive")
    edges = [sorted_vals[0], q1, q2, q3, sorted_vals[-1]]
    counts = [0, 0, 0, 0]
    for v in values:
        if v <= q1:
            counts[0] += 1
        elif v <= q2:
            counts[1] += 1
        elif v <= q3:
            counts[2] += 1
        else:
            counts[3] += 1
    return [
        BucketCount(label=QUARTILE_BUCKET_LABELS[i], lower=edges[i], upper=edges[i + 1], count=counts[i])
        for i in range(4)
    ]


def portfolio_risk_distribution(db: Session) -> list[TaskDistribution]:
    cache_rows = list(db.execute(select(PortfolioPredictionCache)).scalars().all())
    if not cache_rows:
        return []

    sig_probs = [r.significant_delay_probability for r in cache_rows if r.significant_delay_probability is not None]
    delay_days = [r.final_delay_days_predicted for r in cache_rows]
    cost_probs = [r.cost_overrun_probability for r in cache_rows if r.cost_overrun_probability is not None]
    cost_pct = [r.final_cost_overrun_pct_predicted for r in cache_rows]

    return [
        TaskDistribution("significant_delay", "fixed_probability_bands", _bucket_fixed(sig_probs), sig_probs),
        TaskDistribution("final_delay_days", "cohort_quartiles", _bucket_quartile(delay_days), delay_days),
        TaskDistribution("cost_overrun", "fixed_probability_bands", _bucket_fixed(cost_probs), cost_probs),
        TaskDistribution("final_cost_overrun_pct", "cohort_quartiles", _bucket_quartile(cost_pct), cost_pct),
    ]
