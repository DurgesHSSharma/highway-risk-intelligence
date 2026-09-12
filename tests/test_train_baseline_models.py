from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.pipeline import Pipeline

from scripts.data_split import project_level_split
from scripts.generate_dataset import generate_dataset
from scripts.prepare_features import (
    COST_TARGETS,
    DELAY_TARGETS,
    FLAG_COLUMNS,
    IDENTIFIER_COLUMNS,
    PREDICTOR_COLUMNS,
    build_feature_table,
)
from scripts.train_baseline_models import (
    CATEGORICAL_PREDICTORS,
    NUMERIC_PREDICTORS,
    build_preprocessor,
    classification_metrics,
    regression_metrics,
)

SMALL_N = 40


@pytest.fixture(scope="module")
def raw_df() -> pd.DataFrame:
    return generate_dataset(n_projects=SMALL_N, seed=321)


@pytest.fixture(scope="module")
def raw_csv_path(tmp_path_factory, raw_df: pd.DataFrame) -> Path:
    path = tmp_path_factory.mktemp("train_baseline_raw") / "raw.csv"
    raw_df.to_csv(path, index=False)
    return path


@pytest.fixture(scope="module")
def features(raw_df: pd.DataFrame) -> pd.DataFrame:
    return build_feature_table(raw_df)


@pytest.fixture(scope="module")
def split(features: pd.DataFrame, raw_csv_path: Path):
    return project_level_split(features, raw_path=raw_csv_path)


# --- Feature/target separation (Phase 4 brief section 10) ---------------

def test_targets_never_appear_in_predictor_columns() -> None:
    for target in DELAY_TARGETS + COST_TARGETS:
        assert target not in PREDICTOR_COLUMNS


def test_project_id_excluded_from_predictor_columns() -> None:
    assert "project_id" not in PREDICTOR_COLUMNS
    assert "project_id" in IDENTIFIER_COLUMNS


def test_is_terminal_snapshot_excluded_from_predictor_columns() -> None:
    assert "is_terminal_snapshot" not in PREDICTOR_COLUMNS
    assert "is_terminal_snapshot" in FLAG_COLUMNS


def test_reporting_month_excluded_from_predictor_columns() -> None:
    assert "reporting_month" not in PREDICTOR_COLUMNS


def test_numeric_and_categorical_predictors_partition_predictor_columns() -> None:
    assert set(NUMERIC_PREDICTORS) | set(CATEGORICAL_PREDICTORS) == set(PREDICTOR_COLUMNS)
    assert set(NUMERIC_PREDICTORS) & set(CATEGORICAL_PREDICTORS) == set()


# --- Preprocessing ---------------------------------------------------------

