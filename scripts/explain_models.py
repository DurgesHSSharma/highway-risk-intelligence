"""
Phase 5: SHAP explainability for the tree-based models trained by
scripts/train_tree_models.py, evaluated on the identical frozen Phase 4
project-level split (scripts/data_split.py). Generates:

  - one GLOBAL beeswarm/summary plot per task (docs/artifacts/*_shap_summary.png)
  - two LOCAL waterfall plots per task -- a high-prediction and a
    low-prediction example, selected from the TEST set by the model's own
    prediction (never by looking at the true target label), so example
    selection cannot leak target information
    (docs/artifacts/*_shap_waterfall_{high,low}.png)
  - a machine-readable summary of every local example's top contributing
    features (docs/artifacts/shap_local_examples.json), which
    docs/SHAP_EXPLAINABILITY_REPORT.md is written from directly.

IMPORTANT -- which model is explained per task
------------------------------------------------
shap.TreeExplainer requires a tree-based model. docs/MODEL_COMPARISON_REPORT.md
honestly recommends the Phase 4 LINEAR baseline (not a tree model) for three
of the four tasks (B, C, D), because Random Forest / XGBoost did not
robustly improve on it there. Since SHAP TreeExplainer cannot explain a
linear baseline, this script explains the BEST-VALIDATION-SCORING tree
model for every task regardless of which model is ultimately recommended
for deployment -- this is a deliberate, disclosed deviation from "explain
the recommended model" so that Phase 5's tree ensembles remain inspectable.
See docs/SHAP_EXPLAINABILITY_REPORT.md section 1 for the same disclosure.

SHAP values are model attribution, not causation -- every local explanation
below is worded as "associated with" / "pushed the prediction" /
"the model relied on", never "caused".

Usage (from repo root):
    backend/.venv/Scripts/python.exe -m scripts.explain_models
"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shap

from scripts.data_split import project_level_split
from scripts.prepare_features import PREDICTOR_COLUMNS
from scripts.train_baseline_models import TASKS

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROCESSED_DIR = REPO_ROOT / "data" / "processed"
DEFAULT_ARTIFACTS_DIR = REPO_ROOT / "docs" / "artifacts"
DEFAULT_RF_DIR = REPO_ROOT / "models" / "random_forest"
DEFAULT_XGB_DIR = REPO_ROOT / "models" / "xgboost"
DEFAULT_OUTPUT_JSON = DEFAULT_ARTIFACTS_DIR / "shap_local_examples.json"

# Which tree model family is explained for each task -- the model with the
# higher VALIDATION primary metric (never test) among Random Forest /
# XGBoost, per models/metrics/tree_metrics.json (see module docstring for
# why this can differ from the deployment recommendation).
SHAP_MODEL_FOR_TASK = {
    "delay_classification": "random_forest",
    "delay_regression": "xgboost",
    "cost_classification": "xgboost",
    "cost_regression": "xgboost",
}

MAX_DISPLAY = 12
GLOBAL_SAMPLE_SIZE = 500  # test-set rows used for the global beeswarm plot


def load_pipeline(task_key: str, model_family: str):
    directory = DEFAULT_RF_DIR if model_family == "random_forest" else DEFAULT_XGB_DIR
    return joblib.load(directory / f"{task_key}_{model_family}.joblib")


def transform(pipeline, X: pd.DataFrame) -> tuple[np.ndarray, list[str]]:
    preprocessor = pipeline.named_steps["preprocess"]
    transformed = preprocessor.transform(X)
    if hasattr(transformed, "toarray"):
        transformed = transformed.toarray()
    return transformed, list(preprocessor.get_feature_names_out())


def build_explanation(pipeline, model_family: str, task_type: str, Xt: np.ndarray, feature_names: list[str]):
    """Returns a shap.Explanation already sliced to a single output
    dimension (positive class for classification, the raw prediction for
    regression) and with feature_names attached."""
    model = pipeline.named_steps["model"]
    explainer = shap.TreeExplainer(model)
    explanation = explainer(Xt)
    if task_type == "classification" and explanation.values.ndim == 3:
        # RandomForestClassifier: shape (n, features, n_classes) -- keep class 1.
        explanation = explanation[..., 1]
    explanation.feature_names = feature_names
    return explanation


def top_contributions(explanation_row, k: int = 8) -> dict:
    values = explanation_row.values
    names = explanation_row.feature_names
    order = np.argsort(np.abs(values))[::-1][:k]
    pushed_up = [
        {"feature": names[i], "shap_value": float(values[i])}
        for i in order if values[i] > 0
    ]
    pushed_down = [
        {"feature": names[i], "shap_value": float(values[i])}
        for i in order if values[i] < 0
    ]
    return {
        "base_value": float(explanation_row.base_values),
        "final_output": float(explanation_row.base_values + values.sum()),
        "pushed_prediction_up": pushed_up,
        "pushed_prediction_down": pushed_down,
    }


def explain_task(task_key: str, cfg: dict, artifacts_dir: Path) -> dict:
    model_family = SHAP_MODEL_FOR_TASK[task_key]
    task_type = cfg["task_type"]
    target = cfg["target"]

    df = pd.read_csv(DEFAULT_PROCESSED_DIR / cfg["dataset"])
    split = project_level_split(df)
    X_test = split.test[PREDICTOR_COLUMNS].reset_index(drop=True)
    y_test = split.test[target].reset_index(drop=True)

    pipeline = load_pipeline(task_key, model_family)
    Xt, feature_names = transform(pipeline, X_test)

    # --- Global explanation: a fixed-size, seeded sample of the test set ---
    rng = np.random.default_rng(42)
    sample_size = min(GLOBAL_SAMPLE_SIZE, Xt.shape[0])
    sample_idx = rng.choice(Xt.shape[0], size=sample_size, replace=False)
    sample_idx.sort()
    global_explanation = build_explanation(pipeline, model_family, task_type, Xt[sample_idx], feature_names)

    artifacts_dir.mkdir(parents=True, exist_ok=True)
    plt.figure()
    shap.plots.beeswarm(global_explanation, show=False, max_display=MAX_DISPLAY)
    plt.title(f"{cfg['label']} -- SHAP global summary ({model_family})")
    summary_path = artifacts_dir / f"{task_key}_shap_summary.png"
    plt.savefig(summary_path, dpi=120, bbox_inches="tight")
    plt.close()

    mean_abs = np.abs(global_explanation.values).mean(axis=0)
    global_ranking = [
        {"feature": feature_names[i], "mean_abs_shap": float(mean_abs[i])}
        for i in np.argsort(mean_abs)[::-1][:15]
    ]

    # --- Local explanations: selected by the model's OWN prediction ---
    # Predict via the full pipeline so predictions are computed identically
    # to how the model is actually used (predict_proba/predict on raw X).
    if task_type == "classification":
        pred_score = pipeline.predict_proba(X_test)[:, 1]
    else:
        pred_score = pipeline.predict(X_test)

    high_idx = int(np.argmax(pred_score))
    low_idx = int(np.argmin(pred_score))

    local_idx = np.array(sorted({high_idx, low_idx}))
    local_explanation = build_explanation(pipeline, model_family, task_type, Xt[local_idx], feature_names)
    local_pos = {orig_i: pos for pos, orig_i in enumerate(local_idx)}

    local_examples = {}
    for label, idx in [("high", high_idx), ("low", low_idx)]:
        row_explanation = local_explanation[local_pos[idx]]
        contrib = top_contributions(row_explanation)
        contrib.update({
            "test_row_index": idx,
            "project_id": str(split.test.reset_index(drop=True).loc[idx, "project_id"]),
            "reporting_month": str(split.test.reset_index(drop=True).loc[idx, "reporting_month"]),
            "model_predicted_score": float(pred_score[idx]),
            "actual_target_value": (
                None if task_type == "classification" else float(y_test.loc[idx])
            ) if task_type != "classification" else int(y_test.loc[idx]),
        })
        local_examples[label] = contrib

        plt.figure()
        shap.plots.waterfall(row_explanation, show=False, max_display=MAX_DISPLAY)
        plt.title(f"{cfg['label']} -- {label}-prediction example ({model_family})")
        plot_path = artifacts_dir / f"{task_key}_shap_waterfall_{label}.png"
        plt.savefig(plot_path, dpi=120, bbox_inches="tight")
        plt.close()

    return {
        "task_type": task_type,
        "label": cfg["label"],
        "model_family_explained": model_family,
        "global_summary_plot": str((artifacts_dir / f"{task_key}_shap_summary.png").relative_to(REPO_ROOT)),
        "global_feature_ranking": global_ranking,
        "local_examples": local_examples,
        "local_example_plots": {
            "high": str((artifacts_dir / f"{task_key}_shap_waterfall_high.png").relative_to(REPO_ROOT)),
            "low": str((artifacts_dir / f"{task_key}_shap_waterfall_low.png").relative_to(REPO_ROOT)),
        },
    }


def main() -> None:
    results = {}
    for task_key, cfg in TASKS.items():
        print(f"\n=== SHAP: {cfg['label']} ({SHAP_MODEL_FOR_TASK[task_key]}) ===")
        result = explain_task(task_key, cfg, DEFAULT_ARTIFACTS_DIR)
        results[task_key] = result
        print(f"  top global feature: {result['global_feature_ranking'][0]['feature']} "
              f"(mean|SHAP|={result['global_feature_ranking'][0]['mean_abs_shap']:.4f})")
        print(f"  saved: {result['global_summary_plot']}")

    DEFAULT_OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(DEFAULT_OUTPUT_JSON, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nWrote SHAP local-example summary to {DEFAULT_OUTPUT_JSON}")


if __name__ == "__main__":
    main()
