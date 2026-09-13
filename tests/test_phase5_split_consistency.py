"""
Phase 5: proves the frozen Phase 4 project-level split is reused EXACTLY,
never reimplemented or recomputed differently.

tests/fixtures/phase4_frozen_split_project_ids.json is a one-time snapshot
of scripts.data_split.project_level_split's actual output (train/validation/
test project_id sets for both delay_features.csv and cost_features.csv),
captured at Phase 5 kickoff. This is the persisted "Phase 4 train/validation/
test project IDs" the brief requires Phase 5 to match -- comparing against a
saved fixture (rather than only two live calls to each other) means the
test would also catch someone changing the seed, the raw dataset, or
`project_level_split`'s internal ordering/assignment logic, not just an
accidental second reimplementation.
"""

import json
from pathlib import Path

import pandas as pd
import pytest

from scripts.data_split import project_level_split
from scripts.prepare_features import PREDICTOR_COLUMNS

REPO_ROOT = Path(__file__).resolve().parent.parent
DELAY_FEATURES_PATH = REPO_ROOT / "data" / "processed" / "delay_features.csv"
COST_FEATURES_PATH = REPO_ROOT / "data" / "processed" / "cost_features.csv"
BASELINE_METRICS_PATH = REPO_ROOT / "models" / "metrics" / "baseline_metrics.json"
FROZEN_SPLIT_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "phase4_frozen_split_project_ids.json"

DATASET_FILES = {
    "delay_features.csv": DELAY_FEATURES_PATH,
    "cost_features.csv": COST_FEATURES_PATH,
}


@pytest.fixture(scope="module")
def baseline_metrics() -> dict:
    with open(BASELINE_METRICS_PATH) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def frozen_split_ids() -> dict:
    with open(FROZEN_SPLIT_FIXTURE) as f:
        return json.load(f)


@pytest.fixture(scope="module", params=list(DATASET_FILES))
def dataset_name(request) -> str:
    return request.param


@pytest.fixture(scope="module")
def dataset_df(dataset_name) -> pd.DataFrame:
    return pd.read_csv(DATASET_FILES[dataset_name])


def test_phase5_train_project_ids_equal_phase4_train_project_ids(dataset_name, dataset_df, frozen_split_ids):
    result = project_level_split(dataset_df)
    expected = frozen_split_ids[dataset_name]
    assert sorted(result.train["project_id"].unique()) == expected["train_project_ids"]


def test_phase5_validation_project_ids_equal_phase4_validation_project_ids(dataset_name, dataset_df, frozen_split_ids):
    result = project_level_split(dataset_df)
    expected = frozen_split_ids[dataset_name]
    assert sorted(result.validation["project_id"].unique()) == expected["validation_project_ids"]


def test_phase5_test_project_ids_equal_phase4_test_project_ids(dataset_name, dataset_df, frozen_split_ids):
    result = project_level_split(dataset_df)
    expected = frozen_split_ids[dataset_name]
    assert sorted(result.test["project_id"].unique()) == expected["test_project_ids"]


def test_phase5_split_metadata_matches_frozen_baseline_metrics_json(dataset_name, dataset_df, baseline_metrics):
    """Cross-checks against the actual persisted Phase 4 run output (not
    just a fresh reference fixture) -- project counts, row counts, and
    planned_start_date ranges per split must match exactly."""
    result = project_level_split(dataset_df)
    frozen_meta = baseline_metrics["run_metadata"]["split_metadata"][dataset_name]
    for split_name in ("train", "validation", "test"):
        assert result.metadata[f"n_projects_{split_name}"] == frozen_meta[f"n_projects_{split_name}"]
        assert result.metadata[f"n_rows_{split_name}"] == frozen_meta[f"n_rows_{split_name}"]
        assert (
            list(result.metadata[f"planned_start_date_range_{split_name}"])
            == list(frozen_meta[f"planned_start_date_range_{split_name}"])
        )
    assert result.metadata["seed"] == frozen_meta["seed"] == 42


def test_zero_project_overlap_between_splits(dataset_name, dataset_df):
    result = project_level_split(dataset_df)
    train_p = set(result.train["project_id"])
    val_p = set(result.validation["project_id"])
    test_p = set(result.test["project_id"])
    assert not (train_p & val_p)
    assert not (train_p & test_p)
    assert not (val_p & test_p)


def test_zero_terminal_snapshots_in_modeling_data(dataset_name, dataset_df):
    result = project_level_split(dataset_df)
    assert not result.train["is_terminal_snapshot"].any()
    assert not result.validation["is_terminal_snapshot"].any()
    assert not result.test["is_terminal_snapshot"].any()


def test_exactly_45_predictor_columns_present_in_dataset(dataset_name, dataset_df):
    assert len(PREDICTOR_COLUMNS) == 45
    for col in PREDICTOR_COLUMNS:
        assert col in dataset_df.columns


def test_targets_and_identifiers_are_not_predictors(dataset_name, dataset_df):
    non_predictor_columns = {
        "project_id", "reporting_month", "is_terminal_snapshot",
        "final_delay_days", "significant_delay",
        "final_cost_overrun_pct", "cost_overrun",
    }
    assert set(PREDICTOR_COLUMNS).isdisjoint(non_predictor_columns)
