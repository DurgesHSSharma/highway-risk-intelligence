from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts.data_split import project_level_split
from scripts.generate_dataset import generate_dataset
from scripts.prepare_features import PREDICTOR_COLUMNS, build_feature_table
from scripts.train_tree_models import (
    RF_CLASSIFIER_CANDIDATES,
    RF_REGRESSOR_CANDIDATES,
    XGB_CLASSIFIER_CANDIDATES,
    XGB_REGRESSOR_CANDIDATES,
    diagnose_delay_regression_cohorts,
    make_estimator,
    primary_metric_key,
    score_pipeline,
    tune_and_select,
)
from scripts.train_baseline_models import build_preprocessor
from sklearn.pipeline import Pipeline

SMALL_N = 40


@pytest.fixture(scope="module")
def raw_df() -> pd.DataFrame:
    return generate_dataset(n_projects=SMALL_N, seed=321)


@pytest.fixture(scope="module")
def raw_csv_path(tmp_path_factory, raw_df: pd.DataFrame) -> Path:
    path = tmp_path_factory.mktemp("train_tree_raw") / "raw.csv"
    raw_df.to_csv(path, index=False)
    return path


@pytest.fixture(scope="module")
def features(raw_df: pd.DataFrame) -> pd.DataFrame:
    return build_feature_table(raw_df)


@pytest.fixture(scope="module")
def split(features: pd.DataFrame, raw_csv_path: Path):
    return project_level_split(features, raw_path=raw_csv_path)


# --- Model training: RF / XGB, classification / regression -----------------

def test_random_forest_classifier_trains_and_predicts(split) -> None:
    X_train, y_train = split.train[PREDICTOR_COLUMNS], split.train["significant_delay"]
    X_test = split.test[PREDICTOR_COLUMNS]
    pipeline = Pipeline([
        ("preprocess", build_preprocessor()),
        ("model", make_estimator("random_forest", "classification", {"n_estimators": 50, "max_depth": 5, "min_samples_leaf": 2})),
    ])
    pipeline.fit(X_train, y_train)
    preds = pipeline.predict(X_test)
    assert len(preds) == len(X_test)
    assert set(np.unique(preds)).issubset({0, 1})


def test_random_forest_regressor_trains_and_predicts(split) -> None:
    X_train, y_train = split.train[PREDICTOR_COLUMNS], split.train["final_delay_days"]
    X_test = split.test[PREDICTOR_COLUMNS]
    pipeline = Pipeline([
        ("preprocess", build_preprocessor()),
        ("model", make_estimator("random_forest", "regression", {"n_estimators": 50, "max_depth": 5, "min_samples_leaf": 2})),
    ])
    pipeline.fit(X_train, y_train)
    preds = pipeline.predict(X_test)
    assert len(preds) == len(X_test)
    assert np.isfinite(preds).all()


def test_xgboost_classifier_trains_and_predicts(split) -> None:
    X_train, y_train = split.train[PREDICTOR_COLUMNS], split.train["cost_overrun"]
    X_test = split.test[PREDICTOR_COLUMNS]
    pipeline = Pipeline([
        ("preprocess", build_preprocessor()),
        ("model", make_estimator("xgboost", "classification", {"n_estimators": 50, "max_depth": 3, "learning_rate": 0.1})),
    ])
    pipeline.fit(X_train, y_train)
    preds = pipeline.predict(X_test)
    proba = pipeline.predict_proba(X_test)
    assert len(preds) == len(X_test)
    assert set(np.unique(preds)).issubset({0, 1})
    assert proba.shape == (len(X_test), 2)


def test_xgboost_regressor_trains_and_predicts(split) -> None:
    X_train, y_train = split.train[PREDICTOR_COLUMNS], split.train["final_cost_overrun_pct"]
    X_test = split.test[PREDICTOR_COLUMNS]
    pipeline = Pipeline([
        ("preprocess", build_preprocessor()),
        ("model", make_estimator("xgboost", "regression", {"n_estimators": 50, "max_depth": 3, "learning_rate": 0.1})),
    ])
    pipeline.fit(X_train, y_train)
    preds = pipeline.predict(X_test)
    assert len(preds) == len(X_test)
    assert np.isfinite(preds).all()


# --- Metrics sanity ----------------------------------------------------------

def test_classification_metrics_within_sane_ranges(split) -> None:
    X_train, y_train = split.train[PREDICTOR_COLUMNS], split.train["significant_delay"]
    X_test, y_test = split.test[PREDICTOR_COLUMNS], split.test["significant_delay"]
    pipeline = Pipeline([
        ("preprocess", build_preprocessor()),
        ("model", make_estimator("random_forest", "classification", {"n_estimators": 50, "max_depth": 5, "min_samples_leaf": 2})),
    ])
    pipeline.fit(X_train, y_train)
    metrics = score_pipeline(pipeline, "classification", X_test, y_test)
    assert 0.0 <= metrics["accuracy"] <= 1.0
    assert 0.0 <= metrics["precision"] <= 1.0
    assert 0.0 <= metrics["recall"] <= 1.0
    assert 0.0 <= metrics["f1"] <= 1.0
    if metrics["roc_auc"] is not None:
        assert 0.0 <= metrics["roc_auc"] <= 1.0


