from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts.generate_dataset import generate_dataset
from scripts.prepare_features import (
    COST_TARGETS,
    DELAY_TARGETS,
    DUPLICATE_COLUMNS_DROPPED,
    RATIO_CAP,
    REQUIRED_INPUT_COLUMNS,
    build_feature_table,
    load_input,
    prepare,
)

SMALL_N = 15


@pytest.fixture(scope="module")
def raw_df() -> pd.DataFrame:
    return generate_dataset(n_projects=SMALL_N, seed=321)


@pytest.fixture(scope="module")
def features(raw_df: pd.DataFrame) -> pd.DataFrame:
    return build_feature_table(raw_df)


def test_load_input_raises_clearly_on_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_input(tmp_path / "does_not_exist.csv")


def test_load_input_raises_clearly_on_missing_required_column(tmp_path: Path, raw_df: pd.DataFrame) -> None:
    broken = raw_df.drop(columns=["actual_physical_progress_pct"])
    path = tmp_path / "broken.csv"
    broken.to_csv(path, index=False)
    with pytest.raises(ValueError, match="actual_physical_progress_pct"):
        load_input(path)


def test_all_required_columns_declared_present_in_generator_output(raw_df: pd.DataFrame) -> None:
    missing = [c for c in REQUIRED_INPUT_COLUMNS if c not in raw_df.columns]
    assert not missing


def test_prepare_writes_both_output_files(tmp_path: Path, raw_df: pd.DataFrame) -> None:
    input_path = tmp_path / "raw.csv"
    raw_df.to_csv(input_path, index=False)
    output_dir = tmp_path / "processed"
    prepare(input_path=input_path, output_dir=output_dir)
    assert (output_dir / "delay_features.csv").exists()
    assert (output_dir / "cost_features.csv").exists()


def test_project_id_and_reporting_month_preserved(raw_df: pd.DataFrame, features: pd.DataFrame) -> None:
    assert set(features["project_id"]) == set(raw_df["project_id"])
    assert len(features) == len(raw_df)
    assert set(features["reporting_month"]) == set(raw_df["reporting_month"])


def test_no_duplicate_project_reporting_month(features: pd.DataFrame) -> None:
    assert not features.duplicated(subset=["project_id", "reporting_month"]).any()


def test_targets_correctly_separated_no_cross_task_leakage(tmp_path: Path, raw_df: pd.DataFrame) -> None:
    input_path = tmp_path / "raw.csv"
    raw_df.to_csv(input_path, index=False)
    result = prepare(input_path=input_path, output_dir=tmp_path / "processed")

    delay_df = result["delay_features"]
    cost_df = result["cost_features"]

    for t in DELAY_TARGETS:
        assert t in delay_df.columns
    for t in COST_TARGETS:
        assert t not in delay_df.columns

    for t in COST_TARGETS:
        assert t in cost_df.columns
    for t in DELAY_TARGETS:
        assert t not in cost_df.columns


def test_targets_values_match_source(raw_df: pd.DataFrame, features: pd.DataFrame) -> None:
    merged = features.merge(
        raw_df[["project_id", "reporting_month", *DELAY_TARGETS, *COST_TARGETS]],
        on=["project_id", "reporting_month"],
        suffixes=("", "_raw"),
    )
    for t in DELAY_TARGETS + COST_TARGETS:
        pd.testing.assert_series_equal(merged[t], merged[f"{t}_raw"], check_names=False)


def test_duplicate_raw_columns_dropped(features: pd.DataFrame) -> None:
    for col in DUPLICATE_COLUMNS_DROPPED:
        assert col not in features.columns


def test_is_terminal_snapshot_matches_project_status(raw_df: pd.DataFrame, features: pd.DataFrame) -> None:
    merged = features.merge(
        raw_df[["project_id", "reporting_month", "project_status"]], on=["project_id", "reporting_month"]
    )
    expected = merged["project_status"] == "Completed"
    assert (merged["is_terminal_snapshot"] == expected).all()
    # exactly one terminal snapshot per project
    assert features.groupby("project_id")["is_terminal_snapshot"].sum().eq(1).all()


