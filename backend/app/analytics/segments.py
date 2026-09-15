"""Phase 14 state / project-type / contractor analytics, historical and
predicted kept structurally separate per segment value (never blended into
one ambiguous field -- see docs/ADVANCED_ANALYTICS.md).

Minimum-sample thresholds were set by INSPECTING the actual corpus
distribution first (see docs/ADVANCED_ANALYTICS.md "Contractor
minimum-sample rule" for the real measured counts), not assumed:

- state / project_type: the brief's default 15-project minimum works fine
  here (18 of 20 states and all 6 project types clear it).
- contractor: 50 contractors manage 400 projects; a flat 15-project
  minimum would leave exactly 1 of 50 contractors usable for comparison,
  which is not a meaningful "contractor analytics" section. 8 was chosen
  instead -- the smallest round threshold that still yields a usable
  comparison set (26 of 50 contractors) while excluding the long tail of
  2-7-project contractors from comparative ranking. Every contractor below
  8, and every state/project_type below 15, is still reported (never
  dropped) with `small_sample=True`.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.risk_score import compute_portfolio_risk_scores
from app.db.models import Project, PortfolioPredictionCache
from app.analytics.historical import terminal_outcome_rows

DIMENSIONS = ("state", "project_type", "contractor")

MIN_SAMPLE_THRESHOLDS: dict[str, int] = {
    "state": 15,
    "project_type": 15,
    "contractor": 8,
}


@dataclass(frozen=True)
class HistoricalSegmentStat:
    project_count: int
    significant_delay_rate: float
    cost_overrun_rate: float
    mean_final_delay_days: float
    mean_final_cost_overrun_pct: float


@dataclass(frozen=True)
class PredictedSegmentStat:
    scored_project_count: int
    avg_significant_delay_probability: float
    avg_cost_overrun_probability: float
    avg_final_delay_days_predicted: float
    avg_final_cost_overrun_pct_predicted: float
    avg_composite_risk_score: float
    risk_level_counts: dict[str, int]


@dataclass(frozen=True)
class SegmentEntry:
    dimension: str
    value: str
    min_sample_threshold: int
    small_sample: bool
    historical: HistoricalSegmentStat | None
    predicted: PredictedSegmentStat | None


def _validate_dimension(dimension: str) -> None:
    if dimension not in DIMENSIONS:
        raise ValueError(f"Unknown segmentation dimension {dimension!r}; expected one of {DIMENSIONS}")


def historical_segment_stats(db: Session, dimension: str) -> dict[str, HistoricalSegmentStat]:
    _validate_dimension(dimension)
    grouped: dict[str, list] = defaultdict(list)
    for row in terminal_outcome_rows(db):
        value = getattr(row, dimension)
        if value is None:
            continue
        grouped[value].append(row)

    out: dict[str, HistoricalSegmentStat] = {}
    for value, rows in grouped.items():
        n = len(rows)
        sig = sum(1 for r in rows if r.significant_delay == 1)
        cost = sum(1 for r in rows if r.cost_overrun == 1)
        out[value] = HistoricalSegmentStat(
            project_count=n,
            significant_delay_rate=sig / n,
            cost_overrun_rate=cost / n,
            mean_final_delay_days=sum(r.final_delay_days for r in rows) / n,
            mean_final_cost_overrun_pct=sum(r.final_cost_overrun_pct for r in rows) / n,
        )
    return out


def predicted_segment_stats(db: Session, dimension: str) -> dict[str, PredictedSegmentStat]:
    _validate_dimension(dimension)
    cache_rows = list(db.execute(select(PortfolioPredictionCache)).scalars().all())
    if not cache_rows:
        return {}

    risk_results, _ = compute_portfolio_risk_scores(cache_rows)
    risk_by_project = {r.project_id: r for r in risk_results}

    dim_column = getattr(Project, dimension)
    dim_map = dict(db.execute(select(Project.project_id, dim_column)).all())

    grouped: dict[str, list] = defaultdict(list)
    for row in cache_rows:
        value = dim_map.get(row.project_id)
        if value is None:
            continue
        grouped[value].append(row)

    out: dict[str, PredictedSegmentStat] = {}
    for value, rows in grouped.items():
        n = len(rows)
        risk_rows = [risk_by_project[r.project_id] for r in rows]
        level_counts: dict[str, int] = defaultdict(int)
        for rr in risk_rows:
            level_counts[rr.risk_level] += 1
        out[value] = PredictedSegmentStat(
            scored_project_count=n,
            avg_significant_delay_probability=sum(r.significant_delay_probability or 0.0 for r in rows) / n,
            avg_cost_overrun_probability=sum(r.cost_overrun_probability or 0.0 for r in rows) / n,
            avg_final_delay_days_predicted=sum(r.final_delay_days_predicted for r in rows) / n,
            avg_final_cost_overrun_pct_predicted=sum(r.final_cost_overrun_pct_predicted for r in rows) / n,
            avg_composite_risk_score=sum(rr.composite_risk_score for rr in risk_rows) / n,
            risk_level_counts=dict(level_counts),
        )
    return out


def segment_report(db: Session, dimension: str) -> list[SegmentEntry]:
    _validate_dimension(dimension)
    threshold = MIN_SAMPLE_THRESHOLDS[dimension]
    historical = historical_segment_stats(db, dimension)
    predicted = predicted_segment_stats(db, dimension)

    def _sort_key(value: str) -> tuple[int, str]:
        count = historical[value].project_count if value in historical else 0
        return (-count, value)

    values = sorted(set(historical) | set(predicted), key=_sort_key)

    entries: list[SegmentEntry] = []
    for value in values:
        hist = historical.get(value)
        pred = predicted.get(value)
        reference_count = hist.project_count if hist is not None else (pred.scored_project_count if pred else 0)
        entries.append(
            SegmentEntry(
                dimension=dimension,
                value=value,
                min_sample_threshold=threshold,
                small_sample=reference_count < threshold,
                historical=hist,
                predicted=pred,
            )
        )
    return entries
