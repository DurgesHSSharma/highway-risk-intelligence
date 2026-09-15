# Phase 15 — Decision Intelligence

*** Every number and example on this page was produced by an actual run of
this phase's code against the real committed corpus/database/models/cache
-- none of it is estimated or invented. Regenerate the examples in section
14 with:
```
cd C:\Projects\highway-risk-intelligence\backend
./.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
curl "http://127.0.0.1:8000/projects/HRI-0006/decision-intelligence?reporting_month=2022-12"
curl "http://127.0.0.1:8000/projects/HRI-0006/decision-intelligence?reporting_month=2023-06"
curl "http://127.0.0.1:8000/projects/HRI-0328/decision-intelligence?reporting_month=2025-08"
```
***

## 1. Purpose

Phases 1-14 already answer two separate kinds of question: "what will
happen to project X, and why?" (Phase 11's `GET /risk-summary` — live
prediction, live per-instance SHAP, grounded RAG evidence, potential
inconsistencies, an illustrative what-if scenario) and "how does the
portfolio look overall?" (Phase 14's `GET /analytics/*` — historical vs.
predicted separation, composite risk scoring, peer-group segmentation,
portfolio-wide SHAP drivers). Phase 15 answers the question that sits
between them, for one specific project:

1. What is this project's risk?
2. Why does the model consider it risky?
3. What documentary evidence supports that explanation?
4. How does it compare with the rest of the scored portfolio?
5. How does it compare with its state / project-type / contractor peers?
6. Do its project-level live SHAP drivers align with the portfolio-level
   drivers for the same tasks?
7. What should a project manager investigate next?
8. What hypothetical scenario can be evaluated?

This remains a **decision-support prototype**. It never claims causal
inference, causal impact, a guaranteed prediction, guaranteed intervention
effectiveness, official NHAI decision-making, validated operational risk
thresholds, or autonomous decision-making — every disclaimer from Phases
11 and 14 is reused verbatim on every response (section 11).

## 2. Architecture

Phase 15 is a pure **composition** layer. It never duplicates Phase
11's prediction/SHAP/RAG/contradiction/scenario logic, and never
reimplements Phase 14's risk-scoring/segmentation/driver math:

```
GET /projects/{id}/decision-intelligence?reporting_month=YYYY-MM
                       |
                       v
app.decision_support.synthesizer.run_risk_summary   (Phase 11, called ONCE,
    |                                                 as a black box)
    | (project.state / project_type / contractor)
    v
app.decision_intelligence.portfolio_context
    - get_risk_positioning()  -- reads portfolio_prediction_cache via
                                  app.analytics.batch_scoring /
                                  app.analytics.risk_score (Phase 14, reused)
    - get_peer_context()      -- app.analytics.segments.segment_report
                                  (Phase 14, reused), once per dimension
    v
app.decision_intelligence.driver_alignment
    - compute_driver_alignment(live_risk_drivers, portfolio_drivers())
      (app.analytics.drivers.portfolio_drivers is Phase 14's saved global
       SHAP artifact, reused verbatim)
    v
app.decision_intelligence.recommendations
    - peer_elevated_risk_recommendations()
    - driver_divergence_recommendations()
    v
merge with Phase 11's 4 recommendation families,
cap at app.decision_support.recommendations.MAX_TOTAL_RECOMMENDATIONS (reused)
    v
DecisionIntelligenceResponse
```

| File | Role |
|---|---|
| `backend/app/decision_intelligence/portfolio_context.py` | Risk positioning (composite score/percentile/risk level) + peer context (state/project_type/contractor), both reusing Phase 14 services directly. |
| `backend/app/decision_intelligence/driver_alignment.py` | Compares Phase 11's live top SHAP driver against Phase 14's portfolio-wide top driver, per task. |
| `backend/app/decision_intelligence/recommendations.py` | The 5th recommendation family: peer-elevated-risk rule + driver-divergence rule. |
| `backend/app/decision_intelligence/synthesizer.py` | Orchestrates the above, calling Phase 11's `run_risk_summary` once. |
| `backend/app/schemas/decision_intelligence.py` | Response schema, reusing Phase 11/14 schema types directly. |
| `backend/app/routers/decision_intelligence.py` | `GET /projects/{project_id}/decision-intelligence`. |
| `frontend/src/pages/DecisionIntelligence.jsx` | Frontend page, `/projects/:projectId/decision-intelligence`. |
| `frontend/src/components/DecisionIntelligence/*.jsx` | `PercentileGauge`, `PeerContextCard`, `DriverAlignmentRow` — new, additive components. |

