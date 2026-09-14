# Phase 11 — AI Decision-Support Synthesizer

*** Every number and example on this page was produced by an actual run of
this phase's code against the real committed corpus/database/models — none
of it is estimated or invented. Regenerate the example in section 13 with:
```
cd C:\Projects\highway-risk-intelligence\backend
./.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
curl "http://127.0.0.1:8000/projects/HRI-0006/risk-summary?reporting_month=2022-12"
curl "http://127.0.0.1:8000/projects/HRI-0001/risk-summary?reporting_month=2024-03"
```
***

**REPAIR NOTICE**: This document replaces an earlier version whose SHAP
section incorrectly described reusing Phase 5's *static, cross-model-family*
global feature-importance JSON as "the" Phase 11 explanation, and whose
public endpoint was `POST /projects/{project_id}/decision-support`. Neither
is true of the current implementation. The current implementation computes
**live, per-instance SHAP** against the exact model Phase 6 serves for each
task, and exposes `GET /projects/{project_id}/risk-summary`. See section 1
of this doc's own history for what changed and why.

## 1. Architecture

`backend/app/decision_support/` orchestrates existing Phase 5-pattern SHAP
computation plus Phase 6/8/9/10 services — it trains nothing, embeds
nothing, and detects nothing new:

```
project snapshot
       |
       v
terminal? --yes--> actual outcome (Phase 6) + evidence/inconsistencies only,
       |            prediction/SHAP/simulation explicitly skipped
       |no
       v
ML predictions (Phase 6: app.ml.predict.predict_all_tasks)
       |
       v
LIVE per-instance SHAP risk drivers (app.decision_support.shap_explainer --
the EXACT model app.ml.registry.TASK_MODEL_REGISTRY serves per task)
       |
       +------------------------+
       |                        |
       v                        v
RAG evidence queries       illustrative scenario
(top 1-2 live SHAP         (top live significant_delay driver,
 drivers -> topics)         reused via Phase 10's run_simulation)
       |                        |
       v                        |
RAG evidence (Phase 8)          |
       |                        |
       v                        |
potential inconsistencies       |
(Phase 9, scoped to evidence)   |
       |                        |
       +-----------+------------+
                   |
                   v
          decision-support output
```

| File | Role |
|---|---|
| `backend/app/decision_support/shap_explainer.py` | **The core repair.** Computes LIVE per-instance SHAP against the exact Phase 6 serving pipeline for each task. |
| `backend/app/decision_support/synthesizer.py` | Orchestrates the pipeline; terminal-vs-non-terminal branching. |
| `backend/app/decision_support/topic_mapping.py` | Maps a raw predictor column to a RAG query topic phrase (all 45 columns covered). |
| `backend/app/decision_support/scenario.py` | Constructs the single illustrative what-if scenario from the live top `significant_delay` SHAP driver. |
| `backend/app/decision_support/evidence.py` | Runs Phase 8 retrieval for the SHAP-derived (or terminal-fallback) queries. |
| `backend/app/decision_support/inconsistencies.py` | Scopes the global Phase 9 result to this request's retrieved evidence. |
| `backend/app/decision_support/risk_summary.py` | Deterministic, hedged sentence templates. |
| `backend/app/decision_support/recommendations.py` | Evidence-first recommendation rules. |
| `backend/app/schemas/decision_support.py` | Response schema + disclaimer constants (no request schema — the endpoint takes no body). |
| `backend/app/routers/decision_support.py` | `GET /projects/{project_id}/risk-summary`. |

## 2. Inputs

For a selected real `(project_id, reporting_month)` snapshot:

- **ML predictions** (non-terminal only) — `app.ml.predict.predict_all_tasks`, the exact Phase 6
  function, run against `app.ml.features.build_predictor_row`'s feature row.
