"""Phase 10: loads the numeric predictor-feature training ranges computed by
`scripts/compute_training_ranges.py` from the frozen Phase 4 TRAINING split
(never validation/test/full-dataset/live-snapshot data) -- used by the
what-if simulator's extrapolation-warning check (see
docs/WHATIF_SIMULATOR.md).

Loaded ONCE at application startup (mirrors app.ml.registry.load_models's
load-once pattern) and never recomputed per request. Fails loudly if the
artifact is missing, exactly like a missing model artifact -- this module
never falls back to computing ranges from validation/test/full data.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import settings


class TrainingRangesMissingError(RuntimeError):
    pass


_NUMERIC_FEATURE_RANGES: dict[str, dict[str, float]] = {}
_RUN_METADATA: dict[str, Any] = {}


def training_ranges_path() -> Path:
    return settings.models_dir_path / "metrics" / "training_feature_ranges.json"


def load_training_ranges() -> None:
    path = training_ranges_path()
    if not path.exists():
        raise TrainingRangesMissingError(
            "Phase 10 startup failed: the training-range artifact required by the "
            f"what-if simulator was not found at {path}. This service does not "
            "compute ranges from validation/test/full data as a fallback -- run "
            "`python -m scripts.compute_training_ranges` first (it is committed to "
            "git; see docs/WHATIF_SIMULATOR.md)."
        )
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    _NUMERIC_FEATURE_RANGES.clear()
    _NUMERIC_FEATURE_RANGES.update(data["numeric_feature_ranges"])
    _RUN_METADATA.clear()
    _RUN_METADATA.update(data["run_metadata"])


def is_loaded() -> bool:
    return bool(_NUMERIC_FEATURE_RANGES)


def get_range(field: str) -> dict[str, float] | None:
    """Returns {"min": ..., "max": ..., "n_non_null": ...} for a numeric
    predictor column, or None if the field has no training-range entry
    (e.g. a categorical column, which is never extrapolation-checked)."""
    return _NUMERIC_FEATURE_RANGES.get(field)


def get_metadata() -> dict[str, Any]:
    return dict(_RUN_METADATA)
