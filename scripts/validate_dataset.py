"""
Validates data/synthetic/highway_project_snapshots.csv (or any dataset with
the same schema) against the structural, range, consistency, and
leakage-heuristic checks described in docs/DATASET_REPORT.md.

This is a data-quality check, not a proof of correctness of the underlying
simulation — see docs/SYNTHETIC_DATA_METHODOLOGY.md for what the synthetic
data can and cannot be used to claim.

Usage (from backend/.venv):
    ../backend/.venv/Scripts/python.exe validate_dataset.py [path/to/dataset.csv]
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

DEFAULT_DATASET_PATH = Path(__file__).resolve().parent.parent / "data" / "synthetic" / "highway_project_snapshots.csv"

PROJECT_ID_PATTERN = re.compile(r"^HRI-\d{4}$")
REPORTING_MONTH_PATTERN = re.compile(r"^\d{4}-\d{2}$")

ID_COLUMNS = ["project_id", "reporting_month"]
TARGET_COLUMNS = ["final_delay_days", "significant_delay", "final_cost_overrun_pct", "cost_overrun"]

REQUIRED_COLUMNS = [
    "data_provenance", "project_id", "project_name", "highway_number", "state",
    "project_type", "contractor", "project_length_km", "original_contract_value_inr_cr",
    "planned_start_date", "planned_completion_date", "planned_duration_months",
    "reporting_month", "months_since_start", "project_status",
    "planned_physical_progress_pct", "actual_physical_progress_pct", "physical_progress_variance_pct",
    "planned_financial_progress_pct", "actual_financial_progress_pct", "financial_progress_variance_pct",
    "planned_expenditure_inr_cr", "actual_expenditure_inr_cr", "expenditure_variance_pct",
    "land_acquisition_delay_days", "utility_shifting_delay_days", "environment_clearance_delay_days",
    "material_delay_days", "labour_shortage_days", "equipment_unavailability_days",
    "weather_disruption_days", "contractor_productivity_factor", "traffic_diversion_delay_days",
    "design_change_delay_days", "approval_delay_days",
    "planned_cost_to_date_inr_cr", "actual_cost_to_date_inr_cr", "material_cost_inr_cr",
    "labour_cost_inr_cr", "equipment_cost_inr_cr", "variation_cost_inr_cr", "delay_related_cost_inr_cr",
] + TARGET_COLUMNS

PERCENT_0_100_COLUMNS = [
    "planned_physical_progress_pct", "actual_physical_progress_pct",
    "planned_financial_progress_pct", "actual_financial_progress_pct",
]
NON_NEGATIVE_COLUMNS = [
    "project_length_km", "land_acquisition_delay_days", "utility_shifting_delay_days",
    "environment_clearance_delay_days", "material_delay_days", "labour_shortage_days",
    "equipment_unavailability_days", "weather_disruption_days", "traffic_diversion_delay_days",
    "design_change_delay_days", "approval_delay_days", "planned_cost_to_date_inr_cr",
    "actual_cost_to_date_inr_cr", "material_cost_inr_cr", "labour_cost_inr_cr",
    "equipment_cost_inr_cr", "variation_cost_inr_cr", "delay_related_cost_inr_cr",
]
COST_COMPONENT_COLUMNS = ["material_cost_inr_cr", "labour_cost_inr_cr", "equipment_cost_inr_cr", "variation_cost_inr_cr", "delay_related_cost_inr_cr"]

SIGNIFICANT_DELAY_THRESHOLD_DAYS = 60
COST_OVERRUN_THRESHOLD_PCT = 10.0
LEAKAGE_CORRELATION_THRESHOLD = 0.95


@dataclass
class CheckResult:
    name: str
    status: str  # PASS, WARN, FAIL
    message: str


def check_file_exists(path: Path) -> CheckResult:
    if path.exists():
        return CheckResult("file_exists", "PASS", f"Found {path}")
    return CheckResult("file_exists", "FAIL", f"Missing dataset file: {path}")


def check_required_columns(df: pd.DataFrame) -> CheckResult:
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        return CheckResult("required_columns", "FAIL", f"Missing columns: {missing}")
    return CheckResult("required_columns", "PASS", f"All {len(REQUIRED_COLUMNS)} required columns present")


def check_no_duplicate_snapshots(df: pd.DataFrame) -> CheckResult:
    dupes = df.duplicated(subset=["project_id", "reporting_month"]).sum()
    if dupes:
        return CheckResult("no_duplicate_snapshots", "FAIL", f"{dupes} duplicate (project_id, reporting_month) rows")
    return CheckResult("no_duplicate_snapshots", "PASS", "No duplicate (project_id, reporting_month) rows")


def check_id_formats(df: pd.DataFrame) -> CheckResult:
    bad_ids = (~df["project_id"].astype(str).str.match(PROJECT_ID_PATTERN)).sum()
    bad_months = (~df["reporting_month"].astype(str).str.match(REPORTING_MONTH_PATTERN)).sum()
    if bad_ids or bad_months:
        return CheckResult("id_formats", "FAIL", f"{bad_ids} malformed project_id, {bad_months} malformed reporting_month")
    return CheckResult("id_formats", "PASS", "project_id and reporting_month formats OK")


def check_no_missing_in_identity_and_targets(df: pd.DataFrame) -> CheckResult:
    critical = ID_COLUMNS + TARGET_COLUMNS + ["actual_physical_progress_pct", "original_contract_value_inr_cr"]
    bad = {c: int(df[c].isna().sum()) for c in critical if df[c].isna().any()}
    if bad:
        return CheckResult("no_missing_in_identity_and_targets", "FAIL", f"Unexpected nulls: {bad}")
    return CheckResult("no_missing_in_identity_and_targets", "PASS", "No nulls in ID/target/core-progress columns")


def check_missing_value_report(df: pd.DataFrame) -> CheckResult:
    pct_missing = (df.isna().mean() * 100).round(2)
    nonzero = pct_missing[pct_missing > 0].sort_values(ascending=False)
    high = nonzero[nonzero > 15.0]
    msg = "; ".join(f"{c}={v}%" for c, v in nonzero.items()) or "no missing values"
    if len(high) > 0:
        return CheckResult("missing_value_report", "WARN", f"Columns with >15% missing: {dict(high)}. Full: {msg}")
    return CheckResult("missing_value_report", "PASS", f"Missing-value rates within expected range. {msg}")


def check_percentage_ranges(df: pd.DataFrame) -> CheckResult:
    problems = {}
    for col in PERCENT_0_100_COLUMNS:
        s = df[col].dropna()
        out_of_range = ((s < 0) | (s > 100)).sum()
        if out_of_range:
            problems[col] = int(out_of_range)
    if problems:
        return CheckResult("percentage_ranges", "FAIL", f"Out-of-[0,100] values: {problems}")
    return CheckResult("percentage_ranges", "PASS", "All progress-pct columns within [0, 100]")


def check_non_negative(df: pd.DataFrame) -> CheckResult:
    problems = {}
    for col in NON_NEGATIVE_COLUMNS:
        s = df[col].dropna()
        negative = (s < 0).sum()
        if negative:
            problems[col] = int(negative)
    if (df["original_contract_value_inr_cr"] <= 0).any():
        problems["original_contract_value_inr_cr"] = int((df["original_contract_value_inr_cr"] <= 0).sum())
    if problems:
        return CheckResult("non_negative", "FAIL", f"Negative/non-positive values found: {problems}")
    return CheckResult("non_negative", "PASS", "No negative values in day-count/cost/length columns")


def check_date_consistency(df: pd.DataFrame) -> CheckResult:
    start = pd.to_datetime(df["planned_start_date"])
    completion = pd.to_datetime(df["planned_completion_date"])
    reporting = pd.to_datetime(df["reporting_month"], format="%Y-%m")
    bad_order = (completion <= start).sum()
    bad_reporting = (reporting < start).sum()
    if bad_order or bad_reporting:
        return CheckResult("date_consistency", "FAIL", f"{bad_order} rows with completion<=start; {bad_reporting} rows reporting before start")
    return CheckResult("date_consistency", "PASS", "planned_completion_date > planned_start_date; reporting_month >= planned_start_date")


def check_progress_variance_consistency(df: pd.DataFrame) -> CheckResult:
    physical = df.dropna(subset=["actual_physical_progress_pct", "planned_physical_progress_pct", "physical_progress_variance_pct"])
    physical_diff = (physical["actual_physical_progress_pct"] - physical["planned_physical_progress_pct"] - physical["physical_progress_variance_pct"]).abs()
    financial = df.dropna(subset=["actual_financial_progress_pct", "planned_financial_progress_pct", "financial_progress_variance_pct"])
    financial_diff = (financial["actual_financial_progress_pct"] - financial["planned_financial_progress_pct"] - financial["financial_progress_variance_pct"]).abs()
    bad_physical = int((physical_diff > 0.05).sum())
    bad_financial = int((financial_diff > 0.05).sum())
    if bad_physical or bad_financial:
        return CheckResult("progress_variance_consistency", "FAIL", f"{bad_physical} physical + {bad_financial} financial variance mismatches (>0.05 tolerance)")
    return CheckResult("progress_variance_consistency", "PASS", "variance_pct == actual - planned for all non-missing rows")


def check_cost_component_sum(df: pd.DataFrame) -> CheckResult:
    subset = df.dropna(subset=COST_COMPONENT_COLUMNS + ["actual_cost_to_date_inr_cr"])
    component_sum = subset[COST_COMPONENT_COLUMNS].sum(axis=1)
    diff = (component_sum - subset["actual_cost_to_date_inr_cr"]).abs()
    tolerance = 0.02 + 0.01 * subset["actual_cost_to_date_inr_cr"].abs()
    bad = int((diff > tolerance).sum())
    if bad:
        return CheckResult("cost_component_sum", "FAIL", f"{bad} rows where cost components don't sum to actual_cost_to_date_inr_cr within tolerance")
    return CheckResult("cost_component_sum", "PASS", "Cost components sum to actual_cost_to_date_inr_cr within tolerance")


def check_target_consistency_within_project(df: pd.DataFrame) -> CheckResult:
    nunique = df.groupby("project_id")[TARGET_COLUMNS].nunique()
    inconsistent = (nunique > 1).any(axis=1).sum()
    if inconsistent:
        return CheckResult("target_consistency_within_project", "FAIL", f"{inconsistent} projects have non-constant target values across their snapshots")
    return CheckResult("target_consistency_within_project", "PASS", "Target columns are constant across all snapshots of each project")


def check_target_definitions(df: pd.DataFrame) -> CheckResult:
    expected_sig = (df["final_delay_days"] > SIGNIFICANT_DELAY_THRESHOLD_DAYS).astype(int)
    expected_overrun = (df["final_cost_overrun_pct"] > COST_OVERRUN_THRESHOLD_PCT).astype(int)
    bad_sig = int((df["significant_delay"] != expected_sig).sum())
    bad_overrun = int((df["cost_overrun"] != expected_overrun).sum())
    if bad_sig or bad_overrun:
        return CheckResult("target_definitions", "FAIL", f"{bad_sig} rows violate significant_delay=final_delay_days>{SIGNIFICANT_DELAY_THRESHOLD_DAYS}; {bad_overrun} rows violate cost_overrun=final_cost_overrun_pct>{COST_OVERRUN_THRESHOLD_PCT}")
    return CheckResult("target_definitions", "PASS", f"significant_delay and cost_overrun match their documented threshold definitions")


def check_target_distribution(df: pd.DataFrame) -> CheckResult:
    proj = df.groupby("project_id")[TARGET_COLUMNS].first()
    sig_rate = proj["significant_delay"].mean()
    overrun_rate = proj["cost_overrun"].mean()
    msg = (
        f"significant_delay rate={sig_rate:.1%}, cost_overrun rate={overrun_rate:.1%}, "
        f"final_delay_days mean={proj['final_delay_days'].mean():.1f}/median={proj['final_delay_days'].median():.1f}, "
        f"final_cost_overrun_pct mean={proj['final_cost_overrun_pct'].mean():.1f}%/median={proj['final_cost_overrun_pct'].median():.1f}%"
    )
    if sig_rate < 0.02 or sig_rate > 0.98 or overrun_rate < 0.02 or overrun_rate > 0.98:
        return CheckResult("target_distribution", "WARN", f"Target classes near-degenerate: {msg}")
    return CheckResult("target_distribution", "PASS", msg)


def check_extreme_values(df: pd.DataFrame) -> CheckResult:
    caps = {
        "project_length_km": 500,
        "original_contract_value_inr_cr": 15000,
        "final_delay_days": 3000,
        "planned_duration_months": 120,
    }
    flagged = {}
    for col, cap in caps.items():
        count = int((df[col].abs() > cap).sum())
        if count:
            flagged[col] = count
    if flagged:
        return CheckResult("extreme_values", "WARN", f"Values beyond domain-reasonable caps: {flagged}")
    return CheckResult("extreme_values", "PASS", "No values beyond domain-reasonable caps")


def check_leakage_correlation(df: pd.DataFrame) -> CheckResult:
    numeric = df.select_dtypes(include=[np.number])
    feature_cols = [c for c in numeric.columns if c not in TARGET_COLUMNS]
    flagged = {}
    for target in ["final_delay_days", "final_cost_overrun_pct"]:
        corr = numeric[feature_cols].corrwith(numeric[target]).abs()
        offenders = corr[corr > LEAKAGE_CORRELATION_THRESHOLD]
        if len(offenders) > 0:
            flagged[target] = dict(offenders.round(3))
    if flagged:
        return CheckResult(
            "leakage_correlation_heuristic", "FAIL",
            f"Feature(s) with |corr| > {LEAKAGE_CORRELATION_THRESHOLD} vs a target (possible leakage/degenerate formula): {flagged}",
        )
    return CheckResult("leakage_correlation_heuristic", "PASS", f"No feature exceeds |corr| > {LEAKAGE_CORRELATION_THRESHOLD} against either continuous target")


def check_provenance_label(df: pd.DataFrame) -> CheckResult:
    values = df["data_provenance"].unique().tolist()
    if values != ["SYNTHETIC"]:
        return CheckResult("provenance_label", "FAIL", f"data_provenance column contains unexpected values: {values}")
    return CheckResult("provenance_label", "PASS", "data_provenance is uniformly labeled SYNTHETIC")


CHECKS = [
    check_required_columns,
    check_no_duplicate_snapshots,
    check_id_formats,
    check_no_missing_in_identity_and_targets,
    check_missing_value_report,
    check_percentage_ranges,
    check_non_negative,
    check_date_consistency,
    check_progress_variance_consistency,
    check_cost_component_sum,
    check_target_consistency_within_project,
    check_target_definitions,
    check_target_distribution,
    check_extreme_values,
    check_leakage_correlation,
    check_provenance_label,
]


def run_validation(path: Path) -> list[CheckResult]:
    file_check = check_file_exists(path)
    if file_check.status == "FAIL":
        return [file_check]

    df = pd.read_csv(path)
    results = [file_check, CheckResult("row_count", "PASS", f"{len(df):,} rows, {df['project_id'].nunique():,} unique projects, {len(df.columns)} columns")]
    for check in CHECKS:
        try:
            results.append(check(df))
        except Exception as exc:  # noqa: BLE001 - surface any check crash as a FAIL, not a silent skip
            results.append(CheckResult(check.__name__, "FAIL", f"Check raised an exception: {exc}"))
    return results


def print_report(results: list[CheckResult]) -> int:
    print(f"{'STATUS':<6} {'CHECK':<38} MESSAGE")
    print("-" * 100)
    counts = {"PASS": 0, "WARN": 0, "FAIL": 0}
    for r in results:
        print(f"{r.status:<6} {r.name:<38} {r.message}")
        counts[r.status] += 1
    print("-" * 100)
    print(f"Summary: {counts['PASS']} passed, {counts['WARN']} warnings, {counts['FAIL']} failed")
    return 1 if counts["FAIL"] > 0 else 0


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DATASET_PATH
    results = run_validation(path)
    exit_code = print_report(results)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