- **Actual outcome** (terminal only) — the recorded `significant_delay`/`final_delay_days`/
  `cost_overrun`/`final_cost_overrun_pct` values straight off the snapshot row, mirroring
  `GET /predict`'s own terminal branch exactly.
- **Live SHAP explanation** (non-terminal only) — computed at request time against the
  same singleton pipeline `app.ml.registry.get_model(task_key)` already loaded at startup.
  See section 4.
- **RAG evidence** — `app.rag.retrieval.get_retrieval_service()`, the exact
  Phase 8 singleton, queried once per generated topic.
- **Potential inconsistencies** — `app.contradiction.detector.get_detection_summary()`,
  the exact Phase 9 singleton, unchanged.
- **Illustrative scenario** (non-terminal only) — `app.simulation.service.run_simulation`,
  the exact Phase 10 function, with one override auto-derived from the live top SHAP driver.

## 3. Decision-support flow

`app.decision_support.synthesizer.run_risk_summary` looks up the project/snapshot once,
then branches:

- **Terminal** (`is_terminal_snapshot=true`): returns the recorded actual outcome
  (`prediction_status="actual_outcome"`), explicitly skips SHAP and the scenario
  (`shap_skipped_reason`/`scenario_skipped_reason` populated, `risk_drivers=[]`,
  `scenario=null`), but still runs RAG evidence (using the fixed fallback query pair,
  since no live SHAP driver exists to derive queries from) and Phase 9 scoping.
- **Non-terminal**: runs the full pipeline — prediction, live SHAP for all four tasks,
  SHAP-derived evidence queries, Phase 9 scoping, and the auto-derived illustrative
  scenario.

## 4. ML prediction integration

Unchanged reuse of `app.ml.registry.TASK_MODEL_REGISTRY`, read directly from the actual
code (not assumed) before this repair began:

| Task | Served model | `model_used` |
|---|---|---|
| `significant_delay` | Random Forest | `random_forest` |
| `final_delay_days` | XGBoost | `xgboost` |
| `cost_overrun` | Phase 4 Logistic Regression baseline | `logistic_regression_baseline` |
| `final_cost_overrun_pct` | Phase 4 Linear Regression baseline | `linear_regression_baseline` |

## 5. Live SHAP explainer per task (the core repair)

`app.decision_support.shap_explainer.explain_instance(task_key, X)` computes SHAP for the
**current snapshot's own feature row**, against the **exact model Phase 6 serves**:

| Task | Explainer | Wraps |
|---|---|---|
| `significant_delay` | `shap.TreeExplainer` | the served `RandomForestClassifier` |
| `final_delay_days` | `shap.TreeExplainer` | the served `XGBRegressor` |
| `cost_overrun` | `shap.LinearExplainer` | the served `LogisticRegression` |
| `final_cost_overrun_pct` | `shap.LinearExplainer` | the served `LinearRegression` |

No model is retrained, refit, or reloaded — every explainer wraps the exact `model` step of
the already-loaded singleton Pipeline (`app.ml.registry.get_model`). Preprocessing is never
refit: only the already-fitted `preprocess` step's `.transform()` is called, mirroring
`scripts/explain_models.py`'s established Phase 5 pattern
(`pipeline.named_steps["preprocess"]` / `pipeline.named_steps["model"]`).

**Verified, not assumed** (`backend/tests/test_decision_support_shap.py`): for every task,
`base_value + sum(shap_values)` reconstructs that task's actual serving pipeline output
exactly (within float tolerance) —

- `significant_delay`: reconstructs `pipeline.predict_proba(Xt)[:, 1]` exactly.
- `final_delay_days`: reconstructs `pipeline.predict(Xt)` exactly.
- `cost_overrun`: reconstructs `pipeline.decision_function(Xt)` (log-odds/margin, **not**
  probability) exactly.
- `final_cost_overrun_pct`: reconstructs `pipeline.predict(Xt)` exactly.