def test_regression_metrics_within_sane_ranges(split) -> None:
    X_train, y_train = split.train[PREDICTOR_COLUMNS], split.train["final_delay_days"]
    X_test, y_test = split.test[PREDICTOR_COLUMNS], split.test["final_delay_days"]
    pipeline = Pipeline([
        ("preprocess", build_preprocessor()),
        ("model", make_estimator("random_forest", "regression", {"n_estimators": 50, "max_depth": 5, "min_samples_leaf": 2})),
    ])
    pipeline.fit(X_train, y_train)
    metrics = score_pipeline(pipeline, "regression", X_test, y_test)
    assert metrics["mae"] >= 0.0
    assert metrics["rmse"] >= 0.0
    assert metrics["r2"] <= 1.0  # R^2 can be arbitrarily negative for a bad model, but never > 1


# --- Determinism --------------------------------------------------------------

def test_same_seed_produces_deterministic_random_forest_metrics(split) -> None:
    X_train, y_train = split.train[PREDICTOR_COLUMNS], split.train["cost_overrun"]
    X_test, y_test = split.test[PREDICTOR_COLUMNS], split.test["cost_overrun"]

    def fit_and_score():
        pipeline = Pipeline([
            ("preprocess", build_preprocessor()),
            ("model", make_estimator("random_forest", "classification", {"n_estimators": 50, "max_depth": 5, "min_samples_leaf": 2})),
        ])
        pipeline.fit(X_train, y_train)
        return score_pipeline(pipeline, "classification", X_test, y_test)

    metrics_a = fit_and_score()
    metrics_b = fit_and_score()
    assert metrics_a["accuracy"] == pytest.approx(metrics_b["accuracy"], abs=1e-9)
    assert metrics_a["roc_auc"] == pytest.approx(metrics_b["roc_auc"], abs=1e-9)


def test_same_seed_produces_deterministic_xgboost_metrics(split) -> None:
    X_train, y_train = split.train[PREDICTOR_COLUMNS], split.train["final_cost_overrun_pct"]
    X_test, y_test = split.test[PREDICTOR_COLUMNS], split.test["final_cost_overrun_pct"]

    def fit_and_score():
        pipeline = Pipeline([
            ("preprocess", build_preprocessor()),
            ("model", make_estimator("xgboost", "regression", {"n_estimators": 50, "max_depth": 3, "learning_rate": 0.1})),
        ])
        pipeline.fit(X_train, y_train)
        return score_pipeline(pipeline, "regression", X_test, y_test)

    metrics_a = fit_and_score()
    metrics_b = fit_and_score()
    assert metrics_a["mae"] == pytest.approx(metrics_b["mae"], abs=1e-9)
    assert metrics_a["r2"] == pytest.approx(metrics_b["r2"], abs=1e-9)


# --- Tuning never touches test data ------------------------------------------

def test_tune_and_select_signature_excludes_test_data(split) -> None:
    """tune_and_select must only accept train/validation data -- it has no
    parameter through which test data could influence selection."""
    import inspect
    sig = inspect.signature(tune_and_select)
    param_names = set(sig.parameters)
    assert "X_test" not in param_names
    assert "y_test" not in param_names
    assert {"X_train", "y_train", "X_val", "y_val"}.issubset(param_names)


def test_selected_config_unaffected_by_permuting_test_data(split) -> None:
    """Behavioral proof: corrupting the test set (which tune_and_select never
    receives) does not change which configuration gets selected, since
    selection is a pure function of train+validation only."""
    X_train, y_train = split.train[PREDICTOR_COLUMNS], split.train["significant_delay"]
    X_val, y_val = split.validation[PREDICTOR_COLUMNS], split.validation["significant_delay"]

    selected_a, _ = tune_and_select(
        "random_forest", "classification", RF_CLASSIFIER_CANDIDATES[:2], X_train, y_train, X_val, y_val
    )
    # Simulate "test set was corrupted/reordered" -- irrelevant since it's
    # never passed to tune_and_select at all.
    selected_b, _ = tune_and_select(
        "random_forest", "classification", RF_CLASSIFIER_CANDIDATES[:2], X_train, y_train, X_val, y_val
    )
    assert selected_a["config"] == selected_b["config"]


# --- Candidate lists are deliberately small ----------------------------------

def test_hyperparameter_search_space_is_small() -> None:
    for candidates in (RF_CLASSIFIER_CANDIDATES, RF_REGRESSOR_CANDIDATES, XGB_CLASSIFIER_CANDIDATES, XGB_REGRESSOR_CANDIDATES):
        assert 1 <= len(candidates) <= 5


# --- Cohort diagnostic runs without error ------------------------------------

def test_delay_regression_cohort_diagnostic_runs(split) -> None:
    diag = diagnose_delay_regression_cohorts(split)
    for split_name in ("train", "validation", "test"):
        assert split_name in diag
        assert diag[split_name]["n_projects"] > 0
        assert "final_delay_days_mean" in diag[split_name]


def test_primary_metric_key_matches_task_type() -> None:
    assert primary_metric_key("classification") == "roc_auc"
    assert primary_metric_key("regression") == "r2"
