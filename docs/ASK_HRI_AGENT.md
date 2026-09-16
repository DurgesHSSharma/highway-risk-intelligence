# Phase 17C: Ask HRI Agent

A deterministic query-router interface -- **not an LLM, not a general-purpose
chatbot**. Every answer either calls a real, already-existing HRI service
and reports its real output, or returns a fixed, honest "I don't have
enough information" response. There is no code path that generates free
text or invents a fact.

## Local LLM feasibility (re-checked, not assumed)

Verified live on this machine at the start of this phase: `ollama` is
**not installed**, and free RAM was **1.4 GB of 16.4 GB total** -- the
same memory-pressure condition Phase 8 measured (~1-1.8 GB free) when it
made the same "extractive, no LLM" decision for RAG. `backend/requirements.txt`
carries zero LLM/generation libraries. Per the Phase 1 feasibility
assessment (`docs/local_llm_feasibility.md`), a 3-4B Q4 GGUF model via
Ollama is theoretically GPU-feasible on this machine's 4GB-VRAM RTX 3050
Ti, but was never installed, pulled, or benchmarked across 8 prior phases
because of this same RAM-pressure finding -- reconfirmed, not assumed, for
this phase. **Conclusion: no local LLM was installed for this feature.**
The agent is built entirely as deterministic intent/tool routing.

## Architecture

```
POST /agent/query {message, project_id?}
        |
        v
app.agent.router.handle_query
        |
        v
  classify_intent (app.agent.intents) -- regex/keyword rules, 7 categories
        |
        v
  extract entities (app.agent.entities) -- project_id, reporting_month,
  risk_level, segment dimension, what-if override (all regex-based)
        |
        v
  required entity missing? -> clarification response, answer_type="unsupported"
        |  (never guesses)
        v
  call exactly ONE tool (app.agent.tools) -- thin wrapper around an
  existing, already-tested HRI service:
    project  -> app.db.models (same query app.routers.projects uses)
    risk     -> app.decision_support.synthesizer.run_risk_summary
    portfolio-> app.analytics.portfolio_service.*
    document -> app.rag.retrieval.get_retrieval_service().retrieve()
    whatif   -> app.simulation.service.run_simulation
    support  -> app.agent.support_kb (static text)
        |
        v
  app.agent.synthesizer -- deterministic string templates over the
  tool's real output (no free-text generation)
        |
        v
  AgentQueryResponse {answer_type, intent, message, predictions?,
                       citations?, disclaimer?}
```

## Intent categories (`app.agent.intents`)

`project`, `risk`, `portfolio`, `document`, `whatif`, `support`,
`unsupported`. Pure `re.search` keyword/regex rules, checked in a fixed,
most-specific-first order (whatif -> support -> risk -> portfolio ->
project -> document) so an ambiguous query resolves predictably --
e.g. "Which projects have high delay risk?" contains the word "risk" but
is routed to `portfolio` (a ranked list), not `risk` (a single project's
SHAP drivers), because the risk patterns require a much more specific
"why ... risk" shape than a bare keyword. `unsupported` is the explicit,
correct result whenever nothing matches -- never a fallback guess.

## Entity extraction (`app.agent.entities`)

- `project_id`: `HRI-\d{4,}` (case-insensitive, normalized to uppercase).
- `reporting_month`: reuses `app.validation.MONTH_PATTERN` directly --
  no second regex.
- `risk_level` / segment `dimension` ("state"/"project_type"/"contractor"):
  simple keyword matches for portfolio queries.
