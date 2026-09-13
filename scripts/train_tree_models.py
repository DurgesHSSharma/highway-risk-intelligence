"""
Phase 5: Random Forest + XGBoost models for the four highway project
prediction tasks, trained and evaluated on the IDENTICAL frozen Phase 4
project-level train/validation/test split (see scripts/data_split.py and
docs/TRAIN_VAL_TEST_STRATEGY.md). The split function is imported unchanged
from Phase 4 -- it is never reimplemented here.

Tasks (same four as Phase 4, same targets, same 45 predictors)
----------------------------------------------------------------
A. delay classification   -- target `significant_delay`      (RandomForestClassifier, XGBClassifier)
B. delay regression       -- target `final_delay_days`        (RandomForestRegressor, XGBRegressor)
C. cost classification    -- target `cost_overrun`            (RandomForestClassifier, XGBClassifier)
D. cost regression        -- target `final_cost_overrun_pct`  (RandomForestRegressor, XGBRegressor)

Design
------
- `TASKS`, `PREDICTOR_COLUMNS`, `build_preprocessor`, `classification_metrics`,
  `regression_metrics` are imported directly from Phase 4's
  `scripts/train_baseline_models.py` -- never redefined -- so preprocessing
  and metric definitions cannot silently drift between the baseline and tree
  models being compared.
- Light, deliberately small, EXPLICIT validation-only hyperparameter search
  (3 candidate configs per model family per task type -- see
  `RF_CLASSIFIER_CANDIDATES` etc. below). No grid/random search library is
  used. The test set is never touched until final evaluation of the one
  selected configuration per (task, model family).
- Selection rule (documented in docs/MODEL_COMPARISON_REPORT.md section
  "Hyperparameter tuning methodology"): among candidates whose validation
  score is within a small epsilon of the best validation score, the
  candidate with the smallest (train_metric - validation_metric) gap is
  selected -- i.e. ties are broken in favor of the less-overfit model
  rather than automatically taking the single highest validation score
  (Phase 5 brief section 10).
- Every final model's train/validation/test metrics are reported (never
  only validation/test) so overfitting is visible task-by-task.

Usage (from backend/.venv):
    ../backend/.venv/Scripts/python.exe train_tree_models.py
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
import xgboost
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.pipeline import Pipeline
from xgboost import XGBClassifier, XGBRegressor

from scripts.data_split import DEFAULT_SEED, DEFAULT_TRAIN_FRAC, DEFAULT_VAL_FRAC, project_level_split
from scripts.prepare_features import PREDICTOR_COLUMNS
from scripts.train_baseline_models import (
    CATEGORICAL_PREDICTORS,
    NUMERIC_PREDICTORS,
    TASKS,
    build_preprocessor,
    classification_metrics,
    regression_metrics,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROCESSED_DIR = REPO_ROOT / "data" / "processed"
DEFAULT_RF_DIR = REPO_ROOT / "models" / "random_forest"
DEFAULT_XGB_DIR = REPO_ROOT / "models" / "xgboost"
DEFAULT_METRICS_PATH = REPO_ROOT / "models" / "metrics" / "tree_metrics.json"
DEFAULT_BASELINE_METRICS_PATH = REPO_ROOT / "models" / "metrics" / "baseline_metrics.json"

RANDOM_STATE = DEFAULT_SEED

# Suspicious-performance warning thresholds (Phase 5 brief section 12).
CLASSIFICATION_AUC_WARNING = 0.95
REGRESSION_R2_WARNING = 0.85

# A model is flagged as overfit when its primary metric degrades by more
# than this amount from train to test (documented, not enforced blindly --
# see docs/MODEL_COMPARISON_REPORT.md "Overfitting analysis").
CLASSIFICATION_OVERFIT_GAP_THRESHOLD = 0.15  # ROC-AUC points
REGRESSION_OVERFIT_GAP_THRESHOLD = 0.15  # R^2 points

# Selection tolerance: candidates within this margin of the best validation
# score are treated as "practically tied"; among those, the candidate with
# the smallest train-vs-validation gap is preferred over the single highest
# validation score (Phase 5 brief section 10 -- avoid rewarding overfitting).
CLASSIFICATION_SELECTION_EPSILON = 0.005  # ROC-AUC points
REGRESSION_SELECTION_EPSILON = 0.01  # R^2 points

# --- Light, explicit, deliberately small validation-only search space -----
RF_CLASSIFIER_CANDIDATES = [
    {"n_estimators": 200, "max_depth": None, "min_samples_leaf": 1},
    {"n_estimators": 200, "max_depth": 8, "min_samples_leaf": 5},
    {"n_estimators": 400, "max_depth": None, "min_samples_leaf": 5},
]
RF_REGRESSOR_CANDIDATES = [
    {"n_estimators": 200, "max_depth": None, "min_samples_leaf": 1},
    {"n_estimators": 200, "max_depth": 8, "min_samples_leaf": 5},
    {"n_estimators": 400, "max_depth": None, "min_samples_leaf": 5},
]
XGB_CLASSIFIER_CANDIDATES = [
    {"n_estimators": 200, "max_depth": 3, "learning_rate": 0.1},
    {"n_estimators": 200, "max_depth": 5, "learning_rate": 0.05},
    {"n_estimators": 400, "max_depth": 3, "learning_rate": 0.05},
]
XGB_REGRESSOR_CANDIDATES = [
    {"n_estimators": 200, "max_depth": 3, "learning_rate": 0.1},
    {"n_estimators": 200, "max_depth": 5, "learning_rate": 0.05},
    {"n_estimators": 400, "max_depth": 3, "learning_rate": 0.05},
]


def make_estimator(model_family: str, task_type: str, config: dict):
    """Construct a fresh, fixed-seed estimator. Never mutates `config`."""
    if model_family == "random_forest":
        cls = RandomForestClassifier if task_type == "classification" else RandomForestRegressor
        return cls(random_state=RANDOM_STATE, n_jobs=-1, **config)
    if model_family == "xgboost":
        if task_type == "classification":
            return XGBClassifier(random_state=RANDOM_STATE, n_jobs=-1, eval_metric="logloss", **config)
        return XGBRegressor(random_state=RANDOM_STATE, n_jobs=-1, **config)
    raise ValueError(f"Unknown model_family: {model_family}")


def primary_metric_key(task_type: str) -> str:
    return "roc_auc" if task_type == "classification" else "r2"


def score_pipeline(pipeline: Pipeline, task_type: str, X: pd.DataFrame, y: pd.Series) -> dict:
    if task_type == "classification":
        pred = pipeline.predict(X)
        score = pipeline.predict_proba(X)[:, 1]
        return classification_metrics(y, pred, score)
    pred = pipeline.predict(X)
    return regression_metrics(y, pred)


def tune_and_select(
    model_family: str,
    task_type: str,
    candidates: list[dict],
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_val: pd.DataFrame,
    y_val: pd.Series,
) -> tuple[dict, list[dict]]:
    """Fit every candidate on TRAIN only, score on TRAIN and VALIDATION only
    (test is never touched here), and select one configuration.

    Returns (selected_trial, all_trials). `selected_trial["pipeline"]` is the
    already-fitted Pipeline for the chosen configuration -- it is reused for
    final evaluation rather than refit, so results are exactly reproducible
    from this one fit.
    """
    metric_key = primary_metric_key(task_type)
    epsilon = CLASSIFICATION_SELECTION_EPSILON if task_type == "classification" else REGRESSION_SELECTION_EPSILON

    trials = []
    for config in candidates:
        pipeline = Pipeline([
            ("preprocess", build_preprocessor()),
            ("model", make_estimator(model_family, task_type, config)),
        ])
        pipeline.fit(X_train, y_train)
        train_metrics = score_pipeline(pipeline, task_type, X_train, y_train)
        val_metrics = score_pipeline(pipeline, task_type, X_val, y_val)
        trials.append({
            "config": config,
            "train_metric": train_metrics[metric_key],
            "validation_metric": val_metrics[metric_key],
            "train_minus_validation_gap": train_metrics[metric_key] - val_metrics[metric_key],
            "pipeline": pipeline,
        })

    best_val = max(t["validation_metric"] for t in trials)
    near_best = [t for t in trials if best_val - t["validation_metric"] <= epsilon]
    selected = min(
        near_best,
        key=lambda t: (t["train_minus_validation_gap"], t["config"].get("n_estimators", 0)),
    )
    return selected, trials


def feature_importance_ranking(pipeline: Pipeline) -> list[dict]:
    preprocessor = pipeline.named_steps["preprocess"]
    model = pipeline.named_steps["model"]
    names = preprocessor.get_feature_names_out()
    importances = model.feature_importances_
    order = np.argsort(importances)[::-1]
    return [{"feature": str(names[i]), "importance": float(importances[i])} for i in order]


def diagnose_delay_regression_cohorts(split) -> dict:
    """Exploratory-only diagnostic (Phase 5 brief section 13): compare
    train/validation/test cohort composition for the delay-regression task
    to see whether the Phase 4 test-R^2-below-validation-R^2 gap lines up
    with an obvious cohort-composition difference. Does NOT change the
    split or feed back into model selection in any way."""
    diag = {}
    for name, df in [("train", split.train), ("validation", split.validation), ("test", split.test)]:
        per_project = df.drop_duplicates("project_id")
        target_per_project = df.groupby("project_id")["final_delay_days"].first()
        diag[name] = {
            "n_projects": int(per_project["project_id"].nunique()),
            "project_type_distribution": {
                str(k): float(v) for k, v in per_project["project_type"].value_counts(normalize=True).round(4).items()
            },
            "state_distribution_top5": {
                str(k): float(v) for k, v in per_project["state"].value_counts(normalize=True).round(4).head(5).items()
            },
            "project_length_km_mean": float(per_project["project_length_km"].mean()),
            "project_length_km_std": float(per_project["project_length_km"].std()),
            "original_contract_value_inr_cr_mean": float(per_project["original_contract_value_inr_cr"].mean()),
            "original_contract_value_inr_cr_std": float(per_project["original_contract_value_inr_cr"].std()),
            "final_delay_days_mean": float(target_per_project.mean()),
            "final_delay_days_std": float(target_per_project.std()),
            "final_delay_days_median": float(target_per_project.median()),
        }
    return diag


def run_task(task_key: str, cfg: dict, split, rf_dir: Path, xgb_dir: Path) -> dict:
    target = cfg["target"]
    task_type = cfg["task_type"]
    X_train, y_train = split.train[PREDICTOR_COLUMNS], split.train[target]
    X_val, y_val = split.validation[PREDICTOR_COLUMNS], split.validation[target]
    X_test, y_test = split.test[PREDICTOR_COLUMNS], split.test[target]

    result: dict = {
        "task_type": task_type,
        "label": cfg["label"],
        "target": target,
        "n_train_rows": len(X_train),
        "n_validation_rows": len(X_val),
        "n_test_rows": len(X_test),
        "models": {},
    }
    metric_key = primary_metric_key(task_type)
    overfit_threshold = (
        CLASSIFICATION_OVERFIT_GAP_THRESHOLD if task_type == "classification" else REGRESSION_OVERFIT_GAP_THRESHOLD
    )
    auc_or_r2_warning = CLASSIFICATION_AUC_WARNING if task_type == "classification" else REGRESSION_R2_WARNING

    families = [
        ("random_forest", rf_dir, RF_CLASSIFIER_CANDIDATES if task_type == "classification" else RF_REGRESSOR_CANDIDATES),
        ("xgboost", xgb_dir, XGB_CLASSIFIER_CANDIDATES if task_type == "classification" else XGB_REGRESSOR_CANDIDATES),
    ]
    for model_family, dirpath, candidates in families:
        selected, trials = tune_and_select(model_family, task_type, candidates, X_train, y_train, X_val, y_val)
        pipeline = selected["pipeline"]

        dirpath.mkdir(parents=True, exist_ok=True)
        artifact_path = dirpath / f"{task_key}_{model_family}.joblib"
        joblib.dump(pipeline, artifact_path)

        train_scores = score_pipeline(pipeline, task_type, X_train, y_train)
        val_scores = score_pipeline(pipeline, task_type, X_val, y_val)
        test_scores = score_pipeline(pipeline, task_type, X_test, y_test)

        overfit_gap = train_scores[metric_key] - test_scores[metric_key]
        suspicious = (val_scores.get(metric_key) or 0) > auc_or_r2_warning or (test_scores.get(metric_key) or 0) > auc_or_r2_warning

        result["models"][model_family] = {
            "selection_metric": metric_key,
            "selection_epsilon": CLASSIFICATION_SELECTION_EPSILON if task_type == "classification" else REGRESSION_SELECTION_EPSILON,
            "selected_config": selected["config"],
            "candidates_tried": [
                {
                    "config": t["config"],
                    "train_metric": t["train_metric"],
                    "validation_metric": t["validation_metric"],
                    "train_minus_validation_gap": t["train_minus_validation_gap"],
                }
                for t in trials
            ],
            "artifact_path": str(artifact_path.relative_to(REPO_ROOT)),
            "train": train_scores,
            "validation": val_scores,
            "test": test_scores,
            "overfitting_gap_train_minus_test": overfit_gap,
            "overfitting_flag": bool(overfit_gap > overfit_threshold),
            "suspicious_performance_flag": bool(suspicious),
            "top_feature_importances": feature_importance_ranking(pipeline)[:10],
        }

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed-dir", type=Path, default=DEFAULT_PROCESSED_DIR)
    parser.add_argument("--rf-dir", type=Path, default=DEFAULT_RF_DIR)
    parser.add_argument("--xgb-dir", type=Path, default=DEFAULT_XGB_DIR)
    parser.add_argument("--metrics-path", type=Path, default=DEFAULT_METRICS_PATH)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()

    datasets = {
        "delay_features.csv": pd.read_csv(args.processed_dir / "delay_features.csv"),
        "cost_features.csv": pd.read_csv(args.processed_dir / "cost_features.csv"),
    }
    splits_by_dataset = {name: project_level_split(df, seed=args.seed) for name, df in datasets.items()}

    results = {}
    for task_key, cfg in TASKS.items():
        split = splits_by_dataset[cfg["dataset"]]
        print(f"\n=== {cfg['label']} ===")
        task_result = run_task(task_key, cfg, split, args.rf_dir, args.xgb_dir)
        for model_family in ("random_forest", "xgboost"):
            m = task_result["models"][model_family]
            metric_key = m["selection_metric"]
            print(
                f"  {model_family:14s} config={m['selected_config']} | "
                f"train {metric_key}={m['train'][metric_key]:.4f} "
                f"val {metric_key}={m['validation'][metric_key]:.4f} "
                f"test {metric_key}={m['test'][metric_key]:.4f} "
                f"overfit_flag={m['overfitting_flag']} suspicious={m['suspicious_performance_flag']}"
            )
        results[task_key] = task_result

    delay_split = splits_by_dataset["delay_features.csv"]
    delay_regression_cohort_diagnostic = diagnose_delay_regression_cohorts(delay_split)

    baseline_metrics = None
    if DEFAULT_BASELINE_METRICS_PATH.exists():
        with open(DEFAULT_BASELINE_METRICS_PATH) as f:
            baseline_metrics = json.load(f)

    run_metadata = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "seed": args.seed,
        "train_frac": DEFAULT_TRAIN_FRAC,
        "val_frac": DEFAULT_VAL_FRAC,
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "sklearn_version": sklearn.__version__,
        "xgboost_version": xgboost.__version__,
        "pandas_version": pd.__version__,
        "numpy_version": np.__version__,
        "input_datasets": {name: str((args.processed_dir / name).resolve().relative_to(REPO_ROOT)) for name in datasets},
        "predictor_columns": PREDICTOR_COLUMNS,
        "n_predictor_columns": len(PREDICTOR_COLUMNS),
        "numeric_predictor_columns": NUMERIC_PREDICTORS,
        "categorical_predictor_columns": CATEGORICAL_PREDICTORS,
        "split_metadata": {name: s.metadata for name, s in splits_by_dataset.items()},
        "preprocessing": {
            "numeric": "SimpleImputer(strategy='median') fit on train only, then StandardScaler() fit on train only",
            "categorical": "SimpleImputer(strategy='constant', fill_value='Unknown') then OneHotEncoder(handle_unknown='ignore'), both fit on train only",
            "fit_scope": "All preprocessing is fit exclusively inside each Pipeline's .fit(X_train, y_train) call; validation/test are only ever .transform()-ed.",
            "note": "Identical ColumnTransformer definition (scripts.train_baseline_models.build_preprocessor) reused unchanged from Phase 4.",
        },
        "hyperparameter_tuning": {
            "method": "small explicit validation-only candidate list (no grid/random search library)",
            "n_candidates_per_model_family": 3,
            "selection_rule": (
                "Among candidates whose validation score is within "
                f"{CLASSIFICATION_SELECTION_EPSILON} (classification, ROC-AUC) / "
                f"{REGRESSION_SELECTION_EPSILON} (regression, R^2) of the best validation "
                "score, the candidate with the smallest (train_metric - validation_metric) "
                "gap is selected -- ties broken toward fewer n_estimators. Test data was "
                "never used in this selection."
            ),
            "candidate_configs": {
                "random_forest_classifier": RF_CLASSIFIER_CANDIDATES,
                "random_forest_regressor": RF_REGRESSOR_CANDIDATES,
                "xgboost_classifier": XGB_CLASSIFIER_CANDIDATES,
                "xgboost_regressor": XGB_REGRESSOR_CANDIDATES,
            },
        },
        "suspicious_performance_thresholds": {
            "classification_roc_auc": CLASSIFICATION_AUC_WARNING,
            "regression_r2": REGRESSION_R2_WARNING,
        },
        "overfitting_gap_thresholds": {
            "classification_roc_auc_train_minus_test": CLASSIFICATION_OVERFIT_GAP_THRESHOLD,
            "regression_r2_train_minus_test": REGRESSION_OVERFIT_GAP_THRESHOLD,
        },
        "reproducibility": {
            "seed": RANDOM_STATE,
            "note": (
                "RandomForest(n_jobs=-1) and XGBoost(n_jobs=-1) are deterministic given a "
                "fixed random_state/seed on a fixed dataset in this environment (scikit-learn "
                "derives per-tree seeds from random_state independent of thread scheduling; "
                "XGBoost's histogram tree method with a fixed seed is deterministic on a "
                "single machine/run). Exact bit-for-bit floating point equality across "
                "different machines/library versions is not guaranteed; this repo's "
                "reproducibility test (tests/test_train_tree_models.py) tolerates the "
                "differences that can arise from parallel floating-point summation order by "
                "asserting metric equality to 1e-9, not raw prediction array equality."
            ),
        },
        "baseline_comparison_source": (
            str(DEFAULT_BASELINE_METRICS_PATH.relative_to(REPO_ROOT)) if baseline_metrics else None
        ),
    }

    output = {
        "run_metadata": run_metadata,
        "tasks": results,
        "delay_regression_cohort_diagnostic": delay_regression_cohort_diagnostic,
    }
    args.metrics_path.parent.mkdir(parents=True, exist_ok=True)
    with open(args.metrics_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nWrote metrics to {args.metrics_path}")
    print(f"Wrote Random Forest artifacts to {args.rf_dir}")
    print(f"Wrote XGBoost artifacts to {args.xgb_dir}")


if __name__ == "__main__":
    main()
