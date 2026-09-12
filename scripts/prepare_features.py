"""
Phase 3: builds leakage-safe, ML-ready feature datasets from the Phase 2
synthetic snapshot dataset.

Reads data/synthetic/highway_project_snapshots.csv and writes:
    data/processed/delay_features.csv
    data/processed/cost_features.csv

Both files share the same predictor columns; they differ only in which
target column(s) are attached (see docs/FEATURE_ENGINEERING.md for the
full feature dictionary and the leakage-audit reasoning behind every
inclusion/exclusion decision below).

Design principles (see docs/FEATURE_ENGINEERING.md section "Design
principles" for the full write-up):
  - Every engineered feature for a given (project_id, reporting_month) row
    is computed only from that project's own rows at or before that
    reporting_month (verified by test_prepare_features.py). No feature is
    ever computed using a later snapshot or a final-outcome column.
  - The two exact-duplicate raw columns identified during EDA
    (planned_expenditure_inr_cr == planned_cost_to_date_inr_cr,
    expenditure_variance_pct == financial_progress_variance_pct) are
    dropped; the canonical column is kept.
  - The 400 terminal snapshots (project_status == "Completed") are KEPT
    (not silently dropped) but flagged with `is_terminal_snapshot`,
    because on those rows final_delay_days is exactly reconstructible from
    reporting_month - planned_completion_date (verified: max abs diff ==
    0 across all 400 terminal rows). This is not leakage in the temporal
    sense (both inputs are contemporaneous), but training/evaluating on
    these rows makes the prediction task trivial. Phase 4 should filter
    `is_terminal_snapshot == False` for genuine forecasting evaluation.
  - No imputation is performed here (see docs/FEATURE_ENGINEERING.md
    "Missing-value strategy" for the documented per-column plan); missing
    values are passed through as NaN for the modeling phase to handle.

Usage (from backend/.venv):
    ../backend/.venv/Scripts/python.exe prepare_features.py
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT_PATH = REPO_ROOT / "data" / "synthetic" / "highway_project_snapshots.csv"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "processed"

REQUIRED_INPUT_COLUMNS = [
    "project_id", "reporting_month", "project_status", "months_since_start",
    "planned_duration_months", "planned_start_date", "planned_completion_date",
    "state", "project_type", "contractor", "highway_number",
    "project_length_km", "original_contract_value_inr_cr",
    "planned_physical_progress_pct", "actual_physical_progress_pct", "physical_progress_variance_pct",
    "planned_financial_progress_pct", "actual_financial_progress_pct", "financial_progress_variance_pct",
    "planned_expenditure_inr_cr", "actual_expenditure_inr_cr", "expenditure_variance_pct",
    "planned_cost_to_date_inr_cr", "actual_cost_to_date_inr_cr",
    "material_cost_inr_cr", "labour_cost_inr_cr", "equipment_cost_inr_cr",
    "variation_cost_inr_cr", "delay_related_cost_inr_cr",
    "land_acquisition_delay_days", "utility_shifting_delay_days", "environment_clearance_delay_days",
    "material_delay_days", "labour_shortage_days", "equipment_unavailability_days",
    "weather_disruption_days", "traffic_diversion_delay_days", "design_change_delay_days",
    "approval_delay_days", "contractor_productivity_factor",
    "final_delay_days", "significant_delay", "final_cost_overrun_pct", "cost_overrun",
]

DELAY_FACTOR_COLUMNS = [
    "land_acquisition_delay_days", "utility_shifting_delay_days", "environment_clearance_delay_days",
    "material_delay_days", "labour_shortage_days", "equipment_unavailability_days",
    "weather_disruption_days", "traffic_diversion_delay_days", "design_change_delay_days",
    "approval_delay_days",
]

# Exact-duplicate raw columns discovered during EDA (see docs/EDA_REPORT.md
# section "Redundant columns"). Dropped in favor of the canonical name.
DUPLICATE_COLUMNS_DROPPED = ["planned_expenditure_inr_cr", "expenditure_variance_pct"]

IDENTIFIER_COLUMNS = ["project_id", "reporting_month"]

RAW_STATIC_NUMERICAL = [
    "project_length_km", "original_contract_value_inr_cr", "planned_duration_months", "months_since_start",
]
RAW_CATEGORICAL = ["state", "project_type", "contractor"]
RAW_SNAPSHOT_NUMERICAL = [
    "planned_physical_progress_pct", "actual_physical_progress_pct", "physical_progress_variance_pct",
    "planned_financial_progress_pct", "actual_financial_progress_pct", "financial_progress_variance_pct",
    "planned_cost_to_date_inr_cr", "actual_expenditure_inr_cr", "actual_cost_to_date_inr_cr",
    "material_cost_inr_cr", "labour_cost_inr_cr", "equipment_cost_inr_cr",
    "variation_cost_inr_cr", "delay_related_cost_inr_cr",
    "contractor_productivity_factor",
] + DELAY_FACTOR_COLUMNS

ENGINEERED_COLUMNS = [
    "expenditure_gap_inr_cr", "cost_tracking_gap_inr_cr",
    "delay_factor_count", "delay_factor_severity",
    "project_age_ratio", "months_to_planned_completion", "schedule_pressure",
    "progress_efficiency", "cost_growth_rate",
    "recent_progress_trend_3m", "recent_cost_trend_3m",
    "consecutive_underperforming_months", "recent_adverse_events_3m",
]

FLAG_COLUMNS = ["is_terminal_snapshot"]

PREDICTOR_COLUMNS = RAW_STATIC_NUMERICAL + RAW_CATEGORICAL + RAW_SNAPSHOT_NUMERICAL + ENGINEERED_COLUMNS

DELAY_TARGETS = ["final_delay_days", "significant_delay"]
COST_TARGETS = ["final_cost_overrun_pct", "cost_overrun"]

# Ratios explode when planned progress/cost-to-date is near zero in a
# project's first 1-2 months (small denominator). Capped for numerical
# usability; see docs/FEATURE_ENGINEERING.md "progress_efficiency /
# cost_growth_rate" for the exact rationale and affected-row count.
RATIO_CAP = 5.0
RATIO_FLOOR_PCT = 1e-6


def load_input(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"Input dataset not found at {path}. Run scripts/generate_dataset.py first "
            "(see data/README.md)."
        )
    df = pd.read_csv(path)
    missing = [c for c in REQUIRED_INPUT_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Input dataset is missing required columns: {missing}")
    return df.sort_values(["project_id", "reporting_month"]).reset_index(drop=True)


def add_engineered_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df["expenditure_gap_inr_cr"] = df["actual_expenditure_inr_cr"] - df["planned_cost_to_date_inr_cr"]
    df["cost_tracking_gap_inr_cr"] = df["actual_expenditure_inr_cr"] - df["actual_cost_to_date_inr_cr"]

    # These 10 columns are cumulative-to-date counters (monotonic within a
    # project by construction). If any is missing this month, the row's
    # true total is unknown -- summing with the pandas default (skipna=True,
    # missing treated as 0) would make the composite spuriously *decrease*
    # versus the prior month whenever a component goes missing, which is
    # impossible for a cumulative quantity and would be misleading. So the
    # composite is NaN whenever any of its 10 inputs is NaN, rather than a
    # silently-undercounted number.
    delay_cols_present = df[DELAY_FACTOR_COLUMNS]
    any_delay_col_missing = delay_cols_present.isna().any(axis=1)
    df["delay_factor_count"] = (delay_cols_present > 0).sum(axis=1).where(~any_delay_col_missing, np.nan)
    df["delay_factor_severity"] = delay_cols_present.sum(axis=1).where(~any_delay_col_missing, np.nan)

    df["project_age_ratio"] = df["months_since_start"] / df["planned_duration_months"]
    df["months_to_planned_completion"] = df["planned_duration_months"] - df["months_since_start"]

    remaining_months = df["months_to_planned_completion"].clip(lower=1)
    df["schedule_pressure"] = (100.0 - df["actual_physical_progress_pct"]) / remaining_months

    planned_floor = df["planned_physical_progress_pct"].clip(lower=RATIO_FLOOR_PCT)
    df["progress_efficiency"] = (df["actual_physical_progress_pct"] / planned_floor).clip(upper=RATIO_CAP)
    planned_cost_floor = df["planned_cost_to_date_inr_cr"].clip(lower=RATIO_FLOOR_PCT)
    df["cost_growth_rate"] = (df["actual_cost_to_date_inr_cr"] / planned_cost_floor).clip(upper=RATIO_CAP)

    # --- Historical/rolling features: computed per project, sorted by
    # reporting_month, using ONLY the current row and rows strictly before
    # it (shift/rolling never look ahead). ---
    grouped = df.groupby("project_id", sort=False)

    progress_increment = grouped["actual_physical_progress_pct"].diff()
    progress_increment = progress_increment.fillna(df["actual_physical_progress_pct"])
    df["recent_progress_trend_3m"] = (
        progress_increment.groupby(df["project_id"]).transform(lambda s: s.rolling(window=3, min_periods=1).mean())
    )

    cost_increment = grouped["actual_cost_to_date_inr_cr"].diff()
    cost_increment = cost_increment.fillna(df["actual_cost_to_date_inr_cr"])
    df["recent_cost_trend_3m"] = (
        cost_increment.groupby(df["project_id"]).transform(lambda s: s.rolling(window=3, min_periods=1).mean())
    )

    expected_monthly_increment = 100.0 / df["planned_duration_months"]
    underperforming = (progress_increment < expected_monthly_increment).astype(int)
    df["consecutive_underperforming_months"] = (
        underperforming.groupby(df["project_id"]).transform(_consecutive_true_run)
    )

    severity_diff = grouped["delay_factor_severity"].diff()
    severity_diff = severity_diff.fillna(df["delay_factor_severity"])
    adverse_event_this_month = (severity_diff > 0).astype(int)
    df["recent_adverse_events_3m"] = (
        adverse_event_this_month.groupby(df["project_id"]).transform(lambda s: s.rolling(window=3, min_periods=1).sum())
    )

    df["is_terminal_snapshot"] = df["project_status"] == "Completed"

    return df


def _consecutive_true_run(flags: pd.Series) -> pd.Series:
    """Running count of consecutive 1s ending at each position; resets to 0 on a 0."""
    result = np.zeros(len(flags), dtype=int)
    running = 0
    for i, v in enumerate(flags.to_numpy()):
        running = running + 1 if v else 0
        result[i] = running
    return pd.Series(result, index=flags.index)


def build_feature_table(df: pd.DataFrame) -> pd.DataFrame:
    df = df.drop(columns=DUPLICATE_COLUMNS_DROPPED)
    df = add_engineered_features(df)
    keep = IDENTIFIER_COLUMNS + PREDICTOR_COLUMNS + FLAG_COLUMNS + DELAY_TARGETS + COST_TARGETS
    return df[keep]


def write_task_dataset(features: pd.DataFrame, targets: list[str], output_path: Path) -> pd.DataFrame:
    exclude_targets = [t for t in DELAY_TARGETS + COST_TARGETS if t not in targets]
    task_df = features.drop(columns=exclude_targets)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    task_df.to_csv(output_path, index=False)
    return task_df


def prepare(input_path: Path = DEFAULT_INPUT_PATH, output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, pd.DataFrame]:
    raw = load_input(input_path)
    features = build_feature_table(raw)
    delay_df = write_task_dataset(features, DELAY_TARGETS, output_dir / "delay_features.csv")
    cost_df = write_task_dataset(features, COST_TARGETS, output_dir / "cost_features.csv")
    return {"delay_features": delay_df, "cost_features": cost_df, "combined": features}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    print("Preparing Phase 3 ML-ready feature datasets from", args.input)
    result = prepare(args.input, args.output_dir)

    for name, key in [("delay_features.csv", "delay_features"), ("cost_features.csv", "cost_features")]:
        d = result[key]
        print(f"\n{name}: {len(d):,} rows x {len(d.columns)} columns")
        print(f"  unique projects: {d['project_id'].nunique():,}")
        print(f"  is_terminal_snapshot=True rows: {int(d['is_terminal_snapshot'].sum()):,}")

    print(f"\nWrote outputs to {args.output_dir}")


if __name__ == "__main__":
    main()