def test_engineered_ratio_features_are_capped(features: pd.DataFrame) -> None:
    assert (features["progress_efficiency"].dropna() <= RATIO_CAP).all()
    assert (features["cost_growth_rate"].dropna() <= RATIO_CAP).all()


def test_delay_factor_count_and_severity_ranges(features: pd.DataFrame) -> None:
    assert (features["delay_factor_count"].dropna().between(0, 10)).all()
    assert (features["delay_factor_severity"].dropna() >= 0).all()


def test_temporal_features_are_exact_functions_of_schedule(raw_df: pd.DataFrame, features: pd.DataFrame) -> None:
    merged = features.merge(
        raw_df[["project_id", "reporting_month", "planned_duration_months", "months_since_start"]],
        on=["project_id", "reporting_month"], suffixes=("", "_raw"),
    )
    expected_age_ratio = merged["months_since_start_raw"] / merged["planned_duration_months_raw"]
    assert np.allclose(merged["project_age_ratio"], expected_age_ratio)
    expected_months_left = merged["planned_duration_months_raw"] - merged["months_since_start_raw"]
    assert (merged["months_to_planned_completion"] == expected_months_left).all()


def test_reproducibility(tmp_path: Path, raw_df: pd.DataFrame) -> None:
    input_path = tmp_path / "raw.csv"
    raw_df.to_csv(input_path, index=False)
    result_a = prepare(input_path=input_path, output_dir=tmp_path / "out_a")
    result_b = prepare(input_path=input_path, output_dir=tmp_path / "out_b")
    pd.testing.assert_frame_equal(result_a["delay_features"], result_b["delay_features"])
    pd.testing.assert_frame_equal(result_a["cost_features"], result_b["cost_features"])


def test_historical_features_never_use_future_rows(raw_df: pd.DataFrame) -> None:
    """If any historical/rolling feature accidentally looked ahead, truncating a
    project's later snapshots would change the engineered values on its earlier,
    still-present snapshots. It must not."""
    full_features = build_feature_table(raw_df)

    truncated_rows = []
    for project_id, group in raw_df.groupby("project_id"):
        group_sorted = group.sort_values("reporting_month")
        keep = max(1, len(group_sorted) - 2)  # drop the last 2 snapshots
        truncated_rows.append(group_sorted.iloc[:keep])
    truncated_raw = pd.concat(truncated_rows, ignore_index=True)
    truncated_features = build_feature_table(truncated_raw)

    key_cols = ["project_id", "reporting_month"]
    historical_cols = [
        "recent_progress_trend_3m", "recent_cost_trend_3m",
        "consecutive_underperforming_months", "recent_adverse_events_3m",
    ]
    merged = truncated_features.merge(
        full_features[key_cols + historical_cols], on=key_cols, suffixes=("_trunc", "_full")
    )
    assert len(merged) == len(truncated_features)
    for col in historical_cols:
        pd.testing.assert_series_equal(
            merged[f"{col}_trunc"], merged[f"{col}_full"], check_names=False,
        )


def test_consecutive_underperforming_months_resets_on_good_month() -> None:
    from scripts.prepare_features import _consecutive_true_run

    flags = pd.Series([1, 1, 0, 1, 1, 1, 0, 0, 1])
    result = _consecutive_true_run(flags)
    assert list(result) == [1, 2, 0, 1, 2, 3, 0, 0, 1]


def test_checked_in_processed_datasets_exist_and_are_consistent() -> None:
    delay_path = Path("data/processed/delay_features.csv")
    cost_path = Path("data/processed/cost_features.csv")
    if not delay_path.exists() or not cost_path.exists():
        pytest.skip("processed datasets not generated yet")
    delay_df = pd.read_csv(delay_path)
    cost_df = pd.read_csv(cost_path)
    assert delay_df["project_id"].nunique() == cost_df["project_id"].nunique()
    assert len(delay_df) == len(cost_df)
    assert not delay_df.duplicated(subset=["project_id", "reporting_month"]).any()
    assert not cost_df.duplicated(subset=["project_id", "reporting_month"]).any()