## 3. Phase 11 + Phase 14 composition, concretely

- **Never duplicates Phase 11**: `run_decision_intelligence` calls
  `app.decision_support.synthesizer.run_risk_summary(db, project_id,
  reporting_month)` exactly once. Every prediction, SHAP driver, RAG
  evidence item, potential inconsistency, and illustrative scenario in the
  response is that call's own output, untouched. Verified directly
  (`test_decision_intelligence_synthesizer.py`): the Decision Intelligence
  response's `predictions`/`risk_drivers`/`documentary_evidence`/
  `potential_inconsistencies`/`scenario` are numerically identical (within
  float tolerance — see section 19) to a separate, direct call to
  `run_risk_summary` for the same snapshot.
- **Never duplicates Phase 14**: `get_risk_positioning` calls
  `app.analytics.batch_scoring.get_cache_metadata` and
  `app.analytics.risk_score.compute_portfolio_risk_scores` directly (the
  exact functions `/analytics/portfolio` and `/analytics/risk-projects`
  already use); `get_peer_context` calls
  `app.analytics.segments.segment_report` directly (the exact function
  `/analytics/segments` already uses, called once per dimension — the same
  3-calls-per-request pattern `portfolio_service.get_portfolio_overview`
  already established in Phase 14); `driver_alignment` calls
  `app.analytics.drivers.portfolio_drivers()` directly (the exact function
  `/analytics/drivers` already uses).
- **The new endpoint never triggers batch scoring.** Proven behaviorally
  (`test_decision_intelligence_no_batch_scoring.py`), not just by
  inspection: `app.analytics.batch_scoring.run_batch_scoring` is
  monkeypatched to raise, and a normal request still succeeds using the
  existing cache.

## 4. New endpoint

```
GET /projects/{project_id}/decision-intelligence?reporting_month=YYYY-MM
```

No request body. Reuses Phase 11's exact exception behavior — 404 for an
unknown project or reporting month (`ProjectNotFoundError` /
`SnapshotNotFoundError`, unchanged), 422 for a feature-construction failure
(`FeatureConstructionError`, unchanged) — no new exception classes.

## 5. Response contract

`backend/app/schemas/decision_intelligence.py::DecisionIntelligenceResponse`.
Every Phase 11 field (`project`, `prediction_status`, `predictions`,
`risk_summary`, `risk_drivers`, `shap_skipped_reason`,
`documentary_evidence`, `potential_inconsistencies`, `scenario`,
`scenario_skipped_reason`, `evidence_strength`, `evidence_strength_basis`)
is reused from Phase 11's own schema types
(`ProjectSnapshotInfoOut`/`RiskSummaryOut`/`TaskRiskDriversOut`/
`EvidenceQueryResultOut`/`ContradictionFlagOut`/`ScenarioOut`), never
redefined. Three new fields:

- `risk_positioning` — composite score, percentile, portfolio-relative
  risk level, cohort size, cache provenance (section 6).
- `peer_context` — `{"state": ..., "project_type": ..., "contractor":
  ...}`, each a `PeerContextEntryOut` reusing Phase 14's
  `HistoricalSegmentStatOut`/`PredictedSegmentStatOut` (section 7).
- `driver_alignment` — one entry per task (section 8).

`recommended_reviews` replaces Phase 11's field of the same name with the
merged 5-family list (section 9); `disclaimers` is unchanged
(`DisclaimersOut`, all 7 Phase 11 fields).

## 6. Portfolio percentile — exact definition

```
percentile = 100 * count(projects in the current scored cohort with
composite_risk_score <= this project's score) / cohort_size
```

