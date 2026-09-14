"""Phase 10: tests scripts/compute_training_ranges.py -- the min/max bounds
must come ONLY from the Phase 4 TRAINING partition (never validation, test,
or the full dataset), reusing scripts.data_split.project_level_split
unchanged. Uses a small synthetic dataset (like tests/test_data_split.py)
rather than the full 400-project real one, for speed."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from scripts.compute_training_ranges import compute_training_ranges
from scripts.data_split import project_level_split
from scripts.generate_dataset import generate_dataset
from scripts.prepare_features import PREDICTOR_COLUMNS, RAW_CATEGORICAL, build_feature_table

SMALL_N = 40


@pytest.fixture(scope="module")
def raw_df() -> pd.DataFrame:
    return generate_dataset(n_projects=SMALL_N, seed=321)


@pytest.fixture(scope="module")
def raw_csv_path(tmp_path_factory, raw_df: pd.DataFrame) -> Path:
    path = tmp_path_factory.mktemp("training_ranges_raw") / "raw.csv"
    raw_df.to_csv(path, index=False)
    return path


@pytest.fixture(scope="module")
def features_csv_path(tmp_path_factory, raw_df: pd.DataFrame) -> Path:
    features = build_feature_table(raw_df)
    path = tmp_path_factory.mktemp("training_ranges_features") / "delay_features.csv"
    features.to_csv(path, index=False)
    return path


def test_bounds_come_only_from_the_train_partition(features_csv_path: Path, raw_csv_path: Path):
    result = project_level_split(pd.read_csv(features_csv_path), raw_path=raw_csv_path)
    train_df = result.train

    computed = compute_training_ranges(features_csv_path, raw_path=raw_csv_path)
    ranges = computed["numeric_feature_ranges"]

    numeric_columns = [c for c in PREDICTOR_COLUMNS if c not in RAW_CATEGORICAL]
    assert set(ranges) == set(numeric_columns)

    for col in numeric_columns:
        expected_series = pd.to_numeric(train_df[col], errors="raise").dropna()
        assert ranges[col]["min"] == pytest.approx(float(expected_series.min()))
        assert ranges[col]["max"] == pytest.approx(float(expected_series.max()))
        assert ranges[col]["n_non_null"] == int(expected_series.count())


def test_categorical_columns_are_excluded(features_csv_path: Path, raw_csv_path: Path):
    computed = compute_training_ranges(features_csv_path, raw_path=raw_csv_path)
    for col in RAW_CATEGORICAL:
        assert col not in computed["numeric_feature_ranges"]


def test_deterministic_across_repeated_runs(features_csv_path: Path, raw_csv_path: Path):
    first = compute_training_ranges(features_csv_path, raw_path=raw_csv_path)
    second = compute_training_ranges(features_csv_path, raw_path=raw_csv_path)
    assert first["numeric_feature_ranges"] == second["numeric_feature_ranges"]


def test_run_metadata_documents_the_train_only_source(features_csv_path: Path, raw_csv_path: Path):
    computed = compute_training_ranges(features_csv_path, raw_path=raw_csv_path)
    meta = computed["run_metadata"]
    assert meta["split_partition_used"] == "train"
    assert meta["split_module"] == "scripts.data_split.project_level_split"
    assert meta["terminal_snapshot_excluded"] is True