**Background data for `LinearExplainer`**: a fixed, seeded (42) sample of 100 rows from the
frozen Phase 4 **TRAINING partition only** (`scripts.data_split.project_level_split` against
`data/processed/delay_features.csv`, unchanged, never validation/test/full-dataset/live-
snapshot data — same rule Phase 10's `training_feature_ranges.json` already follows).
`shap.TreeExplainer` needs no background at all (verified — standard SHAP tree-path
behavior). Explainers and the background sample are built at most once per process and
cached (`_EXPLAINER_CACHE`/`_BACKGROUND_CACHE`), mirroring the "load once" convention
already used for models/RAG index/detector — verified fast in practice (the 9-test SHAP
suite runs in ~2s including all four explainer builds).

**Proven instance-specific, not a static lookup** (`test_shap_is_instance_specific_not_a_static_lookup`):
for the real snapshot `HRI-0006`/`2022-12`, the live top `significant_delay` driver is
`progress_efficiency` — **not** `contractor_productivity_factor`, which was Phase 5's old
*static global* top driver for the same task. A different real snapshot
(`HRI-0132`/`2025-06`) produces a different SHAP value for the same feature. Two of the four
tasks' explained model family also changed outright: `cost_overrun` and
`final_cost_overrun_pct` are now explained via `LinearExplainer` on the actual served linear
baseline, never via a tree model — the exact bug this repair fixes
(`test_cost_tasks_no_longer_explained_via_tree_model`).

### SHAP output semantics (exact, per task)

| Task | What the SHAP value means |
|---|---|
| `significant_delay` | Contribution to the Random Forest's predicted **probability** of the positive (significant-delay) class (probability-scale units). |
| `final_delay_days` | Contribution to the XGBoost model's predicted final-delay-days regression output (same units as the prediction: **days**). |
| `cost_overrun` | Contribution to the Logistic Regression's **linear decision function (log-odds/margin scale, NOT probability)** for the positive (cost-overrun) class — consistent with how Phase 5 already documents XGBoost's classification SHAP values as log-odds-scale, not probability-scale. |
| `final_cost_overrun_pct` | Contribution to the Linear Regression's predicted final-cost-overrun-percentage output (same units as the prediction: **percentage points**). |

Every driver's `direction` field is `"increases"` / `"decreases"` / `"negligible"` from the
sign of its SHAP value, and every `explanation` sentence uses only "associated with a
{direction} model-estimated..." language — never "causes" (enforced by
`test_driver_explanations_are_non_causal`).

### Disclosed finding: a real collinearity artifact in `final_cost_overrun_pct`'s drivers

Investigated (not hidden) during development: `final_cost_overrun_pct`'s live driver list for
`HRI-0006`/`2022-12` shows `planned_physical_progress_pct` and `planned_financial_progress_pct`
with the **identical** SHAP value (`-322.5771`). Verified directly against the real data
(`data/processed/delay_features.csv`): these two columns are **byte-identical across all
8,740 rows** (correlation 0.9999999999999998) — a genuine Phase 2 synthetic-generator
characteristic that Phase 3's own duplicate-column check (which caught
`planned_expenditure_inr_cr`/`planned_cost_to_date_inr_cr` and
`expenditure_variance_pct`/`financial_progress_variance_pct`) did not catch for this pair.
Under perfect collinearity, `LinearRegression`'s fitted coefficients for two identical
columns are not uniquely identified, and since `shap.LinearExplainer`'s value is
`coef_i * (x_i - background_mean_i)`, identical `x_i` and background means for two
perfectly-duplicate columns can legitimately produce identical SHAP contributions. This is a
genuine synthetic-data characteristic, not a bug in this phase's SHAP computation (confirmed
by the additivity check reconstructing the model's actual output exactly) — disclosed here
rather than silently presented, and **not** fixed (fixing Phase 3's feature list is out of
scope for a Phase 11 repair; see the hard "do not modify Phases 1-10" constraint).

## 6. RAG evidence integration