A **higher** percentile means **higher** modeled risk relative to the
current cohort. This is the only percentile methodology used anywhere in
this response (`backend/app/decision_intelligence/portfolio_context.py`'s
`PERCENTILE_DEFINITION` constant, echoed verbatim into every response's
`risk_positioning.percentile_definition` field so the frontend never has
to hardcode it).

`risk_level` (LOW/MEDIUM/HIGH/CRITICAL) is **copied directly** from Phase
14's `compute_portfolio_risk_scores` — never a second risk-band algorithm.

**Cache behavior** (never triggers batch scoring):

| `risk_positioning.status` | Meaning |
|---|---|
| `ok` | The project has a row in `portfolio_prediction_cache`; composite score/percentile/risk level are populated. |
| `cache_unavailable` | The cache has never been generated (`app.analytics.batch_scoring.get_cache_metadata` returns `None`). All numeric fields are `null`; `message` explains how to run `scripts/batch_score_portfolio.py`. |
| `project_not_in_cache` | The cache exists, but this specific project has no row in it (e.g. zero eligible non-terminal snapshots). All numeric fields are `null`; `cohort_size` is still populated so the caller knows the cache itself is fine. |

## 7. Portfolio-relative risk-band disclaimer

`risk_positioning.portfolio_relative_disclaimer` (verbatim, present on
every `ok`-status response):

> This risk level/band is PORTFOLIO-RELATIVE: it is assigned by this
> project's composite-risk-score quartile position within the currently
> scored synthetic cohort... It is NOT an official NHAI threshold, NOT an
> industry threshold, NOT a validated operational threshold, NOT a safety
> threshold, and NOT an intervention threshold.

`risk_positioning.current_risk_basis_note` additionally makes the
historical/predicted/retrospective distinction explicit (master-prompt
section 12): the composite score is computed from each project's own
latest **pre-completion** (non-terminal) snapshot, reusing Phase 14's own
"current predicted risk" definition unchanged — **not** a live "as of
today" snapshot, and explicitly: *"there is no genuinely 'still ongoing'
project in this dataset: current ongoing-project risk is unavailable in
the synthetic corpus."*

## 8. Peer-group methodology

For the selected project, `peer_context` provides one entry per dimension
(`state`, `project_type`, `contractor`), each built entirely from Phase
14's `segment_report(db, dimension)` (never reimplemented):

