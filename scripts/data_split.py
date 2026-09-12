"""
Phase 4: reusable, leakage-safe project-level train/validation/test split.

All four Phase 4 prediction tasks share this module so the split logic is
implemented exactly once (see docs/TRAIN_VAL_TEST_STRATEGY.md for the full
write-up of the methodology and why it was chosen).

Why a project-level split at all
---------------------------------
`final_delay_days`, `significant_delay`, `final_cost_overrun_pct`,
`cost_overrun` are constant across every snapshot row of a given
`project_id` (verified in Phase 2/3). A row-level random split would put
different months of the *same* project into both train and test, which
means the model would already have seen that exact project's answer during
training via an earlier snapshot -- leakage. Every row of a project must
therefore land entirely in one split (see `docs/FEATURE_ENGINEERING.md`
section 8).

Why chronological (not purely random) project assignment
-----------------------------------------------------------
`planned_start_date` for the 400 synthetic projects spans 2019-01 to
2024-06, broken down as: 2019=76, 2020=65, 2021=76, 2022=69, 2023=72,
2024=42 (partial year) projects -- a reasonably even year-over-year spread,
not a single narrow cluster. Ordering projects by `planned_start_date` and
holding out the most-recently-started cohort as validation/test simulates
the intended real deployment scenario ("predict this project's outcome
using only information available today, for a project the model has not
seen before") more realistically than a purely random project shuffle.
A quick check of class balance under a 70/15/15 chronological cut showed
no degenerate split (`significant_delay` rate 49.6%/53.3%/43.3% and
`cost_overrun` rate 37.9%/46.7%/31.7% in train/validation/test
respectively) -- see docs/TRAIN_VAL_TEST_STRATEGY.md for the full table.

`planned_start_date` has month-level granularity (65 unique values across
400 projects; up to 15 projects share the same start month), so ties are
broken with a seeded random draw (`seed`, default 42) rather than by
`project_id` string order, to avoid any hidden correlation between
generation order and a project's latent traits.

Terminal snapshot exclusion (section 8 of the Phase 4 brief / Phase 3's
`is_terminal_snapshot` finding) is applied per-row after project
assignment: it never changes which split a project's remaining rows sit
in, it only drops that project's single terminal row from every split's
modeling data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RAW_PATH = REPO_ROOT / "data" / "synthetic" / "highway_project_snapshots.csv"

DEFAULT_SEED = 42
DEFAULT_TRAIN_FRAC = 0.70
DEFAULT_VAL_FRAC = 0.15


@dataclass
class SplitResult:
    """Container returned by `project_level_split`.

    `train`/`validation`/`test` are row-filtered copies of the input
    DataFrame (terminal snapshots excluded by default). `metadata` carries
    everything needed for reporting and reproducibility (see
    docs/TRAIN_VAL_TEST_STRATEGY.md).
    """

    train: pd.DataFrame
    validation: pd.DataFrame
    test: pd.DataFrame
    metadata: dict = field(default_factory=dict)


def _project_start_dates(raw_path: Path) -> pd.DataFrame:
    raw = pd.read_csv(raw_path, usecols=["project_id", "planned_start_date"])
    starts = raw.drop_duplicates("project_id").copy()
    starts["planned_start_date"] = pd.to_datetime(starts["planned_start_date"])
    return starts.sort_values("project_id").reset_index(drop=True)


def assign_project_splits(
    project_ids,
    raw_path: Path = DEFAULT_RAW_PATH,
    train_frac: float = DEFAULT_TRAIN_FRAC,
    val_frac: float = DEFAULT_VAL_FRAC,
    seed: int = DEFAULT_SEED,
) -> dict:
    """Assign each project_id to 'train' / 'validation' / 'test'.

    Deterministic given (project_ids, raw_path, train_frac, val_frac, seed):
    projects are always sorted alphabetically by project_id before the
    seeded RNG draws tie-break values, so the result does not depend on the
    input iteration order of `project_ids`.
    """
    project_id_set = set(project_ids)
    starts = _project_start_dates(raw_path)
    starts = starts[starts["project_id"].isin(project_id_set)].reset_index(drop=True)

    missing = project_id_set - set(starts["project_id"])
    if missing:
        raise ValueError(
            f"{len(missing)} project_id(s) not found in raw dataset {raw_path}: "
            f"{sorted(missing)[:5]}"
        )

    rng = np.random.default_rng(seed)
    starts = starts.sort_values("project_id").reset_index(drop=True)
    starts["_tiebreak"] = rng.random(len(starts))

    ordered = starts.sort_values(["planned_start_date", "_tiebreak"]).reset_index(drop=True)
    n = len(ordered)
    n_train = round(n * train_frac)
    n_val = round(n * val_frac)
    n_test = n - n_train - n_val

    if n_train < 1 or n_val < 1 or n_test < 1:
        raise ValueError(
            f"Split fractions produced an empty split for n={n} projects "
            f"(train={n_train}, validation={n_val}, test={n_test}); "
            "adjust train_frac/val_frac or provide more projects."
        )

    labels = np.empty(n, dtype=object)
    labels[:n_train] = "train"
    labels[n_train:n_train + n_val] = "validation"
    labels[n_train + n_val:] = "test"

    return dict(zip(ordered["project_id"], labels))


def project_level_split(
    df: pd.DataFrame,
    raw_path: Path = DEFAULT_RAW_PATH,
    train_frac: float = DEFAULT_TRAIN_FRAC,
    val_frac: float = DEFAULT_VAL_FRAC,
    seed: int = DEFAULT_SEED,
    exclude_terminal: bool = True,
) -> SplitResult:
    """Split a Phase 3 feature table (delay_features.csv / cost_features.csv
    or any table sharing their `project_id` / `is_terminal_snapshot` /
    `reporting_month` columns) into leakage-safe train/validation/test sets.

    Guarantees:
      - every row of a given project_id lands in exactly one of the three
        returned DataFrames (asserted internally)
      - `is_terminal_snapshot == True` rows are dropped from all three
        splits when `exclude_terminal=True` (the default)
    """
    if "project_id" not in df.columns:
        raise ValueError("df must contain a project_id column")
    if "is_terminal_snapshot" not in df.columns:
        raise ValueError("df must contain an is_terminal_snapshot column")

    assignment = assign_project_splits(df["project_id"].unique(), raw_path, train_frac, val_frac, seed)
    split_series = df["project_id"].map(assignment)
    if split_series.isna().any():
        unmatched = df.loc[split_series.isna(), "project_id"].unique()
        raise ValueError(f"Could not assign split for project_id(s): {sorted(unmatched)[:5]}")

    terminal_mask = df["is_terminal_snapshot"].astype(bool)
    keep_mask = ~terminal_mask if exclude_terminal else pd.Series(True, index=df.index)

    train_df = df.loc[(split_series == "train").values & keep_mask.values].reset_index(drop=True)
    val_df = df.loc[(split_series == "validation").values & keep_mask.values].reset_index(drop=True)
    test_df = df.loc[(split_series == "test").values & keep_mask.values].reset_index(drop=True)

    train_p, val_p, test_p = set(train_df["project_id"]), set(val_df["project_id"]), set(test_df["project_id"])
    assert not (train_p & val_p), "train/validation project overlap detected"
    assert not (train_p & test_p), "train/test project overlap detected"
    assert not (val_p & test_p), "validation/test project overlap detected"

    starts_map = _project_start_dates(raw_path).set_index("project_id")["planned_start_date"]

    def _date_range(pids):
        if not pids:
            return (None, None)
        dates = starts_map.loc[sorted(pids)]
        return (str(dates.min().date()), str(dates.max().date()))

    def _month_range(part_df):
        if len(part_df) == 0:
            return (None, None)
        return (str(part_df["reporting_month"].min()), str(part_df["reporting_month"].max()))

    metadata = {
        "seed": seed,
        "train_frac": train_frac,
        "val_frac": val_frac,
        "test_frac": round(1 - train_frac - val_frac, 6),
        "split_rule": (
            "Project-level chronological cohort split: all projects ordered by "
            "planned_start_date (ties on an identical start month broken by a "
            f"seeded random draw, seed={seed}); the earliest {train_frac:.0%} of "
            f"projects assigned to train, the next {val_frac:.0%} to validation, "
            f"and the most-recently-started {1 - train_frac - val_frac:.0%} to test. "
            "Assignment never used any outcome/target value."
        ),
        "raw_dataset_path": str(raw_path),
        "terminal_snapshot_excluded": exclude_terminal,
        "n_projects_total": int(df["project_id"].nunique()),
        "n_projects_train": len(train_p),
        "n_projects_validation": len(val_p),
        "n_projects_test": len(test_p),
        "n_rows_train": len(train_df),
        "n_rows_validation": len(val_df),
        "n_rows_test": len(test_df),
        "n_terminal_rows_total": int(terminal_mask.sum()),
        "n_terminal_projects_total": int(df.loc[terminal_mask, "project_id"].nunique()),
        "n_terminal_rows_excluded_train": int((terminal_mask.values & (split_series == "train").values).sum()),
        "n_terminal_rows_excluded_validation": int((terminal_mask.values & (split_series == "validation").values).sum()),
        "n_terminal_rows_excluded_test": int((terminal_mask.values & (split_series == "test").values).sum()),
        "planned_start_date_range_train": _date_range(train_p),
        "planned_start_date_range_validation": _date_range(val_p),
        "planned_start_date_range_test": _date_range(test_p),
        "reporting_month_range_train": _month_range(train_df),
        "reporting_month_range_validation": _month_range(val_df),
        "reporting_month_range_test": _month_range(test_df),
    }

    return SplitResult(train=train_df, validation=val_df, test=test_df, metadata=metadata)


def main() -> None:
    from scripts.prepare_features import DEFAULT_OUTPUT_DIR

    df = pd.read_csv(DEFAULT_OUTPUT_DIR / "delay_features.csv")
    result = project_level_split(df)
    print("Split rule:", result.metadata["split_rule"])
    for split_name in ("train", "validation", "test"):
        print(
            f"{split_name:10s}: {result.metadata[f'n_projects_{split_name}']:3d} projects, "
            f"{result.metadata[f'n_rows_{split_name}']:5d} rows, "
            f"start dates {result.metadata[f'planned_start_date_range_{split_name}']}"
        )


if __name__ == "__main__":
    main()
