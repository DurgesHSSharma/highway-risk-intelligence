"""Phase 14 portfolio-wide model-attributed drivers.

Reuses Phase 5's saved GLOBAL SHAP artifact
(docs/artifacts/shap_local_examples.json) VERBATIM -- values, order, and
feature identities are read directly from that committed file, never
recomputed. This is a DIFFERENT explanation than Phase 11's LIVE
per-instance SHAP (`app.decision_support.shap_explainer.explain_instance`),
which explains ONE snapshot's own prediction at request time; this module
explains the model's aggregate behavior across the whole Phase 5 test set,
computed once back in Phase 5 and never touched since. See
docs/ADVANCED_ANALYTICS.md "SHAP / global-driver methodology" and the SHAP
integrity test (backend/tests/test_portfolio_drivers.py), which asserts
this module's output reproduces the artifact file exactly, in the same
order -- no drift, no re-ranking.

Known, disclosed characteristic carried over UNMODIFIED from Phase 5 (see
docs/SHAP_EXPLAINABILITY_REPORT.md): for `cost_overrun` and
`final_cost_overrun_pct`, the saved global ranking explains XGBoost
(`model_family_explained`), NOT the Logistic/Linear Regression baseline
that `app.ml.registry.TASK_MODEL_REGISTRY` actually serves for those two
tasks -- Phase 5 only computed global SHAP for the tree-model family, and
this phase's brief explicitly requires reusing that artifact rather than
recomputing it for the linear baselines. `matches_serving_model=False` is
carried on every driver row for those two tasks so this is never silently
implied to explain the serving model.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache

from app.config import REPO_ROOT
from app.decision_support.shap_explainer import clean_feature_name
from app.ml.registry import TASK_MODEL_REGISTRY

SHAP_ARTIFACT_PATH = REPO_ROOT / "docs" / "artifacts" / "shap_local_examples.json"

TASK_KEY_TO_ARTIFACT_SECTION: dict[str, str] = {
    "significant_delay": "delay_classification",
    "final_delay_days": "delay_regression",
    "cost_overrun": "cost_classification",
    "final_cost_overrun_pct": "cost_regression",
}


class ShapArtifactMissingError(RuntimeError):
    pass


@dataclass(frozen=True)
class PortfolioDriver:
    rank: int
    feature: str
    raw_feature: str
    mean_abs_shap: float


@dataclass(frozen=True)
class TaskPortfolioDrivers:
    task_key: str
    label: str
    model_family_explained: str
    matches_serving_model: bool
    drivers: list[PortfolioDriver]


@lru_cache(maxsize=1)
def _load_artifact() -> dict:
    if not SHAP_ARTIFACT_PATH.exists():
        raise ShapArtifactMissingError(
            f"Phase 5 global SHAP artifact not found at {SHAP_ARTIFACT_PATH}. "
            "This is a committed repository artifact -- restore it rather than recomputing."
        )
    with open(SHAP_ARTIFACT_PATH, encoding="utf-8") as f:
        return json.load(f)


def portfolio_drivers(top_n: int = 10) -> list[TaskPortfolioDrivers]:
    artifact = _load_artifact()
    out: list[TaskPortfolioDrivers] = []
    for task_key, section_key in TASK_KEY_TO_ARTIFACT_SECTION.items():
        section = artifact[section_key]
        ranking = section["global_feature_ranking"][:top_n]
        drivers = [
            PortfolioDriver(
                rank=i + 1,
                feature=clean_feature_name(entry["feature"]),
                raw_feature=entry["feature"],
                mean_abs_shap=entry["mean_abs_shap"],
            )
            for i, entry in enumerate(ranking)
        ]
        spec = TASK_MODEL_REGISTRY[task_key]
        out.append(
            TaskPortfolioDrivers(
                task_key=task_key,
                label=section["label"],
                model_family_explained=section["model_family_explained"],
                matches_serving_model=section["model_family_explained"] == spec.model_name,
                drivers=drivers,
            )
        )
    return out