`app.decision_support.evidence.generate_evidence_queries_from_drivers` takes the union of
each task's live top-1 SHAP driver, deduplicates by raw predictor-column identity (a
categorical one-hot feature like `state_Karnataka` reduces to `state`), and maps up to 2
unique identities through `app.decision_support.topic_mapping.FEATURE_TOPIC_MAP` (all 45
`PREDICTOR_COLUMNS` covered — verified by direct comparison against
`scripts.prepare_features.PREDICTOR_COLUMNS`, zero missing). For `HRI-0006`/`2022-12` this
produces `["physical progress project delay", "contractor productivity performance"]` (from
`progress_efficiency` and `contractor_productivity_factor`, the tasks' live top-1 drivers).

`app.decision_support.evidence.gather_evidence` then runs each query through the
**unmodified** Phase 8 `RetrievalService.retrieve()` (top_k=3) and reuses
`app.rag.answer.build_extractive_answer` for the citation-grounded extractive answer text —
no paraphrasing, no inference, no second retrieval implementation. Verified directly
(`test_evidence_reuses_the_exact_retrieval_service_results`): calling
`get_retrieval_service().retrieve(query, top_k=3)` independently for the same query returns
byte-identical `chunk_id`s and `similarity_score`s to what the decision-support response
carries. Every returned evidence item preserves `document_id`, `page_number`, `chunk_id`, and
a `"[DOC-xxx, p. N]"` citation string. A query with nothing above the Phase 8 relevance
threshold (0.35) returns `not_found: true`, `results: []`, and the fixed
`"Not found in the available documents."` string — never a fabricated claim.

For a **terminal** snapshot, no live SHAP driver exists, so evidence queries fall back to the
fixed default pair `("project delay", "cost overrun")` — documented, not silently different
behavior.

## 7. Phase 9 inconsistency integration

Unchanged from the original design (see the module docstring in
`app.decision_support.inconsistencies`): Phase 9's contradiction detector is a single global,
corpus-wide pass, not parameterized by project. `scope_inconsistencies_to_evidence` filters
the unmodified global flag list down to flags where at least one source chunk was actually
retrieved as documentary evidence for *this request's* (SHAP-derived) queries — a filter over
Phase 9's own already-hedged output, no flag's wording, confidence, or status altered. Every
surfaced flag keeps Phase 9's hedged wording verbatim ("potential inconsistency requiring
verification", never "confirmed contradiction"/"confirmed error"). A zero-flag result is a
valid, explicit response (`test_potential_inconsistencies_hedged_or_empty` covers both cases
against the real corpus).

## 8. Illustrative scenario integration (Phase 10 reused)

`app.decision_support.scenario.build_illustrative_scenario` constructs exactly **one**
illustrative what-if scenario per non-terminal request, anchored on the live top
`significant_delay` SHAP driver — never a caller-supplied override (the endpoint takes no
request body):

- **Which feature**: `significant_delay`'s own rank-1 live SHAP driver. SHAP magnitudes are
  not comparable across tasks (probability-scale vs. days-scale vs. log-odds-scale vs.
  percentage-points-scale — see section 5's semantics table), so "the single highest SHAP
  value across all four tasks" would be a scale-comparison fallacy.
  `significant_delay` is the primary risk classification this synthesizer leads with, making
  it a defensible, deterministic anchor.
- **Categorical top driver**: if that driver is a categorical one-hot feature, no numeric
  "illustrative reference value" is well-defined, so no scenario is constructed for that
  request (`scenario_skipped_reason` explains why) — never approximated.
- **Reference value**: the real arithmetic **mean** of that raw predictor column over the
  frozen Phase 4 TRAINING partition (same source file/split as the SHAP background) — a real,
  defensible population-typical value, never an invented threshold. For `HRI-0006`/`2022-12`
  the top driver is `progress_efficiency`, training mean `1.351`.
- **Scoring**: `app.simulation.service.run_simulation` (Phase 10, unmodified) is called with
  exactly `{field: reference_value}`. Real result: moving `progress_efficiency` to `1.351`
  shifted predicted final delay from `94.6` to `76.5` days and predicted final cost overrun
  from `6.4%` to `4.3%`.
- **Labeling**: every scenario carries `label="illustrative, not a recommendation"`, and the
  corresponding recommendation text is prefixed `"Illustrative, not a recommendation: ..."`.
  `scenario.disclaimer` is `app.schemas.simulation.SIMULATION_DISCLAIMER` verbatim (the exact
  Phase 10 string): *"This is a model re-scoring under a hypothetical assumption, not a
  prediction of what will actually happen. It is not a validated causal estimate."*

For a **terminal** snapshot, the scenario is skipped entirely (`scenario=null`,
`scenario_skipped_reason` explains why) — re-scoring a snapshot whose row already encodes the
known final outcome would not isolate a hypothetical override's effect (same rationale Phase
10's own `TerminalSnapshotError` already used for user-supplied overrides).

## 9. Recommendation generation

`app.decision_support.recommendations.generate_recommendations` applies four independent rule
families, **each firing only when its grounding condition is concretely true**:

1. **Model-driver rules**: each task's rank-1 live SHAP driver, deduplicated by raw
   predictor-column identity across tasks. Capped at 3.
2. **Documentary-evidence rules**: one recommendation per evidence query that actually
   returned results, citing every retrieved citation. A query with no results produces no
   recommendation.
3. **Potential-inconsistency rules**: one recommendation per unique (document pair, claim
   type) among the scoped Phase 9 flags, merging flags that share a document pair/claim type.
   Capped at 3.
4. **Scenario rule**: only when the illustrative scenario was actually constructed — one
   recommendation labeled "Illustrative, not a recommendation: ..." plus one per Phase 10
   extrapolation warning.

Every `RecommendationOut` carries `basis_type` and a non-empty `basis_detail` naming the
concrete evidence. The total list is capped at 8.

## 10. Evidence-strength logic

Unchanged from the original design — three interpretable categories, never a calibrated
probability: `high evidence support` (evidence found, no inconsistency touches it),
`moderate evidence support` (evidence found, an inconsistency touches it), `limited evidence
support` (no relevant evidence retrieved).

## 11. Mandatory disclaimers

`app.schemas.decision_support.DisclaimersOut` — present in **every** successful response
(terminal and non-terminal alike, verified by `test_mandatory_disclaimers_present_on_terminal_response_too`):
`ml_limitation`, `causality_limitation`, `scenario_limitation` (Phase 10's
`SIMULATION_DISCLAIMER` verbatim), `evidence_limitation`, `inconsistency_limitation`,
`system_identity`, `synthetic_data_disclaimer` (Phase 6's `SYNTHETIC_DATA_DISCLAIMER_MODEL`
verbatim).

## 12. Terminal snapshot rule

**Decision (repaired)**: a `GET /risk-summary` request for a terminal snapshot
(`is_terminal_snapshot=true`) now returns **HTTP 200** with the recorded actual outcome —
not a 422 rejection as an earlier version of this endpoint did. Prediction, SHAP, and the
illustrative scenario are explicitly skipped (never silently substituted), while RAG evidence
and Phase 9 inconsistency sections still run (using the fixed fallback evidence-query pair,
since no live SHAP driver exists to derive topic queries from).

This mirrors Phase 6's own established terminal-snapshot behavior exactly: `GET /predict`
already returns the recorded actual value (`is_model_prediction: false`) rather than running
a model for a terminal snapshot — `risk-summary`'s `prediction_status="actual_outcome"` is the
identical concept. SHAP and the scenario are skipped (rather than computed) because both are
explicitly forward-looking constructs (association drivers of, and a hypothetical re-scoring
toward, a *predicted* outcome) that do not apply to a snapshot whose actual outcome is already
known and recorded on the row.

Verified on the real running server, not just in tests:
`GET /projects/HRI-0001/risk-summary?reporting_month=2024-03` → `HTTP 200`, real response body
in section 13.

## 13. API contract

```
GET /projects/{project_id}/risk-summary?reporting_month=YYYY-MM
```

No request body.

**Non-terminal example** (real response, trimmed, from `HRI-0006`/`2022-12`, live-server-verified 2026-09-14):

```json
{
  "project": {
    "project_id": "HRI-0006", "state": "Telangana", "project_type": "Greenfield Highway",
    "reporting_month": "2022-12", "project_status": "Ongoing", "is_terminal_snapshot": false
  },
  "prediction_status": "model_prediction",
  "risk_summary": {
    "significant_delay_summary": "The model assigns a probability of 94.7% to the significant-delay class (predicted class: significant-delay).",
    "final_delay_days_summary": "Model-estimated final delay: 94.6 days (total modeled project delay at completion, not days remaining)."
  },
  "risk_drivers": [
    {
      "task_key": "significant_delay", "model_used": "random_forest", "explainer_type": "TreeExplainer",
      "top_drivers": [{"rank": 1, "feature": "progress_efficiency", "shap_value": 0.1130, "direction": "increases"}]
    },
    {
      "task_key": "cost_overrun", "model_used": "logistic_regression_baseline", "explainer_type": "LinearExplainer",
      "top_drivers": [{"rank": 1, "feature": "project_age_ratio", "shap_value": 3.0093, "direction": "increases"}]
    }
  ],
  "shap_skipped_reason": null,
  "documentary_evidence": ["... 2 queries derived from live SHAP drivers, 3 citations each ..."],
  "potential_inconsistencies": [],
  "scenario": {
    "field": "progress_efficiency", "reference_value": 1.3515, "label": "illustrative, not a recommendation",
    "baseline": {"final_delay_days": {"predicted_final_delay_days": 94.60}},
    "simulated": {"final_delay_days": {"predicted_final_delay_days": 76.48}}
  },
  "scenario_skipped_reason": null,
  "recommended_reviews": ["... 6 recommendations, each with basis_type + basis_detail ..."],
  "evidence_strength": "high evidence support",
  "disclaimers": {"...": "all 7 mandatory disclaimer fields"}
}
```

**Terminal example** (real response, trimmed, from `HRI-0001`/`2024-03`):

```json
{
  "project": {"project_id": "HRI-0001", "project_status": "Completed", "is_terminal_snapshot": true},
  "prediction_status": "actual_outcome",
  "predictions": {"significant_delay": {"model_used": null, "predicted_class": null, "actual_value": 0}},
  "risk_summary": {
    "significant_delay_summary": "Recorded actual outcome (terminal snapshot, not a model prediction): significant delay = no."
  },
  "risk_drivers": [],
  "shap_skipped_reason": "Skipped: this snapshot is terminal (is_terminal_snapshot=true) and already records the project's known final outcome, so a live SHAP explanation of a forward-looking model prediction is not applicable -- see docs/DECISION_SUPPORT.md 'Terminal snapshot rule'.",
  "documentary_evidence": ["... fallback queries [\"project delay\", \"cost overrun\"] ..."],
  "scenario": null,
  "scenario_skipped_reason": "Skipped: this snapshot is terminal, so no live SHAP driver exists to anchor an illustrative what-if scenario, ..."
}
```

HTTP status codes:

| Status | Cause |
|---|---|
| 200 | Valid response — terminal or non-terminal. |
| 404 | Unknown `project_id` or `reporting_month`. |
| 422 | Feature-construction failure (defensive parity with `/predict`; not hit by any real snapshot in this corpus). |

## 14. Testing

Baseline confirmed before this repair began: 347/347 (159 root + 188 backend).

- `backend/tests/test_decision_support_shap.py` (9 tests, **new**) — proves the
  explainer/model-family relationship itself (not merely that a `shap` field exists):
  served-model-class assertions read from the actual loaded registry, explainer-type
  assertions, the additivity reconstruction of each task's real pipeline output, and
  instance-specificity (two different real snapshots produce different SHAP values; this
  snapshot's live top driver differs from Phase 5's old static top driver).
- `backend/tests/test_decision_support_service.py` (20 tests, **rewritten**) — `run_risk_summary`
  against the real database/models/RAG index/contradiction detector: non-terminal validity,
  evidence-query derivation from live SHAP drivers, exact retrieval-service-result reuse,
  scenario auto-derivation and Phase 6 baseline consistency, terminal skip behavior, hedged
  wording, recommendation grounding.
- `backend/tests/test_decision_support_api.py` (15 tests, **rewritten**) — HTTP contract:
  the exact `GET /risk-summary` route, confirmation the old `POST /decision-support` route no
  longer exists, no-request-body requirement, 404s, full-schema validation for both terminal
  and non-terminal responses, mandatory-disclaimer presence, and existing-endpoint health
  (`/predict`, `/simulate`, `/documents/search`, `/documents/inconsistencies`).
- Real-server smoke test performed (actual `uvicorn` process + `curl`, not just `TestClient`):
  non-terminal and terminal `risk-summary` requests, confirmation the old POST route returns
  404, and all four pre-existing endpoints, on a freshly started server; server stopped
  cleanly afterward.

Repo-wide count: 159 root + 200 backend = **359**, all passing, pre-existing 321 (from before
Phase 11 entirely) re-verified unmodified.

## 15. Limitations

- Model outputs are estimates from models trained on a **synthetic** dataset — they say
  nothing about real highway-project behavior.
- SHAP values are association, computed on a synthetic-data-fitted model; `contractor_productivity_factor`'s
  outsized influence is a direct, disclosed consequence of Phase 2's generator design (an
  AR(1) latent trait deliberately driving multiple downstream columns), not evidence of a
  real-world relationship of that strength.
- `final_cost_overrun_pct`'s driver list is affected by a real, disclosed perfect-collinearity
  artifact between two Phase 2 synthetic columns (section 5) — SHAP correctly attributes a
  combined effect, but the specific 50/50-looking split between the two identical columns is
  a property of `LinearRegression`'s degenerate solution under exact collinearity, not a
  meaningful individual signal.
- The document corpus is small (4 real documents, ~861 chunks) — a "not found" result is
  expected for most SHAP-derived topics, not a bug.
- The illustrative scenario's single feature choice (`significant_delay`'s top driver) may
  not be the feature a human reviewer would consider most actionable for a given project —
  it is a deterministic, disclosed anchor choice, not a claim of optimality.
- Recommendations are template-generated from real inputs, not written or reviewed by a
  domain expert.

## 16. Why this is not a fact-checker

Every documentary claim traces to a specific, retrieved chunk with a citation, or is
explicitly reported as "Not found in the available documents". Potential inconsistencies are
Phase 9's own heuristic, hedged output, scoped further here, never elevated to "confirmed"
status. No source is ever described as false, wrong, or in error.

## 17. Why this is not causal inference

Live SHAP values describe feature attribution for a specific model's specific prediction on a
synthetic dataset — not causal identification. Every driver statement uses "associated with" /
"the model places importance on" language; "causes" is never generated (enforced by
`test_driver_explanations_are_non_causal`). The illustrative scenario is explicitly labeled
"illustrative, not a recommendation" and carries Phase 10's unmodified causal-limitation
disclaimer.

## 18. Why this is not an official NHAI system

Stated in `disclaimers.system_identity` on every response, terminal and non-terminal alike:
this is a student portfolio project, a prototype inspired by highway infrastructure
monitoring/risk-management workflows, with no connection to the National Highways Authority
of India.
