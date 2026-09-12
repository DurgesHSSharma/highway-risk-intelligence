import pandas as pd
import pytest

from scripts.generate_dataset import (
    COST_OVERRUN_THRESHOLD_PCT,
    OUTPUT_PATH,
    SIGNIFICANT_DELAY_THRESHOLD_DAYS,
    generate_dataset,
)
from scripts.validate_dataset import TARGET_COLUMNS, check_leakage_correlation

# Small n_projects for fast unit tests; separate tests below check the
# full checked-in dataset meets the 300-500 project / "several thousand
# rows" target from the Phase 2 spec.
SMALL_N = 25


@pytest.fixture(scope="module")
def small_df() -> pd.DataFrame:
    return generate_dataset(n_projects=SMALL_N, seed=123)


def test_nonempty(small_df: pd.DataFrame) -> None:
    assert len(small_df) > 0


def test_expected_columns_present(small_df: pd.DataFrame) -> None:
    expected = {
        "data_provenance", "project_id", "reporting_month", "project_status",
        "planned_physical_progress_pct", "actual_physical_progress_pct",
        "land_acquisition_delay_days", "contractor_productivity_factor",
        "actual_cost_to_date_inr_cr", *TARGET_COLUMNS,
    }
    assert expected.issubset(small_df.columns)


def test_multiple_snapshots_per_project(small_df: pd.DataFrame) -> None:
    counts = small_df.groupby("project_id").size()
    assert len(counts) == SMALL_N
    assert (counts > 1).all()


def test_project_and_snapshot_uniqueness(small_df: pd.DataFrame) -> None:
    assert not small_df.duplicated(subset=["project_id", "reporting_month"]).any()


def test_target_generation_and_ranges(small_df: pd.DataFrame) -> None:
    assert small_df["significant_delay"].isin([0, 1]).all()
    assert small_df["cost_overrun"].isin([0, 1]).all()
    assert small_df["final_delay_days"].notna().all()
    assert small_df["final_cost_overrun_pct"].notna().all()


def test_target_definitions_hold(small_df: pd.DataFrame) -> None:
    expected_sig = (small_df["final_delay_days"] > SIGNIFICANT_DELAY_THRESHOLD_DAYS).astype(int)
    expected_overrun = (small_df["final_cost_overrun_pct"] > COST_OVERRUN_THRESHOLD_PCT).astype(int)
    assert (small_df["significant_delay"] == expected_sig).all()
    assert (small_df["cost_overrun"] == expected_overrun).all()


def test_targets_constant_within_each_project(small_df: pd.DataFrame) -> None:
    nunique = small_df.groupby("project_id")[TARGET_COLUMNS].nunique()
    assert (nunique == 1).all().all()


def test_progress_percentages_within_bounds(small_df: pd.DataFrame) -> None:
    for col in ["planned_physical_progress_pct", "actual_physical_progress_pct"]:
        assert small_df[col].between(0, 100).all()


def test_no_missing_values_in_ids_and_targets(small_df: pd.DataFrame) -> None:
    for col in ["project_id", "reporting_month", *TARGET_COLUMNS]:
        assert small_df[col].notna().all()


def test_reproducibility_with_fixed_seed() -> None:
    df_a = generate_dataset(n_projects=10, seed=7)
    df_b = generate_dataset(n_projects=10, seed=7)
    pd.testing.assert_frame_equal(df_a, df_b)


def test_different_seeds_produce_different_data() -> None:
    df_a = generate_dataset(n_projects=10, seed=1)
    df_b = generate_dataset(n_projects=10, seed=2)
    assert not df_a["actual_physical_progress_pct"].equals(df_b["actual_physical_progress_pct"])


def test_no_obvious_leakage_correlation(small_df: pd.DataFrame) -> None:
    result = check_leakage_correlation(small_df)
    assert result.status != "FAIL", result.message


def test_data_provenance_labeled_synthetic(small_df: pd.DataFrame) -> None:
    assert (small_df["data_provenance"] == "SYNTHETIC").all()


def test_checked_in_dataset_scale() -> None:
    """The committed dataset (not the fast small_df fixture) should match the
    Phase 2 spec's ~300-500 project / several-thousand-row target."""
    if not OUTPUT_PATH.exists():
        pytest.skip(f"{OUTPUT_PATH} not generated yet")
    df = pd.read_csv(OUTPUT_PATH)
    n_projects = df["project_id"].nunique()
    assert 300 <= n_projects <= 500
    assert len(df) >= 2000
