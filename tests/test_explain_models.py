from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import shap
from sklearn.pipeline import Pipeline

from scripts.data_split import project_level_split
from scripts.generate_dataset import generate_dataset
from scripts.prepare_features import PREDICTOR_COLUMNS, build_feature_table
from scripts.train_baseline_models import build_preprocessor
from scripts.train_tree_models import make_estimator
from scripts.explain_models import build_explanation, top_contributions, transform

SMALL_N = 40


@pytest.fixture(scope="module")
def raw_df() -> pd.DataFrame:
    return generate_dataset(n_projects=SMALL_N, seed=321)


@pytest.fixture(scope="module")
def raw_csv_path(tmp_path_factory, raw_df: pd.DataFrame) -> Path:
    path = tmp_path_factory.mktemp("explain_raw") / "raw.csv"
    raw_df.to_csv(path, index=False)
    return path


@pytest.fixture(scope="module")
def features(raw_df: pd.DataFrame) -> pd.DataFrame:
    return build_feature_table(raw_df)


@pytest.fixture(scope="module")
def split(features: pd.DataFrame, raw_csv_path: Path):
    return project_level_split(features, raw_path=raw_csv_path)


@pytest.fixture(scope="module")
def rf_classifier_pipeline(split):
    X_train, y_train = split.train[PREDICTOR_COLUMNS], split.train["significant_delay"]
    pipeline = Pipeline([
        ("preprocess", build_preprocessor()),
        ("model", make_estimator("random_forest", "classification", {"n_estimators": 50, "max_depth": 5, "min_samples_leaf": 2})),
    ])
    pipeline.fit(X_train, y_train)
    return pipeline


@pytest.fixture(scope="module")
def xgb_regressor_pipeline(split):
    X_train, y_train = split.train[PREDICTOR_COLUMNS], split.train["final_delay_days"]
    pipeline = Pipeline([
        ("preprocess", build_preprocessor()),
        ("model", make_estimator("xgboost", "regression", {"n_estimators": 50, "max_depth": 3, "learning_rate": 0.1})),
    ])
    pipeline.fit(X_train, y_train)
    return pipeline


def test_shap_tree_explainer_runs_for_random_forest_classifier(split, rf_classifier_pipeline) -> None:
    X_test = split.test[PREDICTOR_COLUMNS]
    Xt, feature_names = transform(rf_classifier_pipeline, X_test)
    explanation = build_explanation(rf_classifier_pipeline, "random_forest", "classification", Xt[:10], feature_names)
    assert explanation.values.shape == (10, len(feature_names))


def test_shap_tree_explainer_runs_for_xgboost_regressor(split, xgb_regressor_pipeline) -> None:
    X_test = split.test[PREDICTOR_COLUMNS]
    Xt, feature_names = transform(xgb_regressor_pipeline, X_test)
    explanation = build_explanation(xgb_regressor_pipeline, "xgboost", "regression", Xt[:10], feature_names)
    assert explanation.values.shape == (10, len(feature_names))


def test_shap_produces_one_attribution_per_feature_per_instance(split, rf_classifier_pipeline) -> None:
    X_test = split.test[PREDICTOR_COLUMNS]
    Xt, feature_names = transform(rf_classifier_pipeline, X_test)
    explanation = build_explanation(rf_classifier_pipeline, "random_forest", "classification", Xt[:5], feature_names)
    assert explanation.values.shape[0] == 5
    assert explanation.values.shape[1] == len(feature_names) == Xt.shape[1]
    for row in range(5):
        assert explanation.values[row].shape == (len(feature_names),)
        assert np.isfinite(explanation.values[row]).all()


def test_shap_local_additivity_matches_model_output(split, xgb_regressor_pipeline) -> None:
    """SHAP's core guarantee: base_value + sum(shap_values) == model output
    for that instance (within floating-point tolerance)."""
    X_test = split.test[PREDICTOR_COLUMNS].reset_index(drop=True)
    Xt, feature_names = transform(xgb_regressor_pipeline, X_test)
    explanation = build_explanation(xgb_regressor_pipeline, "xgboost", "regression", Xt[:5], feature_names)
    model = xgb_regressor_pipeline.named_steps["model"]
    raw_predictions = model.predict(Xt[:5])
    for row in range(5):
        reconstructed = explanation.base_values[row] + explanation.values[row].sum()
        assert reconstructed == pytest.approx(raw_predictions[row], abs=1e-2)


def test_top_contributions_summary_is_consistent(split, xgb_regressor_pipeline) -> None:
    X_test = split.test[PREDICTOR_COLUMNS]
    Xt, feature_names = transform(xgb_regressor_pipeline, X_test)
    explanation = build_explanation(xgb_regressor_pipeline, "xgboost", "regression", Xt[:3], feature_names)
    summary = top_contributions(explanation[0], k=5)
    assert "pushed_prediction_up" in summary
    assert "pushed_prediction_down" in summary
    for item in summary["pushed_prediction_up"]:
        assert item["shap_value"] > 0
    for item in summary["pushed_prediction_down"]:
        assert item["shap_value"] < 0
    assert summary["final_output"] == pytest.approx(summary["base_value"] + explanation[0].values.sum(), abs=1e-6)
