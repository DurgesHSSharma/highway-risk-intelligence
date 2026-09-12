from pathlib import Path

import pandas as pd
import pytest

from scripts.generate_dataset import generate_dataset
from scripts.validate_dataset import (
    DEFAULT_DATASET_PATH,
    check_file_exists,
    check_no_duplicate_snapshots,
    check_percentage_ranges,
    check_required_columns,
    check_target_definitions,
    run_validation,
)


@pytest.fixture(scope="module")
def small_df() -> pd.DataFrame:
    return generate_dataset(n_projects=20, seed=99)


def test_generated_dataset_passes_full_validation(small_df: pd.DataFrame, tmp_path: Path) -> None:
    csv_path = tmp_path / "snapshots.csv"
    small_df.to_csv(csv_path, index=False)
    results = run_validation(csv_path)
    failures = [r for r in results if r.status == "FAIL"]
    assert not failures, failures


def test_check_file_exists_reports_fail_for_missing_file(tmp_path: Path) -> None:
    result = check_file_exists(tmp_path / "does_not_exist.csv")
    assert result.status == "FAIL"


def test_check_required_columns_detects_missing_column(small_df: pd.DataFrame) -> None:
    broken = small_df.drop(columns=["project_status"])
    result = check_required_columns(broken)
    assert result.status == "FAIL"
    assert "project_status" in result.message


def test_check_no_duplicate_snapshots_detects_duplicates(small_df: pd.DataFrame) -> None:
    broken = pd.concat([small_df, small_df.iloc[[0]]], ignore_index=True)
    result = check_no_duplicate_snapshots(broken)
    assert result.status == "FAIL"


def test_check_target_definitions_detects_mismatch(small_df: pd.DataFrame) -> None:
    broken = small_df.copy()
    broken.loc[broken.index[0], "significant_delay"] = 1 - broken.loc[broken.index[0], "significant_delay"]
    result = check_target_definitions(broken)
    assert result.status == "FAIL"


def test_check_percentage_ranges_detects_out_of_range(small_df: pd.DataFrame) -> None:
    broken = small_df.copy()
    broken.loc[broken.index[0], "actual_physical_progress_pct"] = 150.0
    result = check_percentage_ranges(broken)
    assert result.status == "FAIL"


def test_checked_in_dataset_passes_validation() -> None:
    if not DEFAULT_DATASET_PATH.exists():
        pytest.skip(f"{DEFAULT_DATASET_PATH} not generated yet")
    results = run_validation(DEFAULT_DATASET_PATH)
    failures = [r for r in results if r.status == "FAIL"]
    assert not failures, failures
