"""
Phase 10: computes the observed min/max of every NUMERIC permitted predictor
feature over the frozen Phase 4 TRAINING split ONLY (never validation, test,
the full dataset, or a live snapshot) -- consumed by the what-if simulator's
extrapolation-warning check (see docs/WHATIF_SIMULATOR.md).

Reuses `scripts.data_split.project_level_split` with its own defaults (seed
42, 70/15/15, terminal snapshots excluded) against
`data/processed/delay_features.csv` -- the exact same split module and
parameters Phase 4/5 used to train every model artifact this project serves.
No split logic is reimplemented here.

Categorical predictor columns (`state`, `project_type`, `contractor`) are
excluded -- per the Phase 10 brief, only numeric features get an
extrapolation check; categorical values are validated against the permitted
feature schema and the existing preprocessing's own `handle_unknown="ignore"`
behavior instead (see scripts/train_baseline_models.py::build_preprocessor).

Writes models/metrics/training_feature_ranges.json (same
committed-artifact convention as models/metrics/baseline_metrics.json /
tree_metrics.json).

Usage (from repo root):
    ./backend/.venv/Scripts/python.exe -m scripts.compute_training_ranges
"""

from __future__ import annotations

import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FEATURES_PATH = REPO_ROOT / "data" / "processed" / "delay_features.csv"
DEFAULT_OUTPUT_PATH = REPO_ROOT / "models" / "metrics" / "training_feature_ranges.json"


def compute_training_ranges(features_path: Path = DEFAULT_FEATURES_PATH, raw_path: Path | None = None) -> dict:
    from scripts.data_split import DEFAULT_RAW_PATH, DEFAULT_SEED, DEFAULT_TRAIN_FRAC, DEFAULT_VAL_FRAC, project_level_split
    from scripts.prepare_features import PREDICTOR_COLUMNS, RAW_CATEGORICAL

    df = pd.read_csv(features_path)
    # `raw_path` is only ever overridden by tests (to point project_level_split's
    # planned_start_date lookup at a small synthetic raw CSV instead of the real
    # committed dataset) -- production always uses the same DEFAULT_RAW_PATH
    # scripts.data_split itself defaults to.
    split = project_level_split(df, raw_path=raw_path or DEFAULT_RAW_PATH)  # seed=42, train/val=70/15, exclude_terminal=True
    train_df = split.train

    numeric_columns = [c for c in PREDICTOR_COLUMNS if c not in RAW_CATEGORICAL]
    ranges: dict[str, dict] = {}
    for col in numeric_columns:
        series = pd.to_numeric(train_df[col], errors="raise").dropna()
        ranges[col] = {
            "min": float(series.min()),
            "max": float(series.max()),
            "n_non_null": int(series.count()),
        }

    try:
        source_features_file = str(features_path.resolve().relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        # Not under REPO_ROOT -- e.g. a test's tmp_path fixture. Record the
        # absolute path rather than raising; this is metadata, not a
        # correctness input.
        source_features_file = str(features_path)

    return {
        "run_metadata": {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_features_file": source_features_file,
            "split_module": "scripts.data_split.project_level_split",
            "split_partition_used": "train",
            "seed": DEFAULT_SEED,
            "train_frac": DEFAULT_TRAIN_FRAC,
            "val_frac": DEFAULT_VAL_FRAC,
            "terminal_snapshot_excluded": True,
            "n_train_projects": split.metadata["n_projects_train"],
            "n_train_rows": split.metadata["n_rows_train"],
            "categorical_columns_excluded": list(RAW_CATEGORICAL),
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "pandas_version": pd.__version__,
            "numpy_version": np.__version__,
            "note": (
                "Bounds are computed ONLY from the Phase 4 TRAINING partition "
                "(never validation/test/full-dataset/live-snapshot data). See "
                "docs/WHATIF_SIMULATOR.md section 11 for how this artifact is used."
            ),
        },
        "numeric_feature_ranges": ranges,
    }


def main() -> None:
    result = compute_training_ranges()
    DEFAULT_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DEFAULT_OUTPUT_PATH, "w") as f:
        json.dump(result, f, indent=2)

    meta = result["run_metadata"]
    print(f"Wrote {len(result['numeric_feature_ranges'])} numeric feature ranges to {DEFAULT_OUTPUT_PATH}")
    print(f"Source: {meta['source_features_file']} | train partition: "
          f"{meta['n_train_rows']} rows / {meta['n_train_projects']} projects (seed={meta['seed']})")


if __name__ == "__main__":
    main()