def test_preprocessing_handles_missing_numerical_values() -> None:
    df = pd.DataFrame({
        "project_length_km": [10.0, np.nan, 30.0, 40.0],
        "state": ["Bihar", "Kerala", "Bihar", "Kerala"],
    })
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline as SkPipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    ct = ColumnTransformer([
        ("numeric", SkPipeline([("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]), ["project_length_km"]),
        ("categorical", SkPipeline([("impute", SimpleImputer(strategy="constant", fill_value="Unknown")), ("encode", OneHotEncoder(handle_unknown="ignore"))]), ["state"]),
    ])
    transformed = ct.fit_transform(df)
    assert not np.isnan(transformed).any()


def test_preprocessing_handles_categorical_missing_and_values() -> None:
    df = pd.DataFrame({
        "project_length_km": [10.0, 20.0, 30.0, 40.0],
        "state": ["Bihar", None, "Kerala", "Bihar"],
    })
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline as SkPipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    ct = ColumnTransformer([
        ("numeric", SkPipeline([("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]), ["project_length_km"]),
        ("categorical", SkPipeline([("impute", SimpleImputer(strategy="constant", fill_value="Unknown")), ("encode", OneHotEncoder(handle_unknown="ignore"))]), ["state"]),
    ])
    transformed = ct.fit_transform(df)
    assert transformed.shape[0] == 4
    assert not np.isnan(transformed).any()


def test_unseen_categorical_value_does_not_crash_transform() -> None:
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline as SkPipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    train_df = pd.DataFrame({"project_length_km": [10.0, 20.0, 30.0], "state": ["Bihar", "Kerala", "Bihar"]})
    test_df = pd.DataFrame({"project_length_km": [15.0], "state": ["Rajasthan"]})  # unseen category

    ct = ColumnTransformer([
        ("numeric", SkPipeline([("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]), ["project_length_km"]),
        ("categorical", SkPipeline([("impute", SimpleImputer(strategy="constant", fill_value="Unknown")), ("encode", OneHotEncoder(handle_unknown="ignore"))]), ["state"]),
    ])
    ct.fit(train_df)
    transformed = ct.transform(test_df)  # must not raise
    assert transformed.shape[0] == 1
    # the categorical block for the unseen "Rajasthan" should be all-zero (ignored)
    n_numeric = 1
    categorical_block = transformed[0, n_numeric:]
    assert np.allclose(categorical_block, 0.0)


def test_preprocessing_fit_parameters_come_only_from_training_data(features: pd.DataFrame, raw_csv_path: Path) -> None:
    """Fit preprocessing on two datasets that are identical in the training
    rows but differ (with an injected extreme value) only in validation
    rows, and assert the fitted imputer/scaler statistics are identical --
    proving they were learned exclusively from the training split."""
    split_a = project_level_split(features, raw_path=raw_csv_path)

    features_b = features.copy()
    val_project = split_a.validation["project_id"].iloc[0]
    mask = (features_b["project_id"] == val_project) & (~features_b["is_terminal_snapshot"])
    features_b.loc[mask, "project_length_km"] = 999_999.0
    features_b.loc[mask, "state"] = "TotallyMadeUpState"
    split_b = project_level_split(features_b, raw_path=raw_csv_path)

    pd.testing.assert_frame_equal(split_a.train, split_b.train)

    prep_a = build_preprocessor()
    prep_a.fit(split_a.train[PREDICTOR_COLUMNS])
    prep_b = build_preprocessor()
    prep_b.fit(split_b.train[PREDICTOR_COLUMNS])

    imputer_a = prep_a.named_transformers_["numeric"].named_steps["impute"]
    imputer_b = prep_b.named_transformers_["numeric"].named_steps["impute"]
    np.testing.assert_array_equal(imputer_a.statistics_, imputer_b.statistics_)

    scaler_a = prep_a.named_transformers_["numeric"].named_steps["scale"]
    scaler_b = prep_b.named_transformers_["numeric"].named_steps["scale"]
    np.testing.assert_array_equal(scaler_a.mean_, scaler_b.mean_)
    np.testing.assert_array_equal(scaler_a.scale_, scaler_b.scale_)

    encoder_a = prep_a.named_transformers_["categorical"].named_steps["encode"]
    encoder_b = prep_b.named_transformers_["categorical"].named_steps["encode"]
    for cats_a, cats_b in zip(encoder_a.categories_, encoder_b.categories_):
        assert list(cats_a) == list(cats_b)
    assert "TotallyMadeUpState" not in encoder_a.categories_[CATEGORICAL_PREDICTORS.index("state")]


# --- Baseline metric correctness -------------------------------------------

def test_dummy_classifier_baseline_accuracy_is_mathematically_correct() -> None:
    y_train = pd.Series([0, 0, 0, 1, 1])  # majority class 0
    y_test = pd.Series([0, 0, 1, 1, 1])
    X_train = pd.DataFrame({"x": range(5)})
    X_test = pd.DataFrame({"x": range(5)})

    dummy = DummyClassifier(strategy="most_frequent", random_state=42)
    dummy.fit(X_train, y_train)
    pred = dummy.predict(X_test)
    score = dummy.predict_proba(X_test)[:, 1]

    expected_accuracy = (y_test == 0).mean()  # dummy always predicts 0
    metrics = classification_metrics(y_test, pred, score)
    assert metrics["accuracy"] == pytest.approx(expected_accuracy)
    assert metrics["precision"] == 0.0  # never predicts positive class
    assert metrics["recall"] == 0.0


def test_dummy_regressor_mean_mae_is_mathematically_correct() -> None:
    y_train = pd.Series([10.0, 20.0, 30.0])
    y_test = pd.Series([15.0, 25.0, 5.0])
    X_train = pd.DataFrame({"x": range(3)})
    X_test = pd.DataFrame({"x": range(3)})

    dummy = DummyRegressor(strategy="mean")
    dummy.fit(X_train, y_train)
    pred = dummy.predict(X_test)

    train_mean = y_train.mean()  # 20.0
    expected_mae = (y_test - train_mean).abs().mean()
    metrics = regression_metrics(y_test, pred)
    assert metrics["mae"] == pytest.approx(expected_mae)


def test_roc_auc_reported_as_unavailable_when_split_has_one_class() -> None:
    y_true = pd.Series([1, 1, 1, 1])  # only one class present
    y_pred = np.array([1, 1, 1, 1])
    y_score = np.array([0.9, 0.8, 0.7, 0.6])
    metrics = classification_metrics(y_true, y_pred, y_score)
    assert metrics["roc_auc"] is None
    assert metrics["pr_auc"] is None
    assert "auc_unavailable_reason" in metrics


# --- Model fit / predict / persistence -------------------------------------

def test_logistic_regression_pipeline_fits_and_predicts(split) -> None:
    X_train, y_train = split.train[PREDICTOR_COLUMNS], split.train["significant_delay"]
    X_test = split.test[PREDICTOR_COLUMNS]

    model = Pipeline([("preprocess", build_preprocessor()), ("model", LogisticRegression(random_state=42))])
    model.fit(X_train, y_train)
    predictions = model.predict(X_test)
    assert len(predictions) == len(X_test)
    assert set(np.unique(predictions)).issubset({0, 1})


def test_linear_regression_pipeline_fits_and_predicts(split) -> None:
    X_train, y_train = split.train[PREDICTOR_COLUMNS], split.train["final_delay_days"]
    X_test = split.test[PREDICTOR_COLUMNS]

    model = Pipeline([("preprocess", build_preprocessor()), ("model", LinearRegression())])
    model.fit(X_train, y_train)
    predictions = model.predict(X_test)
    assert len(predictions) == len(X_test)
    assert np.isfinite(predictions).all()


def test_saved_pipeline_can_be_reloaded_and_predicts_identically(split, tmp_path: Path) -> None:
    X_train, y_train = split.train[PREDICTOR_COLUMNS], split.train["cost_overrun"]
    X_test = split.test[PREDICTOR_COLUMNS]

    model = Pipeline([("preprocess", build_preprocessor()), ("model", LogisticRegression(random_state=42))])
    model.fit(X_train, y_train)
    original_predictions = model.predict(X_test)
    original_proba = model.predict_proba(X_test)

    artifact_path = tmp_path / "model.joblib"
    joblib.dump(model, artifact_path)
    reloaded = joblib.load(artifact_path)

    reloaded_predictions = reloaded.predict(X_test)
    reloaded_proba = reloaded.predict_proba(X_test)

    np.testing.assert_array_equal(original_predictions, reloaded_predictions)
    np.testing.assert_array_almost_equal(original_proba, reloaded_proba)
    assert len(reloaded_predictions) == len(X_test)
