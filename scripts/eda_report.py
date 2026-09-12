"""
Phase 3 EDA: computes the statistics reported in docs/EDA_REPORT.md and
saves a small set of practical plots to docs/artifacts/.

This is a reporting script, not a data-modification script. It reads
data/synthetic/highway_project_snapshots.csv (Phase 2 output) and only
produces read-only artifacts (printed report + PNG plots). Re-running it
reproduces the same numbers because the underlying dataset is fixed.

Usage (from backend/.venv):
    ../backend/.venv/Scripts/python.exe eda_report.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

DATASET_PATH = Path(__file__).resolve().parent.parent / "data" / "synthetic" / "highway_project_snapshots.csv"
ARTIFACTS_DIR = Path(__file__).resolve().parent.parent / "docs" / "artifacts"

DELAY_FACTOR_COLUMNS = [
    "land_acquisition_delay_days", "utility_shifting_delay_days", "environment_clearance_delay_days",
    "material_delay_days", "labour_shortage_days", "equipment_unavailability_days",
    "weather_disruption_days", "traffic_diversion_delay_days", "design_change_delay_days",
    "approval_delay_days",
]


def load() -> pd.DataFrame:
    df = pd.read_csv(DATASET_PATH)
    return df.sort_values(["project_id", "reporting_month"]).reset_index(drop=True)


def print_section(title: str) -> None:
    print("\n" + "=" * 100)
    print(title)
    print("=" * 100)


def report_structure(df: pd.DataFrame) -> None:
    print_section("1. DATASET STRUCTURE")
    print(f"rows={len(df):,} columns={len(df.columns)} unique_projects={df['project_id'].nunique():,}")
    snaps = df.groupby("project_id").size()
    print(f"snapshots/project: mean={snaps.mean():.2f} median={snaps.median():.1f} min={snaps.min()} max={snaps.max()}")
    print(f"reporting_month range: {df['reporting_month'].min()} .. {df['reporting_month'].max()}")


def report_missing(df: pd.DataFrame) -> None:
    print_section("2. MISSING VALUES")
    pct = (df.isna().mean() * 100).round(3)
    nonzero = pct[pct > 0].sort_values(ascending=False)
    for col, val in nonzero.items():
        print(f"  {col:<38} {val:.3f}%")
    if nonzero.empty:
        print("  (no missing values)")


def report_duplicates_and_invalid(df: pd.DataFrame) -> None:
    print_section("3. DUPLICATES AND INVALID VALUES")
    print("full duplicate rows:", df.duplicated().sum())
    print("dup (project_id, reporting_month):", df.duplicated(subset=["project_id", "reporting_month"]).sum())
    print("actual_physical_progress_pct out of [0,100]:", ((df["actual_physical_progress_pct"] < 0) | (df["actual_physical_progress_pct"] > 100)).sum())
    neg_cols = DELAY_FACTOR_COLUMNS + ["material_cost_inr_cr", "labour_cost_inr_cr", "equipment_cost_inr_cr", "variation_cost_inr_cr", "delay_related_cost_inr_cr", "actual_cost_to_date_inr_cr"]
    negatives = {c: int((df[c] < 0).sum()) for c in neg_cols if (df[c] < 0).sum() > 0}
    print("negative values in day-count/cost columns:", negatives or "none")
    bad_dates = (pd.to_datetime(df["planned_completion_date"]) <= pd.to_datetime(df["planned_start_date"])).sum()
    print("planned_completion_date <= planned_start_date:", bad_dates)


def report_targets(df: pd.DataFrame) -> pd.DataFrame:
    print_section("4. TARGET ANALYSIS (project level)")
    proj = df.groupby("project_id").first()
    print("significant_delay:", proj["significant_delay"].value_counts().to_dict(), f"rate={proj['significant_delay'].mean():.2%}")
    print("cost_overrun:", proj["cost_overrun"].value_counts().to_dict(), f"rate={proj['cost_overrun'].mean():.2%}")
    print("final_delay_days describe:\n", proj["final_delay_days"].describe(percentiles=[.05, .25, .5, .75, .95]))
    print("final_cost_overrun_pct describe:\n", proj["final_cost_overrun_pct"].describe(percentiles=[.05, .25, .5, .75, .95]))
    print("negative final_delay_days (early finish):", (proj["final_delay_days"] < 0).sum(), f"of {len(proj)}")
    print("negative final_cost_overrun_pct (under budget):", (proj["final_cost_overrun_pct"] < 0).sum(), f"of {len(proj)}")
    print("corr(final_delay_days, final_cost_overrun_pct):", round(proj["final_delay_days"].corr(proj["final_cost_overrun_pct"]), 3))
    return proj


def report_terminal_row_leakage_check(df: pd.DataFrame) -> None:
    print_section("5. TERMINAL-SNAPSHOT (project_status=='Completed') CHECK")
    last = df[df["project_status"] == "Completed"].copy()
    print("Completed rows:", len(last), "of", len(df))
    derived = (pd.to_datetime(last["reporting_month"], format="%Y-%m") - pd.to_datetime(last["planned_completion_date"])).dt.days
    max_diff = (derived - last["final_delay_days"]).abs().max()
    print("max |derived_delay - final_delay_days| on Completed rows:", max_diff)


def report_realism(df: pd.DataFrame) -> None:
    print_section("6. REALISM CHECKS (correlations with final snapshot, project level)")
    final = df[df["project_status"] == "Completed"].set_index("project_id")
    for col in DELAY_FACTOR_COLUMNS + ["contractor_productivity_factor"]:
        print(f"  corr({col}, final_delay_days) = {final[col].corr(final['final_delay_days']):.3f}")
    print(f"  corr(contractor_productivity_factor, final_cost_overrun_pct) = {final['contractor_productivity_factor'].corr(final['final_cost_overrun_pct']):.3f}")

    print("\nproject_type vs targets (mean):")
    print(df.groupby("project_id").first().groupby("project_type")[[]].size())
    proj = df.groupby("project_id").first()
    final_join = final[["final_delay_days", "final_cost_overrun_pct"]]
    grouped = proj[["project_type"]].join(final_join).groupby("project_type").mean(numeric_only=True)
    print(grouped)


def make_plots(df: pd.DataFrame, proj: pd.DataFrame) -> None:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"figure.dpi": 100})

    # 1. Target distributions
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    axes[0].hist(proj["final_delay_days"], bins=30, color="#3b6fa0")
    axes[0].axvline(0, color="black", linewidth=1, linestyle="--")
    axes[0].set_title("final_delay_days (project level, n=400)")
    axes[0].set_xlabel("days")
    axes[1].hist(proj["final_cost_overrun_pct"], bins=30, color="#a05a3b")
    axes[1].axvline(0, color="black", linewidth=1, linestyle="--")
    axes[1].set_title("final_cost_overrun_pct (project level, n=400)")
    axes[1].set_xlabel("percent")
    fig.tight_layout()
    fig.savefig(ARTIFACTS_DIR / "target_distributions.png")
    plt.close(fig)

    # 2. Missingness
    pct = (df.isna().mean() * 100)
    nonzero = pct[pct > 0].sort_values()
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.barh(nonzero.index, nonzero.values, color="#6a8caf")
    ax.set_xlabel("% missing")
    ax.set_title("Missing values by column")
    fig.tight_layout()
    fig.savefig(ARTIFACTS_DIR / "missingness.png")
    plt.close(fig)

    # 3. Progress gap distribution (physical_progress_variance_pct, ongoing rows)
    ongoing = df[df["project_status"] == "Ongoing"]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.hist(ongoing["physical_progress_variance_pct"], bins=40, color="#4a9078")
    ax.axvline(0, color="black", linewidth=1, linestyle="--")
    ax.set_title("Progress gap (actual - planned physical progress %), ongoing snapshots")
    ax.set_xlabel("percentage points")
    fig.tight_layout()
    fig.savefig(ARTIFACTS_DIR / "progress_gap_distribution.png")
    plt.close(fig)

    # 4. Delay-factor correlations with final_delay_days
    final = df[df["project_status"] == "Completed"].set_index("project_id")
    corrs = pd.Series({c: final[c].corr(final["final_delay_days"]) for c in DELAY_FACTOR_COLUMNS}).sort_values()
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.barh(corrs.index, corrs.values, color="#a0763b")
    ax.set_title("Delay-factor correlation with final_delay_days (final snapshot)")
    ax.set_xlabel("Pearson r")
    fig.tight_layout()
    fig.savefig(ARTIFACTS_DIR / "delay_factor_correlations.png")
    plt.close(fig)

    # 5. Project duration distribution
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.hist(proj["planned_duration_months"], bins=20, color="#7a5ba0")
    ax.set_title("planned_duration_months distribution (project level)")
    ax.set_xlabel("months")
    fig.tight_layout()
    fig.savefig(ARTIFACTS_DIR / "project_duration_distribution.png")
    plt.close(fig)

    # 6. Cost overrun vs delay relationship
    fig, ax = plt.subplots(figsize=(6, 5))
    ax.scatter(proj["final_delay_days"], proj["final_cost_overrun_pct"], s=14, alpha=0.6, color="#3b6fa0")
    ax.axhline(0, color="grey", linewidth=0.8)
    ax.axvline(0, color="grey", linewidth=0.8)
    ax.set_xlabel("final_delay_days")
    ax.set_ylabel("final_cost_overrun_pct")
    ax.set_title(f"Cost overrun vs delay (r={proj['final_delay_days'].corr(proj['final_cost_overrun_pct']):.2f})")
    fig.tight_layout()
    fig.savefig(ARTIFACTS_DIR / "cost_vs_delay.png")
    plt.close(fig)

    print_section("7. PLOTS SAVED")
    for p in sorted(ARTIFACTS_DIR.glob("*.png")):
        print(" ", p)


def main() -> None:
    df = load()
    report_structure(df)
    report_missing(df)
    report_duplicates_and_invalid(df)
    proj = report_targets(df)
    report_terminal_row_leakage_check(df)
    report_realism(df)
    make_plots(df, proj)


if __name__ == "__main__":
    main()
