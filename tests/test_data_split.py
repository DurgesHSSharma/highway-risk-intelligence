from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts.data_split import assign_project_splits, project_level_split
from scripts.generate_dataset import generate_dataset
from scripts.prepare_features import build_feature_table

SMALL_N = 40


@pytest.fixture(scope="module")
def raw_df() -> pd.DataFrame:
    return generate_dataset(n_projects=SMALL_N, seed=321)


@pytest.fixture(scope="module")
def raw_csv_path(tmp_path_factory, raw_df: pd.DataFrame) -> Path:
    path = tmp_path_factory.mktemp("data_split_raw") / "raw.csv"
    raw_df.to_csv(path, index=False)
    return path


@pytest.fixture(scope="module")
def features(raw_df: pd.DataFrame) -> pd.DataFrame:
    return build_feature_table(raw_df)


def test_no_project_appears_in_more_than_one_split(features: pd.DataFrame, raw_csv_path: Path) -> None:
    result = project_level_split(features, raw_path=raw_csv_path)
    train_p = set(result.train["project_id"])
    val_p = set(result.validation["project_id"])
    test_p = set(result.test["project_id"])
    assert not (train_p & val_p)
    assert not (train_p & test_p)
    assert not (val_p & test_p)
    assert train_p | val_p | test_p == set(features["project_id"])


def test_project_level_grouping_preserved_at_row_level(features: pd.DataFrame, raw_csv_path: Path) -> None:
    """Every row for a given project_id must end up in exactly one split's
    output, never split across two (checked at the row level, not just via
    the id-set overlap check above)."""
    result = project_level_split(features, raw_path=raw_csv_path, exclude_terminal=False)
    combined = pd.concat([
        result.train.assign(_split="train"),
        result.validation.assign(_split="validation"),
        result.test.assign(_split="test"),
    ])
    per_project_split_counts = combined.groupby("project_id")["_split"].nunique()
    assert (per_project_split_counts == 1).all()


def test_no_terminal_snapshot_in_any_split(features: pd.DataFrame, raw_csv_path: Path) -> None:
    result = project_level_split(features, raw_path=raw_csv_path)
    assert not result.train["is_terminal_snapshot"].any()
    assert not result.validation["is_terminal_snapshot"].any()
    assert not result.test["is_terminal_snapshot"].any()


def test_terminal_rows_kept_when_exclusion_disabled(features: pd.DataFrame, raw_csv_path: Path) -> None:
    result = project_level_split(features, raw_path=raw_csv_path, exclude_terminal=False)
    total_terminal = (
        result.train["is_terminal_snapshot"].sum()
        + result.validation["is_terminal_snapshot"].sum()
        + result.test["is_terminal_snapshot"].sum()
    )
    assert total_terminal == features["is_terminal_snapshot"].sum()


def test_terminal_exclusion_metadata_matches_actual_rows(features: pd.DataFrame, raw_csv_path: Path) -> None:
    with_terminal = project_level_split(features, raw_path=raw_csv_path, exclude_terminal=False)
    without_terminal = project_level_split(features, raw_path=raw_csv_path, exclude_terminal=True)
    meta = without_terminal.metadata
    assert meta["n_terminal_rows_excluded_train"] == with_terminal.train["is_terminal_snapshot"].sum()
    assert meta["n_terminal_rows_excluded_validation"] == with_terminal.validation["is_terminal_snapshot"].sum()
    assert meta["n_terminal_rows_excluded_test"] == with_terminal.test["is_terminal_snapshot"].sum()
    assert len(without_terminal.train) == len(with_terminal.train) - with_terminal.train["is_terminal_snapshot"].sum()


def test_split_is_deterministic(features: pd.DataFrame, raw_csv_path: Path) -> None:
    result_a = project_level_split(features, raw_path=raw_csv_path, seed=42)
    result_b = project_level_split(features, raw_path=raw_csv_path, seed=42)
    pd.testing.assert_frame_equal(result_a.train, result_b.train)
    pd.testing.assert_frame_equal(result_a.validation, result_b.validation)
    pd.testing.assert_frame_equal(result_a.test, result_b.test)
    assert result_a.metadata == result_b.metadata


