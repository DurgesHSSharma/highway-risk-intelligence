"""
Phase 4: leakage-safe baseline models for the four highway project
prediction tasks, evaluated against naive baselines on a project-level
train/validation/test split (see scripts/data_split.py and
docs/TRAIN_VAL_TEST_STRATEGY.md).

Tasks
-----
A. delay classification   -- target `significant_delay`   (DummyClassifier + LogisticRegression)
B. delay regression       -- target `final_delay_days`     (DummyRegressor x2 + LinearRegression)
C. cost classification    -- target `cost_overrun`         (DummyClassifier + LogisticRegression)
D. cost regression        -- target `final_cost_overrun_pct` (DummyRegressor x2 + LinearRegression)

Design
------
- Predictor columns come directly from `scripts.prepare_features.PREDICTOR_COLUMNS`
  (the Phase 3 leakage-audited feature set) -- never redefined here, so this
  script cannot silently drift from the audited feature list.
- Preprocessing (median imputation + scaling for numeric columns, an
  explicit "Unknown" fill + one-hot encoding for categoricals) is a
  scikit-learn Pipeline/ColumnTransformer fit ONLY inside each model's
  `.fit(X_train, y_train)` call -- it never sees validation/test rows
  during fitting (see docs/TRAIN_VAL_TEST_STRATEGY.md "Preprocessing" and
  tests/test_train_baseline_models.py::test_preprocessing_fit_is_train_only).
- No hyperparameter tuning. LogisticRegression and LinearRegression use
  sklearn's default configuration (only `random_state` is set, for
  reproducibility) -- checked empirically that the default `max_iter=100`
  lbfgs solver converges within 84-87 iterations on both classification
  tasks' training folds (see docs/BASELINE_MODEL_REPORT.md "Overfitting/
  sanity checks"), so no solver adjustment was needed or made. A benign
  `OptimizeWarning: Unknown solver options: iprint` appears during fitting
  regardless of max_iter -- this is a known scikit-learn 1.5.2 / scipy
  1.18.1 version-compatibility message (scipy no longer recognizes an
  internal lbfgs option sklearn still passes), not a convergence problem;
  `n_iter_` confirms convergence well under the iteration cap either way.

Usage (from backend/.venv):
    ../backend/.venv/Scripts/python.exe train_baseline_models.py
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    median_absolute_error,
    precision_score,
    r2_score,
    recall_score,
    roc_auc_score,
    root_mean_squared_error,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from scripts.data_split import DEFAULT_SEED, DEFAULT_TRAIN_FRAC, DEFAULT_VAL_FRAC, project_level_split
from scripts.prepare_features import PREDICTOR_COLUMNS, RAW_CATEGORICAL

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROCESSED_DIR = REPO_ROOT / "data" / "processed"
DEFAULT_MODELS_DIR = REPO_ROOT / "models" / "baseline"
DEFAULT_METRICS_PATH = REPO_ROOT / "models" / "metrics" / "baseline_metrics.json"

NUMERIC_PREDICTORS = [c for c in PREDICTOR_COLUMNS if c not in RAW_CATEGORICAL]
CATEGORICAL_PREDICTORS = list(RAW_CATEGORICAL)

RANDOM_STATE = DEFAULT_SEED

TASKS = {
    "delay_classification": {
        "dataset": "delay_features.csv",
        "target": "significant_delay",
        "task_type": "classification",
        "label": "Task A: Significant Delay Classification",
    },
    "delay_regression": {
        "dataset": "delay_features.csv",
        "target": "final_delay_days",
        "task_type": "regression",
        "label": "Task B: Delay Duration Regression",
    },
    "cost_classification": {
        "dataset": "cost_features.csv",
        "target": "cost_overrun",
        "task_type": "classification",
        "label": "Task C: Cost Overrun Classification",
    },
    "cost_regression": {
        "dataset": "cost_features.csv",
        "target": "final_cost_overrun_pct",
        "task_type": "regression",
        "label": "Task D: Cost Overrun Regression",
    },
}


def build_preprocessor() -> ColumnTransformer:
    """Median-impute + scale numeric columns; Unknown-fill + one-hot encode
    categoricals. Fit only where `.fit`/`.fit_transform` is explicitly
    called (i.e. only on a training split, never on validation/test)."""
    numeric_pipeline = Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
    ])
    categorical_pipeline = Pipeline([
        ("impute", SimpleImputer(strategy="constant", fill_value="Unknown")),
        ("encode", OneHotEncoder(handle_unknown="ignore")),
    ])
    return ColumnTransformer([
        ("numeric", numeric_pipeline, NUMERIC_PREDICTORS),
        ("categorical", categorical_pipeline, CATEGORICAL_PREDICTORS),
    ])


def classification_metrics(y_true: pd.Series, y_pred: np.ndarray, y_score: np.ndarray) -> dict:
    metrics: dict = {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=[0, 1]).tolist(),
        "confusion_matrix_labels": ["actual_0", "actual_1"],
    }
    if y_true.nunique() < 2:
        metrics["roc_auc"] = None
        metrics["pr_auc"] = None
        metrics["auc_unavailable_reason"] = (
            "Only one class present in y_true for this split; ROC-AUC/PR-AUC are "
            "mathematically undefined and are not reported."
        )
    else:
        metrics["roc_auc"] = float(roc_auc_score(y_true, y_score))
        metrics["pr_auc"] = float(average_precision_score(y_true, y_score))
    return metrics


def regression_metrics(y_true: pd.Series, y_pred: np.ndarray) -> dict:
    return {
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "rmse": float(root_mean_squared_error(y_true, y_pred)),
        "r2": float(r2_score(y_true, y_pred)),
        "median_ae": float(median_absolute_error(y_true, y_pred)),
    }


def run_classification_task(task_key: str, cfg: dict, split, models_dir: Path) -> dict:
    target = cfg["target"]
    X_train, y_train = split.train[PREDICTOR_COLUMNS], split.train[target]
    X_val, y_val = split.validation[PREDICTOR_COLUMNS], split.validation[target]
    X_test, y_test = split.test[PREDICTOR_COLUMNS], split.test[target]

    dummy = DummyClassifier(strategy="most_frequent", random_state=RANDOM_STATE)
    dummy.fit(X_train, y_train)

    model = Pipeline([
        ("preprocess", build_preprocessor()),
        ("model", LogisticRegression(random_state=RANDOM_STATE)),
    ])
    model.fit(X_train, y_train)

    models_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = models_dir / f"{task_key}_logistic_regression.joblib"
    import joblib
    joblib.dump(model, artifact_path)

    result = {
        "task_type": "classification",
        "label": cfg["label"],
        "target": target,
        "n_predictors": len(PREDICTOR_COLUMNS),
        "n_train_rows": len(X_train),
        "n_validation_rows": len(X_val),
        "n_test_rows": len(X_test),
        "class_balance_train": {str(k): int(v) for k, v in y_train.value_counts().sort_index().items()},
        "class_balance_validation": {str(k): int(v) for k, v in y_val.value_counts().sort_index().items()},
        "class_balance_test": {str(k): int(v) for k, v in y_test.value_counts().sort_index().items()},
        "model_config": {
            "logistic_regression": {"max_iter": "100 (sklearn default)", "random_state": RANDOM_STATE, "solver": "lbfgs (default)"},
        },
        "artifact_path": str(artifact_path.relative_to(REPO_ROOT)),
        "baseline": {"strategy": "DummyClassifier(strategy='most_frequent')"},
        "validation": {}, "test": {},
    }

    for split_name, X_split, y_split in [("validation", X_val, y_val), ("test", X_test, y_test)]:
        dummy_pred = dummy.predict(X_split)
        dummy_score = dummy.predict_proba(X_split)[:, 1]
        model_pred = model.predict(X_split)
        model_score = model.predict_proba(X_split)[:, 1]
        result[split_name] = {
            "baseline": classification_metrics(y_split, dummy_pred, dummy_score),
            "logistic_regression": classification_metrics(y_split, model_pred, model_score),
        }
        result[split_name]["improvement_over_baseline"] = {
            metric: (
                result[split_name]["logistic_regression"][metric] - result[split_name]["baseline"][metric]
                if result[split_name]["logistic_regression"][metric] is not None
                and result[split_name]["baseline"][metric] is not None
                else None
            )
            for metric in ("accuracy", "f1", "roc_auc", "pr_auc")
        }
    return result


def run_regression_task(task_key: str, cfg: dict, split, models_dir: Path) -> dict:
    target = cfg["target"]
    X_train, y_train = split.train[PREDICTOR_COLUMNS], split.train[target]
    X_val, y_val = split.validation[PREDICTOR_COLUMNS], split.validation[target]
    X_test, y_test = split.test[PREDICTOR_COLUMNS], split.test[target]

    dummy_mean = DummyRegressor(strategy="mean")
    dummy_mean.fit(X_train, y_train)
    dummy_median = DummyRegressor(strategy="median")
    dummy_median.fit(X_train, y_train)

    model = Pipeline([
        ("preprocess", build_preprocessor()),
        ("model", LinearRegression()),
    ])
    model.fit(X_train, y_train)

    models_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = models_dir / f"{task_key}_linear_regression.joblib"
    import joblib
    joblib.dump(model, artifact_path)

    result = {
        "task_type": "regression",
        "label": cfg["label"],
        "target": target,
        "n_predictors": len(PREDICTOR_COLUMNS),
        "n_train_rows": len(X_train),
        "n_validation_rows": len(X_val),
        "n_test_rows": len(X_test),
        "target_stats_train": {
            "mean": float(y_train.mean()), "median": float(y_train.median()), "std": float(y_train.std()),
        },
        "model_config": {"linear_regression": {"fit_intercept": True}},
        "artifact_path": str(artifact_path.relative_to(REPO_ROOT)),
        "baseline": {"strategy": "DummyRegressor(mean) and DummyRegressor(median)"},
        "validation": {}, "test": {},
    }

    for split_name, X_split, y_split in [("validation", X_val, y_val), ("test", X_test, y_test)]:
        mean_pred = dummy_mean.predict(X_split)
        median_pred = dummy_median.predict(X_split)
        model_pred = model.predict(X_split)
        result[split_name] = {
            "baseline_mean": regression_metrics(y_split, mean_pred),
            "baseline_median": regression_metrics(y_split, median_pred),
            "linear_regression": regression_metrics(y_split, model_pred),
        }
        best_baseline_mae = min(result[split_name]["baseline_mean"]["mae"], result[split_name]["baseline_median"]["mae"])
        result[split_name]["improvement_over_best_baseline"] = {
            "mae": best_baseline_mae - result[split_name]["linear_regression"]["mae"],
            "r2": result[split_name]["linear_regression"]["r2"],
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed-dir", type=Path, default=DEFAULT_PROCESSED_DIR)
    parser.add_argument("--models-dir", type=Path, default=DEFAULT_MODELS_DIR)
    parser.add_argument("--metrics-path", type=Path, default=DEFAULT_METRICS_PATH)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()

    datasets = {
        "delay_features.csv": pd.read_csv(args.processed_dir / "delay_features.csv"),
        "cost_features.csv": pd.read_csv(args.processed_dir / "cost_features.csv"),
    }

    splits_by_dataset = {
        name: project_level_split(df, seed=args.seed) for name, df in datasets.items()
    }

    results = {}
    for task_key, cfg in TASKS.items():
        split = splits_by_dataset[cfg["dataset"]]
        print(f"\n=== {cfg['label']} ===")
        if cfg["task_type"] == "classification":
            task_result = run_classification_task(task_key, cfg, split, args.models_dir)
            print(f"  validation: baseline acc={task_result['validation']['baseline']['accuracy']:.3f} "
                  f"f1={task_result['validation']['baseline']['f1']:.3f} | "
                  f"logreg acc={task_result['validation']['logistic_regression']['accuracy']:.3f} "
                  f"f1={task_result['validation']['logistic_regression']['f1']:.3f} "
                  f"roc_auc={task_result['validation']['logistic_regression']['roc_auc']}")
            print(f"  test:       baseline acc={task_result['test']['baseline']['accuracy']:.3f} "
                  f"f1={task_result['test']['baseline']['f1']:.3f} | "
                  f"logreg acc={task_result['test']['logistic_regression']['accuracy']:.3f} "
                  f"f1={task_result['test']['logistic_regression']['f1']:.3f} "
                  f"roc_auc={task_result['test']['logistic_regression']['roc_auc']}")
        else:
            task_result = run_regression_task(task_key, cfg, split, args.models_dir)
            print(f"  validation: baseline_mean MAE={task_result['validation']['baseline_mean']['mae']:.2f} | "
                  f"linreg MAE={task_result['validation']['linear_regression']['mae']:.2f} "
                  f"R2={task_result['validation']['linear_regression']['r2']:.3f}")
            print(f"  test:       baseline_mean MAE={task_result['test']['baseline_mean']['mae']:.2f} | "
                  f"linreg MAE={task_result['test']['linear_regression']['mae']:.2f} "
                  f"R2={task_result['test']['linear_regression']['r2']:.3f}")
        results[task_key] = task_result

    run_metadata = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "seed": args.seed,
        "train_frac": DEFAULT_TRAIN_FRAC,
        "val_frac": DEFAULT_VAL_FRAC,
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "sklearn_version": sklearn.__version__,
        "pandas_version": pd.__version__,
        "numpy_version": np.__version__,
        "input_datasets": {
            name: str((args.processed_dir / name).resolve().relative_to(REPO_ROOT)) for name in datasets
        },
        "predictor_columns": PREDICTOR_COLUMNS,
        "n_predictor_columns": len(PREDICTOR_COLUMNS),
        "categorical_predictor_columns": CATEGORICAL_PREDICTORS,
        "split_metadata": {name: s.metadata for name, s in splits_by_dataset.items()},
        "preprocessing": {
            "numeric": "SimpleImputer(strategy='median') fit on train only, then StandardScaler() fit on train only",
            "categorical": "SimpleImputer(strategy='constant', fill_value='Unknown') then OneHotEncoder(handle_unknown='ignore'), both fit on train only",
            "fit_scope": "All preprocessing is fit exclusively inside each Pipeline's .fit(X_train, y_train) call; validation/test are only ever .transform()-ed.",
        },
        "hyperparameter_tuning": "none (Phase 4 scope excludes tuning)",
    }

    output = {"run_metadata": run_metadata, "tasks": results}
    args.metrics_path.parent.mkdir(parents=True, exist_ok=True)
    with open(args.metrics_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nWrote metrics to {args.metrics_path}")
    print(f"Wrote model artifacts to {args.models_dir}")


if __name__ == "__main__":
    main()
