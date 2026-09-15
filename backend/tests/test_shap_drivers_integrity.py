"""Phase 14 SHAP integrity test (brief section 21): the portfolio-wide
driver representation must reproduce Phase 5's saved global SHAP artifact
EXACTLY -- same values, same order, no drift, no re-ranking caused by an
accidental new methodology.

This test reads docs/artifacts/shap_local_examples.json directly with
plain `json.load` -- it does NOT go through app.analytics.drivers at all
for the "expected" side, so it is a genuine independent comparison, not a
tautology.
"""

from __future__ import annotations

import json

from app.analytics.drivers import SHAP_ARTIFACT_PATH, TASK_KEY_TO_ARTIFACT_SECTION, portfolio_drivers
from app.decision_support.shap_explainer import clean_feature_name


def _load_raw_artifact() -> dict:
    with open(SHAP_ARTIFACT_PATH, encoding="utf-8") as f:
        return json.load(f)


def test_portfolio_drivers_reproduce_the_saved_artifact_exactly():
    raw = _load_raw_artifact()
    computed = {d.task_key: d for d in portfolio_drivers(top_n=15)}

    for task_key, section_key in TASK_KEY_TO_ARTIFACT_SECTION.items():
        expected_ranking = raw[section_key]["global_feature_ranking"]
        actual_drivers = computed[task_key].drivers

        assert len(actual_drivers) == len(expected_ranking)
        for rank, (expected_entry, actual_driver) in enumerate(zip(expected_ranking, actual_drivers), start=1):
            assert actual_driver.rank == rank
            assert actual_driver.raw_feature == expected_entry["feature"]
            assert actual_driver.feature == clean_feature_name(expected_entry["feature"])
            assert actual_driver.mean_abs_shap == expected_entry["mean_abs_shap"]


def test_portfolio_drivers_preserve_descending_order_no_resort_bug():
    for task_drivers in portfolio_drivers(top_n=15):
        values = [d.mean_abs_shap for d in task_drivers.drivers]
        assert values == sorted(values, reverse=True)


def test_model_family_explained_matches_raw_artifact():
    raw = _load_raw_artifact()
    computed = {d.task_key: d for d in portfolio_drivers()}
    for task_key, section_key in TASK_KEY_TO_ARTIFACT_SECTION.items():
        assert computed[task_key].model_family_explained == raw[section_key]["model_family_explained"]


def test_matches_serving_model_flag_is_correct_for_every_task():
    computed = {d.task_key: d for d in portfolio_drivers()}
    # Random Forest / XGBoost genuinely serve the two delay tasks -> match.
    assert computed["significant_delay"].matches_serving_model is True
    assert computed["final_delay_days"].matches_serving_model is True
    # The two cost tasks are served by the Phase 4 linear baselines, but
    # Phase 5's saved global SHAP only explains the XGBoost family for them
    # -- a real, disclosed mismatch, must be flagged False, never hidden.
    assert computed["cost_overrun"].matches_serving_model is False
    assert computed["final_cost_overrun_pct"].matches_serving_model is False