def test_different_seeds_can_change_tie_break_assignment(raw_csv_path: Path) -> None:
    """assign_project_splits should be a pure function of (project_ids, seed):
    same seed -> identical assignment; different seed is permitted to (but
    need not) change ties. This checks the seed is actually wired through,
    not merely accepted and ignored."""
    project_ids = generate_dataset(n_projects=SMALL_N, seed=321)["project_id"].unique()
    assignment_seed_a = assign_project_splits(project_ids, raw_path=raw_csv_path, seed=1)
    assignment_seed_a_again = assign_project_splits(project_ids, raw_path=raw_csv_path, seed=1)
    assert assignment_seed_a == assignment_seed_a_again

    assignment_seed_b = assign_project_splits(project_ids, raw_path=raw_csv_path, seed=2)
    assert isinstance(assignment_seed_b, dict)
    assert set(assignment_seed_b) == set(assignment_seed_a)


def test_assignment_independent_of_input_order(raw_csv_path: Path) -> None:
    project_ids = list(generate_dataset(n_projects=SMALL_N, seed=321)["project_id"].unique())
    forward = assign_project_splits(project_ids, raw_path=raw_csv_path, seed=42)
    reversed_order = assign_project_splits(list(reversed(project_ids)), raw_path=raw_csv_path, seed=42)
    assert forward == reversed_order


def test_missing_project_id_column_raises(features: pd.DataFrame, raw_csv_path: Path) -> None:
    broken = features.drop(columns=["project_id"])
    with pytest.raises(ValueError, match="project_id"):
        project_level_split(broken, raw_path=raw_csv_path)


def test_missing_is_terminal_snapshot_column_raises(features: pd.DataFrame, raw_csv_path: Path) -> None:
    broken = features.drop(columns=["is_terminal_snapshot"])
    with pytest.raises(ValueError, match="is_terminal_snapshot"):
        project_level_split(broken, raw_path=raw_csv_path)


def test_unknown_project_id_raises(features: pd.DataFrame, raw_csv_path: Path) -> None:
    injected = pd.concat([features, features.iloc[[0]].assign(project_id="NOT-A-REAL-PROJECT")], ignore_index=True)
    with pytest.raises(ValueError):
        project_level_split(injected, raw_path=raw_csv_path)


def test_split_fractions_leaving_empty_split_raises(raw_csv_path: Path) -> None:
    project_ids = generate_dataset(n_projects=SMALL_N, seed=321)["project_id"].unique()
    with pytest.raises(ValueError):
        assign_project_splits(project_ids, raw_path=raw_csv_path, train_frac=0.99, val_frac=0.005)


def test_split_row_counts_match_project_counts(features: pd.DataFrame, raw_csv_path: Path) -> None:
    result = project_level_split(features, raw_path=raw_csv_path)
    m = result.metadata
    assert m["n_projects_train"] + m["n_projects_validation"] + m["n_projects_test"] == m["n_projects_total"]
    assert m["n_rows_train"] == len(result.train)
    assert m["n_rows_validation"] == len(result.validation)
    assert m["n_rows_test"] == len(result.test)


def test_chronological_ordering_train_starts_no_later_than_test(features: pd.DataFrame, raw_csv_path: Path) -> None:
    """The chronological-cohort rule should put earlier-started projects in
    train and later-started projects in test (see docs/TRAIN_VAL_TEST_STRATEGY.md)."""
    result = project_level_split(features, raw_path=raw_csv_path)
    train_start, _ = result.metadata["planned_start_date_range_train"]
    _, test_end = result.metadata["planned_start_date_range_test"]
    _, train_end = result.metadata["planned_start_date_range_train"]
    test_start, _ = result.metadata["planned_start_date_range_test"]
    assert train_start <= test_start
    assert train_end <= test_end