- `status: "ok"` — the project's own value for that dimension appears in
  the current segment report. `historical` (always populated when
  `status="ok"` — computed purely from terminal snapshot rows, so it does
  **not** depend on the prediction cache) and `predicted` (populated only
  when the cache exists **and** has scored rows for that segment — `null`
  otherwise, exactly mirroring Phase 14's own `segment_report` behavior)
  are both preserved, along with `small_sample`/`min_sample_threshold`.
- `status: "unavailable"` — either the project has no recorded value for
  that dimension (`contractor` can be `None`), or the value does not
  appear anywhere in the current segment report. `reason` explains which,
  `segment` is `null`. This is never a 500 — a missing peer dimension is
  reported explicitly, never silently substituted.

## 9. Small-sample behavior

Every peer entry preserves Phase 14's `small_sample` flag and
`min_sample_threshold` **unchanged** — a below-threshold peer group (e.g.
Punjab, n=11 < the state threshold of 15) is still shown with its real
historical/predicted stats, just flagged, never dropped or hidden. Phase
14's thresholds (state/project_type: 15, contractor: 8) are never lowered
here to make a segment look statistically stronger.

## 10. Driver-alignment methodology

For each of the 4 supported tasks (`significant_delay`,
`final_delay_days`, `cost_overrun`, `final_cost_overrun_pct`),
`driver_alignment` compares:

- **Live**: Phase 11's per-instance top-1 SHAP driver for *this specific
  snapshot*, computed at request time against the exact model
  `app.ml.registry.TASK_MODEL_REGISTRY` actually serves
  (`app.decision_support.shap_explainer.explain_instance`).
- **Portfolio**: Phase 14's portfolio-wide top-1 driver, read verbatim
  from the committed Phase 5 SHAP artifact
  (`app.analytics.drivers.portfolio_drivers()`).

Both sides are reduced to a raw predictor-column **identity** via the
existing, unchanged `app.decision_support.shap_explainer.driver_identity`
(never a second feature-identity implementation) — a categorical one-hot
level like `state_Karnataka` reduces to `state`, so **two different
one-hot levels of the same categorical column still count as agreement**.
This is a direct, intended consequence of reusing `driver_identity` as-is,
verified with a dedicated synthetic fixture
(`test_decision_intelligence_driver_alignment.py`, since the real corpus's
live top drivers for both delay tasks happen to be numeric, never
naturally exercising the categorical-reduction branch).

| Field | Rule |
|---|---|
| `agreement` | `live_identity == portfolio_identity` when both sides exist; `null` if either side is unavailable (e.g. a terminal snapshot, where Phase 11 skips SHAP entirely). |
| `comparable` | Copied directly from Phase 14's `matches_serving_model` (never recomputed) — `false` whenever the portfolio-wide ranking explains a different model family than the one actually serving that task. |

## 11. `matches_serving_model` caveat — non-comparable cost tasks

For `cost_overrun` and `final_cost_overrun_pct`, Phase 14's saved global
SHAP artifact explains **XGBoost**, but the Phase 4 linear baselines
actually serve those two tasks (`matches_serving_model=false`, an
unmodified, disclosed Phase 14 characteristic — see
`docs/ADVANCED_ANALYTICS.md` section 15). Phase 15 never presents this as
a meaningful agree/disagree comparison: `comparable=false` for both tasks,
and the frontend renders the literal string **"Not a meaningful comparison
— different model family."** instead of a green/red badge — the raw
`live_top_driver`/`portfolio_top_driver`/`agreement` values are still
exposed for transparency, just not framed as a comparison result.

## 12. Recommendation rules — the 5th family (`portfolio_context`)

Phase 11's four existing recommendation families
(`model_driver`/`documentary_evidence`/`potential_inconsistency`/
`scenario`) are reused **unchanged in content** — only re-wrapped into the
new response type because its `basis_type` Literal has a 5th value.
`backend/app/decision_intelligence/recommendations.py` adds exactly two
deterministic sub-rules, each firing only when its grounding condition is
concretely true (never "by default", never random, never an LLM):

**Rule A — peer-elevated-risk.** Fires only when ALL of:
1. `risk_positioning.risk_level` is `HIGH` or `CRITICAL`.
2. At least one peer group has `small_sample=false`.
3. That peer group's historical `significant_delay_rate` **or**
   `cost_overrun_rate` exceeds the portfolio-wide corresponding rate
   (`app.analytics.historical.historical_overview`, reused) by at least
   `PEER_ELEVATION_THRESHOLD_PP` (see section 13).

Text always names the specific dimension, segment value, peer rate,
portfolio-wide rate, and sample size, with hedged wording ("may be worth
reviewing...", "verifying..."), capped at 2 (`MAX_PEER_ELEVATION_RECOMMENDATIONS`).

**Rule B — driver-divergence.** Fires only when `comparable=true` AND
`agreement=false` AND both drivers are available for a task. Structurally
cannot fire for `cost_overrun`/`final_cost_overrun_pct` when
`matches_serving_model=false`, since `comparable` is already `false` in
that case (section 11) — no separate task-key exclusion needed. Text names
the task, the live driver, and the portfolio driver, hedged as "consider
investigating...", capped at 2 (`MAX_DRIVER_DIVERGENCE_RECOMMENDATIONS`).

Both rules avoid every prohibited absolute phrase ("this project will
fail", "this action will reduce delay", "this segment looks risky") —
enforced by a dedicated test
(`test_peer_elevation_never_uses_prohibited_absolute_language`).

The combined list (Phase 11's up to 8 + Phase 15's up to 4 candidates) is
capped at `app.decision_support.recommendations.MAX_TOTAL_RECOMMENDATIONS`
(**8**, imported directly — never a second, redefined constant).

## 13. Real observed data used for threshold selection

Computed via `app.analytics.historical.historical_overview` and
`app.analytics.segments.segment_report` against the real committed
database (see `backend/tests/test_decision_intelligence_independent_validation.py`
for the same computation, independently re-derived from the raw CSV):

- Portfolio-wide historical significant-delay rate: **49.25%**
- Portfolio-wide historical cost-overrun rate: **38.25%**
- 50 of the 70 state/project_type/contractor segments clear their Phase 14
  `MIN_SAMPLE_THRESHOLDS` (`small_sample=False`).
- Peer-minus-portfolio historical-rate spread across those 50 segments:

  | Metric | Min | Max | 75th percentile (Q3) |
  |---|---|---|---|
  | Significant-delay rate | -49.25pp | +50.75pp | +13.25pp |
  | Cost-overrun rate | -38.25pp | +61.75pp | +13.72pp |

**Chosen threshold: 10 percentage points (`PEER_ELEVATION_THRESHOLD_PP =
0.10`).** Defensible because: (1) it is a round, human-interpretable
number a project manager can reason about directly; (2) it sits just below
both metrics' Q3 (~13.3-13.7pp), so it flags roughly the most elevated
~30% of qualifying segments (14-16 of 50) rather than the broad
near-portfolio-average middle; (3) it is well inside the observed range on
both sides (-38 to +62pp), so it is never trivially always-true or
never-true. Not an invented round number — chosen after inspecting the
real distribution above.

## 14. Real example responses

**Non-terminal, real-server-verified** (`HRI-0006` / `2022-12`, MEDIUM risk
level, 49.8th percentile of 400 scored projects):

```json
{
  "project": {"project_id": "HRI-0006", "state": "Telangana", "reporting_month": "2022-12", "is_terminal_snapshot": false},
  "prediction_status": "model_prediction",
  "risk_positioning": {
    "status": "ok", "cohort_size": 400, "composite_risk_score": 35.76,
    "risk_level": "MEDIUM", "percentile": 49.75,
    "delay_risk": 0.527, "cost_risk": 0.188
  },
  "peer_context": {
    "state": {"status": "ok", "value": "Telangana", "small_sample": false,
      "historical": {"project_count": 19, "significant_delay_rate": 0.632, "cost_overrun_rate": 0.316}},
    "contractor": {"status": "ok", "value": "Malwa Builders Pvt Ltd", "small_sample": false,
      "historical": {"project_count": 17, "significant_delay_rate": 0.765, "cost_overrun_rate": 0.529}}
  },
  "driver_alignment": [
    {"task_key": "significant_delay", "matches_serving_model": true, "comparable": true,
     "live_top_driver": "progress_efficiency", "portfolio_top_driver": "contractor_productivity_factor", "agreement": false},
    {"task_key": "final_delay_days", "matches_serving_model": true, "comparable": true,
     "live_top_driver": "contractor_productivity_factor", "portfolio_top_driver": "contractor_productivity_factor", "agreement": true},
    {"task_key": "cost_overrun", "matches_serving_model": false, "comparable": false,
     "live_top_driver": "project_age_ratio", "portfolio_top_driver": "cost_tracking_gap_inr_cr", "agreement": false}
  ],
  "recommended_reviews": ["... 7 items: 3 model_driver, 2 documentary_evidence, 1 scenario, 1 portfolio_context (driver-divergence for significant_delay) ..."]
}
```

**Terminal, real-server-verified** (`HRI-0006` / `2023-06`,
`prediction_status="actual_outcome"`, SHAP/scenario skipped, portfolio
context still renders — it is driven by the project's own cached
pre-completion snapshot, not the requested reporting_month):

```json
{
  "project": {"project_id": "HRI-0006", "reporting_month": "2023-06", "is_terminal_snapshot": true},
  "prediction_status": "actual_outcome",
  "risk_drivers": [],
  "shap_skipped_reason": "Skipped: this snapshot is terminal ...",
  "scenario": null,
  "scenario_skipped_reason": "Skipped: this snapshot is terminal, so no live SHAP driver exists to anchor an illustrative what-if scenario, ...",
  "risk_positioning": {"status": "ok", "percentile": 49.75, "risk_level": "MEDIUM"},
  "driver_alignment": [
    {"task_key": "significant_delay", "live_top_driver": null, "agreement": null, "comparable": true}
  ]
}
```

**CRITICAL project with the peer-elevated-risk rule firing**
(`HRI-0328` / `2025-08`, composite risk score **93.1**, **100.0th**
percentile of 400 — the real top-1 CRITICAL example from
`docs/ADVANCED_ANALYTICS.md` section 22):

```json
{
  "risk_positioning": {"status": "ok", "composite_risk_score": 93.13, "risk_level": "CRITICAL", "percentile": 100.0},
  "recommended_reviews": [
    "... 3 model_driver, 2 documentary_evidence, 1 scenario ...",
    {
      "text": "This project's portfolio-relative risk level is CRITICAL. Its contractor peer group ('Rashtriya Builders Pvt Ltd', n=8) has a historical cost-overrun rate of ...% ... above the portfolio-wide rate of 38.2% -- it may be worth reviewing ...",
      "basis_type": "portfolio_context",
      "basis_detail": "Peer-elevated-risk: contractor='Rashtriya Builders Pvt Ltd' historical cost-overrun rate ... vs. portfolio-wide 38.2% (n=8, threshold=10pp)."
    },
    {
      "text": "This project's portfolio-relative risk level is CRITICAL. Its contractor peer group ('Rashtriya Builders Pvt Ltd', n=8) has a historical significant-delay rate ... -- it may be worth reviewing ...",
      "basis_type": "portfolio_context"
    }
  ]
}
```
(8 total recommendations — capped at `MAX_TOTAL_RECOMMENDATIONS`.)

## 15. Testing

73 new backend tests across 7 files
(`backend/tests/test_decision_intelligence_{portfolio_context,driver_alignment,recommendations,synthesizer,api,no_batch_scoring,independent_validation}.py`),
10 new frontend tests (`frontend/src/pages/DecisionIntelligence.test.jsx`)
plus 1 updated (`frontend/src/layout/Sidebar.test.jsx`, enumerating the new
nav entry).

Covers (master-prompt section 28's full 36-item checklist): endpoint
existence; valid non-terminal/terminal responses; unknown project/month
404; feature-construction 422; cache-unavailable/project-not-in-cache
behavior; no-batch-scoring proof (monkeypatched `run_batch_scoring` to
raise); percentile calculation and independent validation from raw cache
data; risk-level reuse; state/project-type/contractor peer context;
small-sample preservation; live-SHAP-stays-live proof (byte-for-byte
comparison against a direct `run_risk_summary` call); portfolio-driver
retrieval; driver-identity comparison including the categorical path (via
a synthetic fixture); `matches_serving_model` preservation; `comparable`
behavior; non-comparable cost tasks never trigger the divergence rule;
both Phase 15 sub-rules; existing 4 recommendation families intact;
combined-recommendation cap; `basis_type`/`basis_detail` traceability;
no-fabrication (every unavailable state is explicit, never a fallback);
RAG evidence stays grounded; contradiction context stays separate;
what-if disclaimer preserved; historical/predicted/retrospective
distinction; zero-ongoing-project wording; portfolio-relative disclaimer
presence.

**Independent math validation** (master-prompt section 30 — never just
calling the implementation and comparing it to itself):

- Percentile: recomputed from raw `portfolio_prediction_cache` rows with a
  formula written fresh in the test (not calling
  `get_risk_positioning`'s own counting code).
- Peer historical rates (state + contractor): recomputed directly from
  `data/synthetic/highway_project_snapshots.csv` via pandas. A real,
  disclosed synthetic-data quirk was caught while writing this test:
  project `HRI-0084`'s terminal row has a `NaN` `contractor` value (while
  its earlier rows correctly carry it) — `contractor` is a project-level
  STATIC field the app resolves via `groupby("project_id").first()`
  (`app/db/loader.py`, protected Phase 6 file, unmodified), not from the
  terminal row alone, so the independent test was fixed to resolve
  `contractor` the same documented way rather than naively reading the
  terminal row's own value.
- Driver alignment: the live SHAP result was obtained by calling
  `app.decision_support.shap_explainer.explain_instance` directly (not via
  `app.decision_intelligence` at all), and the portfolio artifact was read
  with a raw `json.load` over `docs/artifacts/shap_local_examples.json`
  (not via `app.analytics.drivers.portfolio_drivers()`), then compared.

Repo-wide count after Phase 15: **159 root (unchanged) + 361 backend
(+73) + 70 frontend (+10) = 590**, all passing, pre-existing 507 (all of
Phase 1-14) re-verified unmodified.

## 16. Browser verification

Real project/snapshot used: `HRI-0006`/`2022-12` (non-terminal),
`HRI-0006`/`2023-06` (terminal), `HRI-0328`/`2025-08` (CRITICAL, exercises
the peer-elevated-risk recommendation live). Both `uvicorn` (a real
backend process — the default port 8000 was held by a stale process this
session's tooling could not see or stop, the exact issue already disclosed
in Phase 14's own memory notes; worked around identically, by running a
second instance on port 8010 with a temporary, deleted-before-finishing
`frontend/.env.local` override) and `vite` dev servers were started for
real, not just unit-tested.

Verified in the real running app: page loads; live SHAP renders per task
with the correct explainer-type/semantics text; documentary evidence
renders with citations; "no potential inconsistencies" empty state
renders (this evidence set had none flagged); portfolio percentile and
risk-level badge render (both in the executive-risk summary and the
dedicated Portfolio Position section); all three peer-group cards render
with correct historical/predicted separation and a real small-sample flag
(Punjab-style below-threshold segments render, not hidden); driver
alignment renders "Agrees with portfolio" / "Diverges from portfolio" for
the two comparable tasks and the literal "Not a meaningful comparison —
different model family." note (no colored badge) for the two
non-comparable cost tasks; the merged recommendation list renders with
`basis_type`/`basis_detail` for every item, including a real
`portfolio_context` peer-elevated-risk recommendation for the CRITICAL
project; the terminal snapshot correctly shows "Recorded final outcome"
tiles, the SHAP-skipped and scenario-skipped messages, and still renders
portfolio context (driven by the project's own cache row, not the
requested month); "Open Simulator" and the added "Risk Summary" cross-nav
button both navigate correctly; the `/decision-intelligence` root route
renders `ProjectPicker`; an unknown project (`HRI-9999`) renders the
existing not-found empty state.

**Responsive**: verified at 1280px (desktop, screenshot), 768px (tablet)
and 375px (mobile) via both screenshot and a DOM-level horizontal-overflow
check (`document.documentElement.scrollWidth` vs. `clientWidth`, plus an
explicit per-element bounding-rect scan) — the screenshot tool itself was
occasionally unreliable at non-desktop sizes in this pane (a known,
previously-disclosed compositing artifact, not an app bug — see Phase 14's
own memory notes), so the DOM-level check was treated as authoritative.

**One real bug found and fixed during this verification**: the
non-comparable-cost-task note ("Not a meaningful comparison — different
model family.") was initially rendered using the shared `.badge` CSS
class, which sets `white-space: nowrap` (correct for short pill labels
like "High"/"Medium", wrong for a full sentence) — this overflowed the
375px mobile viewport by ~56px (confirmed via the DOM scan, not just a
screenshot glance). Fixed by giving that note its own additive
`.not-comparable-note` class (`frontend/src/styles/global.css`) that wraps
normally, instead of touching the shared `.badge` class used everywhere
else in the app. Re-verified zero overflow at all three breakpoints after
the fix.

**Browser console**: only the pane's own benign Vite HMR WebSocket
message and the two expected 404s from the deliberate unknown-project
(`HRI-9999`) check — no new application errors introduced.

## 17. Performance

- The endpoint calls Phase 11's `run_risk_summary` exactly once (verified:
  `app.ml.predict.predict_all_tasks` is called exactly once per request,
  not once per portfolio-context section).
- Never triggers Phase 14 batch scoring (section 3).
- `get_risk_positioning` reads the full `portfolio_prediction_cache`
  (~400 rows) once per request — the same bounded-cohort pattern Phase
  14's own `/analytics/*` endpoints already use, explicitly sanctioned by
  `docs/ADVANCED_ANALYTICS.md` section 19 at this project's scale.
- `get_peer_context` calls `segment_report` once per dimension (3 calls
  total) — the identical pattern Phase 14's own
  `portfolio_service.get_portfolio_overview` already uses. No per-peer
  -project query loop.
- `driver_alignment` reads Phase 14's small (~15KB) committed SHAP JSON
  artifact via its existing `lru_cache`d loader — never recomputed.

No new N+1 query pattern was introduced; no new heavy computation was
added beyond what Phase 11's own `run_risk_summary` already performs for a
single `GET /risk-summary` request.

## 18. ₹0 architecture

No new dependency was added (backend or frontend) — Phase 15 is pure
composition over already-installed Phase 1-14 packages. No paid API, LLM,
embedding service, vector DB, cloud DB, OCR, hosting, monitoring, dataset,
or maps service is used.

## 19. Synthetic-data limitation

Every number in this document and every response field ultimately
descends from Phase 2's synthetic dataset — see
`docs/SYNTHETIC_DATA_METHODOLOGY.md`. Nothing here says anything about
real highway-project behavior; `disclaimers.synthetic_data_disclaimer` is
present on every response, reused verbatim from Phase 6/11.

## 20. Retrospective-analysis limitation

As in Phase 14, "current predicted risk" is not a live "as of today"
snapshot — it is each project's own latest pre-completion reporting month,
because every project in this synthetic corpus is simulated through to
completion (section 7). `risk_positioning.current_risk_basis_note` states
this explicitly on every `ok`-status response, including the literal
sentence *"current ongoing-project risk is unavailable in the synthetic
corpus"* required by the master-prompt's zero-ongoing-project rule.

## 21. Non-causal disclaimer

Live SHAP drivers, portfolio-wide SHAP drivers, driver-alignment
agreement/divergence, and peer-elevated-risk recommendations are all
**associational**, never causal. Every generated sentence uses "is
associated with"/"the model places importance on"/"may be worth
reviewing" language; "causes"/"will fail"/"will reduce" are never
generated (enforced by a dedicated test). The illustrative what-if
scenario carries Phase 10's unmodified causal-limitation disclaimer
verbatim.

## 22. Known limitations

- Two floating-point-comparison numeric-tolerance tests exist for the
  identical, already-disclosed reason Phase 14's own
  `test_batch_scoring.py` has one: repeated
  `RandomForestClassifier`/`LogisticRegression` `predict_proba()` calls
  show ~1e-13 drift across independent runs — this test suite calls
  Phase 11's prediction pipeline twice (once inside
  `run_decision_intelligence`, once directly) for a cross-check, so it
  tolerates that drift rather than asserting bit-exact equality.
- Peer context's `predicted` sub-field can legitimately be `null` for a
  peer group with zero cache-scored projects, even when
  `risk_positioning.status="ok"` for the requested project itself — this
  mirrors Phase 14's own `segment_report` behavior exactly, not a Phase 15
  inconsistency.
- The `PEER_ELEVATION_THRESHOLD_PP` (10 percentage points) is derived from
  the current synthetic cohort's own real spread distribution (section
  13) — it is a defensible, data-inspected choice for this dataset, not a
  claim that 10pp is the "correct" real-world threshold for highway
  project risk management.
- All other Phase 11/14 limitations (synthetic-data-fitted models, the
  `final_cost_overrun_pct` collinearity artifact, batch-relative
  normalization, quartile-based risk bands always splitting the cohort
  into ~25% bands by construction, thin predicted-trend tail years) carry
  through unchanged — see `docs/DECISION_SUPPORT.md` section 15 and
  `docs/ADVANCED_ANALYTICS.md` section 20.