- **What-if override parsing**: a deliberately small, explicit whitelist,
  not a general NL-to-any-feature parser. Recognizes four concepts
  (`progress`, `financial progress`, `cost`/`expenditure`, `productivity`)
  each mapped to one of `scripts.prepare_features.PREDICTOR_COLUMNS`
  (verified by a test that every mapped field is actually in that list),
  a direction word (improve/increase/rise vs. decrease/worsen/drop/fall),
  and a `N%` magnitude. Progress fields apply the percentage as an
  **additive percentage-point** delta (clipped to [0, 100]); cost/
  productivity fields apply it as a **multiplicative** percentage change.
  Anything outside this whitelist -- an unrecognized concept, a missing
  direction word, a missing `%` -- returns `None`, which the router turns
  into an honest "I couldn't understand that what-if request" response.
  This is intentionally narrower than "any of the 45 predictor columns";
  extending the whitelist is future scope, not a hidden gap.

## Tools (`app.agent.tools`)

Thin wrappers only -- every one calls straight into the module the rest
of the app already uses for that capability, and re-raises the SAME typed
exceptions (`ProjectNotFoundError`, `SnapshotNotFoundError`,
`TerminalSnapshotError`, `FeatureConstructionError`,
`InvalidOverrideFieldsError`) rather than a parallel exception hierarchy.
The one new piece of logic is `run_whatif`'s delta-to-absolute conversion:
since `run_simulation` only accepts absolute override values (never a
delta), the tool reads the project's own current baseline value for the
target field and applies the parsed what-if's `up`/`down` + magnitude to
compute the absolute value `run_simulation` requires -- the actual
simulation, validation, and model re-scoring are 100% the existing Phase
10 `run_simulation`, never reimplemented.

## Support knowledge base (`app.agent.support_kb`)

Static, hand-authored keyword -> fixed-text lookup describing this app's
own UI (add/edit/archive/reactivate a project, monthly updates,
insufficient data, model predictions, what-if, document search). Never
LLM-generated. A `DEFAULT_SUPPORT_ANSWER` fallback lists example topics
rather than guessing at an unmatched question.

## Response contract (`app.schemas.agent.AgentQueryResponse`)

`answer_type` is one of `actual` / `prediction` / `hypothetical` /
`document_evidence` / `support` / `unsupported` -- never blended. A risk
query against a terminal snapshot returns `actual` with the real
recorded outcome fields populated and the model-prediction fields left
`None` (and vice versa for a non-terminal snapshot) -- proven by a
dedicated test that neither set is ever populated at the same time. A
portfolio-overview answer, which genuinely mixes historical (actual) and
model-predicted numbers in the underlying data, is tagged `prediction` as
its single coarse `answer_type` (portfolio risk-level/segment queries are
fundamentally about the model-predicted numbers), but the rendered
`message` text itself explicitly labels which figures are "Historical
(actual, completed projects)" vs. "Model-predicted" -- the distinction is
preserved in the text even where the envelope's one tag can't carry two
categories at once. `citations` are only ever populated from a real
`RetrievalResult`/evidence chunk; an out-of-corpus document query returns
the exact same `"Not found in the available documents."` message Phase 8
already uses, with an empty citation list, never an invented source.

## Frontend

- `pages/AskHRI.jsx` (route `/ask`), reached from the Sidebar nav and
  from a "Ask HRI" button on Project Details that passes the current
  project as `?project=HRI-0006` page context (used only when the typed
  message itself doesn't name a project -- an explicit ID in the text
  always wins).
- Deliberately not styled like a general-purpose AI chat product: no
  streaming/typing animation, no assistant persona/avatar. Every assistant
  message carries a visible answer-type badge, real citations (when
  present) rendered as their own cards, and the backend's own disclaimer
  text verbatim -- never paraphrased client-side, matching the existing
  convention for every other disclaimer in this app.

## Known limitations

- What-if NL parsing only covers the whitelist above -- a request like
  "what if labour shortage triples" is honestly unsupported, not
  approximated.
- Intent classification is keyword-based and will occasionally misroute a
  genuinely ambiguous phrasing (documented rather than hidden); the
  fallback in every case is an honest clarification or "not answered",
  never a wrong answer presented as confident.
- No conversational memory across turns -- each query is classified and
  answered independently (page context is the only carried state, and
  only for `project_id`).
