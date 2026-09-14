# Frontend Dashboard (Phase 12)

Phase 12 is frontend/dashboard integration only: it turns the already-built
Phase 1-11 backend intelligence (ML predictions, live SHAP, RAG, contradiction
detection, the what-if simulator, the decision-support synthesizer) into a
polished, working web application. No ML retraining, no RAG/contradiction/
simulator redesign, and no change to Phase 6 prediction or Phase 11
decision-support behavior was made.

## Branding

- Product name: **HRI — Highway Risk Intelligence**
- Tagline: **PREDICT DELAYS • CONTROL COSTS**
- Visual identity: dark navy sidebar (`--navy-900`/`--navy-800` gradient),
  light analytics workspace (`--bg`/`--surface`), blue primary actions
  (`--blue-600`/`--blue-700`), and semantic risk colors (green/amber/red for
  low/medium/high) — see `frontend/src/styles/theme.css`.
- Logo: a local, dependency-free inline SVG mark (`frontend/src/components/Logo.jsx`)
  combining a highway curve with an ascending analytics bar. No external
  image URL or logo service is used.

## Zero-cost stack

Everything is free/open-source, installed locally via `npm`:

- **React 19 + Vite 6** (Vite pinned to 6, same Node 20.18/rolldown
  incompatibility documented in [architecture.md](architecture.md) since
  Phase 1)
- **react-router-dom 7** — client-side routing
- **recharts 3** — the only charting library, code-split into its own
  chunk (see "Performance" below) so pages that don't chart never load it
- **vitest 4 + @testing-library/react + happy-dom** — frontend testing
  (see "Testing")
- Hand-authored inline SVG icons (`frontend/src/components/icons.jsx`) — no
  icon library/service
- Plain CSS with custom properties (`frontend/src/styles/`) — no Tailwind,
  no CSS-in-JS, no UI component library

No paid APIs, maps, chart services, icon services, authentication,
analytics, or hosting are used anywhere.

## Architecture

```
frontend/src/
├── api/            client.js (fetch wrapper, error parsing), endpoints.js (one function per backend route)
├── hooks/          useApi.js (loading/success/error/idle data-fetching), useProjectSnapshots.js
├── context/        ProjectsCacheContext.jsx (hydrates all projects once per session)
├── layout/         AppLayout, Sidebar, Topbar
├── components/     shared UI: KpiCard, RiskBadge, DisclaimerBox, StateViews (loading/error/empty),
│                   ProjectPicker, MonthSelect, ProgressBar, DriverBar, EvidenceResultCard,
│                   InconsistencyCard, PredictionTiles, Pagination, charts/
├── pages/          Dashboard, Projects, ProjectDetails, RiskSummary, Simulator, DocumentSearch,
│                   Inconsistencies, Analytics, Reports, NotFound
├── utils/          format.js, snapshots.js, simulatorFields.js, palette.js, histogram.js
└── styles/         theme.css (design tokens), global.css (component styles + responsive rules)
```

`api/client.js` is the **single** place that calls `fetch()` — every page
goes through `api/endpoints.js`, which has one typed-by-JSDoc function per
backend route actually implemented in `backend/app/routers/*.py`. Error
bodies from FastAPI (plain string `detail`, pydantic validation-error
arrays, and the simulate endpoint's `{message, invalid_fields}` object) are
all normalized into one `ApiError` with a human-readable `.message`.

## Routes

| Path | Page | Notes |
|---|---|---|
| `/` | Dashboard | Portfolio KPIs + charts |
| `/projects` | Projects | Client-side search/filter/sort/paginate over the full cached project list |
| `/projects/:projectId` | Project Details | Info, monthly-snapshot selector, progress, cost, delay factors |
| `/risk-summary`, `/projects/:projectId/risk-summary` | AI Risk Summary | Project-picker landing, or the full risk summary for a project+month |
| `/simulator`, `/projects/:projectId/simulator` | What-if Simulator | Same picker pattern |
| `/documents` | Document Search | RAG search |
| `/inconsistencies` | Inconsistencies | Phase 9 report |
| `/analytics` | Analytics | Portfolio-wide charts |
| `/reports`, `/reports/:projectId` | Reports | Print-friendly risk-summary report |
| `*` | NotFound | |

Every page component is lazy-loaded (`React.lazy` + `Suspense` in
`App.jsx`) for route-level code splitting.

## Backend integration

All 10 pre-existing Phase 1-11 endpoints are used exactly as documented in
their own phase docs, with no request/response shape changes:

`GET /health`, `GET /projects`, `GET /projects/{id}`,
`GET /projects/{id}/snapshots`, `GET /projects/{id}/snapshots/{month}`,
`GET /projects/{id}/predict`, `POST /projects/{id}/simulate`,
`GET /documents/search`, `GET /documents/inconsistencies`,
`GET /projects/{id}/risk-summary`.

**One new endpoint was added**: `GET /analytics/summary`
(`backend/app/routers/analytics.py` + `backend/app/schemas/analytics.py`).
No existing Phase 1-11 endpoint returns portfolio-wide aggregate counts
(total projects, status/state/type distribution, significant-delay/
cost-overrun counts), and computing them client-side would require one
HTTP call per project (400 calls) on every Dashboard/Analytics load. This
endpoint runs a few cheap SQL `GROUP BY`/aggregate queries over the
existing `projects`/`project_snapshots` tables (populated by the unmodified
Phase 6 loader) — no ML inference, no RAG, no contradiction detection, no
simulator logic. 6 new backend tests
(`backend/tests/test_analytics_api.py`) cover it, including the known,
already-disclosed data property that every project's *current* status is
"Completed" (`status_counts == {"Completed": 400}`).

The `ProjectsCacheContext` hydrates the full 400-project list once per
session (4 paginated `GET /projects` calls, since `page_size` maxes at
100), shared by Dashboard/Projects/Analytics — this is what backs the
Projects page's client-side search, since `GET /projects` has no free-text
query parameter and building one client-side over a small (400-row)
already-fetched set is the only non-fabricated way to support search.

## Demo-data / synthetic-data disclaimer

The dataset is 400 synthetic projects (documented in
[SYNTHETIC_DATA_METHODOLOGY.md](SYNTHETIC_DATA_METHODOLOGY.md)). **No
mockup numbers from the original design brief were hard-coded anywhere** —
every KPI, chart, and table value is computed from a real backend response.
The `synthetic_data_disclaimer` / `corpus_disclaimer` / Phase 11
`disclaimers` object returned by the backend is always rendered on-page
(never hidden behind a tooltip), via the shared `DisclaimerBox` component.

## Hedged wording preserved verbatim

The frontend never rewrites or paraphrases the backend's hedged language.
The Inconsistencies and AI Risk Summary pages always render Phase 9's
`"Potential inconsistency requiring verification"` phrasing and Phase
9/11's disclaimer text exactly as returned — the app never uses "confirmed
contradiction"/"confirmed error"/"false"/"wrong"/"incorrect". The Simulator
and the Risk Summary's illustrative-scenario section always show the exact
Phase 10 disclaimer string and label the scenario "Illustrative, not a
recommendation".

## Error / loading / empty states

Every API-driven section goes through the shared `AsyncSection` component
(`components/StateViews.jsx`), which renders exactly one of: loading
(spinner + label), error (message + Retry button that re-runs the same
request), empty (explicit title/message — e.g. "Not found in the available
documents.", "No potential inconsistencies surfaced for this evidence.",
"No projects match your filters."), or the real content. A project 404
renders `ProjectDetails`'s/`RiskSummary`'s/`Simulator`'s own explicit
not-found state, not a blank screen. Terminal snapshots get a dedicated
informational message on the Simulator page (rather than attempting the
POST and showing a raw 422) and a dedicated `shap_skipped_reason`/
`scenario_skipped_reason` rendering on the Risk Summary page.

## Responsive design

Breakpoints (in `styles/global.css`): 1180px (2-column KPI/chart grids),
860px (sidebar becomes an off-canvas drawer behind a hamburger button, with
a dimming backdrop; the top search bar hides), 640px (single-column
KPI/chart grids). Tables scroll horizontally in their own container rather
than the page. Verified live in the browser at desktop (1280px), tablet
(768px, `resize_window` preset), and mobile (375px, `resize_window`
preset) — no horizontal page overflow, sidebar drawer opens/closes
correctly with backdrop, filter bars wrap, KPI cards stack.

## Accessibility

Semantic HTML (`<nav>`, `<main>`, `<table>`, real `<button>`/`<a>`
elements), labeled form controls (every `<select>`/`<input>` has an
associated `<label>`), `aria-current="page"` on the active sidebar link,
`role="status"`/`role="alert"` on loading/error states, visible focus
rings (`:focus-visible`). Risk status is always color **+** an icon **+**
text label (`RiskBadge`), never color alone.

## Testing

29 new frontend tests across 10 files (`vitest run`), covering: API client
error-parsing (string/array/object-shaped FastAPI error bodies, network
failure), shared loading/error/empty state components, sidebar navigation
links, risk-bucket thresholds, Projects page rendering/search/empty-state,
Project Details rendering and 404 handling, Document Search result
rendering and the exact "Not found in the available documents." message,
Inconsistencies hedged wording (and that "confirmed error"/"confirmed
contradiction" never appear), AI Risk Summary rendering for both a
non-terminal snapshot (live SHAP drivers, RAG citations, illustrative
scenario) and a terminal snapshot (`shap_skipped_reason`/
`scenario_skipped_reason` shown instead of fabricated data), and the
Simulator's terminal-snapshot message plus a full override-and-run flow.

`jsdom` (Vite/vitest's default DOM environment) could not be used: its
`@asamuzakjp/css-color` dependency requires an ESM-only
`@csstools/css-calc` build via `require()`, which crashes under both the
"forks" and "threads" vitest pools on this machine's Node 20.18 — the same
class of toolchain mismatch as the Vite 8 rolldown issue documented in
[architecture.md](architecture.md). Switched to `happy-dom` (also free,
open-source), which has no such dependency chain.

Run: `cd frontend && npm run test`

## Real browser verification (performed, not just build success)

Both servers were started for real (`uvicorn app.main:app` on :8000, `vite`
dev server on :5173) and driven with a real browser:

- **Dashboard**: real KPIs (400 total projects — not the design brief's
  mockup 250 — 0 ongoing with the disclosed reason shown inline, 197
  significant-delay/49.3%, 153 cost-overrun/38.3%), donut charts, state/type
  bar charts, sample-projects table — all confirmed via live network
  requests to `/analytics/summary` and `/projects`.
- **Projects**: full list loaded (4×100-row paginated fetch), search
  filtered correctly (e.g. "Bangalore" → only HRI-0019), empty-filter state
  shown correctly.
- **Project Details — HRI-0006**: real project data (`NH-698 Greenfield
  Highway Package 8`, Telangana), month selector populated with all 22
  snapshots through the terminal one (June 2023), progress/cost/delay-factor
  sections rendered, terminal-snapshot notice shown for the last month.
- **AI Risk Summary — HRI-0006 / 2022-12** (the mandated project+month):
  live predictions (94.7% significant-delay probability, 95-day predicted
  delay, 9.9% cost-overrun probability, 6.4% predicted cost overrun), 4
  live per-instance SHAP driver panels (RandomForest/XGBoost/
  LogisticRegression/LinearRegression, each with its own `TreeExplainer`/
  `LinearExplainer` semantics text), 2 RAG evidence queries with real
  document citations (`[DOC-004, p. 7]` etc.), 0 potential inconsistencies
  for this evidence (rendered as an explicit non-error empty state), an
  illustrative `progress_efficiency` what-if scenario, and all 7
  disclaimers visible.
- **AI Risk Summary — HRI-0006 / 2023-06 (terminal snapshot)**: verified
  against real database data — `prediction_status="actual_outcome"`,
  recorded outcome badges (Yes/92 days/No/2.8%, matching the Project
  Details page's own terminal-snapshot section exactly), SHAP section shows
  the exact `shap_skipped_reason` text instead of fabricated drivers, and
  the scenario section shows the exact `scenario_skipped_reason` text
  instead of a fabricated scenario.
- **What-if Simulator — HRI-0006 / 2022-12**: overriding
  `contractor_productivity_factor` from its recorded 0.874 to 0.5 and
  running the simulation moved predicted delay from 95→123 days and
  cost-overrun probability from 9.9%→28.9% — directionally consistent with
  the documented EDA correlation and the Phase 10 completion report's own
  real-server smoke test. Applied-overrides table, no extrapolation
  warnings (0.5 is within the training range), both disclaimers shown.
- **What-if Simulator — terminal snapshot**: confirmed it shows the exact
  informational "Simulation is unavailable for this snapshot..." message
  instead of a form, with no "Run Simulation" button present.
- **Document Search**: a real in-corpus example question (from
  `tests/fixtures/rag_test_questions.json`, not invented for the UI)
  returned the correct citation (`[DOC-001, p. 60]`, similarity 0.79,
  matching the ~0.786 documented in RAG_SYSTEM.md); an out-of-corpus
  question ("recipe for chocolate cake") correctly returned "Not found in
  the available documents."
- **Inconsistencies**: the real 3 flagged Bharatmala-outlay findings
  documented in Phase 9's memory/report rendered correctly with hedged
  wording, confidence, and normalized values.
- **Analytics**: portfolio totals/averages, both outcome donuts, full
  state/project-type bar charts, and length/contract-value histograms all
  rendered from real data.
- **Reports — HRI-0006 / 2022-12**: print-friendly single-page report
  combining project info + risk overview + recommended reviews +
  disclaimers; the Print button calls `window.print()` (no fake PDF
  download).
- **Console/network**: no console errors on any page. The only
  `net::ERR_ABORTED` network entries are React 19 StrictMode's dev-only
  double-effect invocation (each is immediately followed by a successful
  retry of the identical URL) — not a real failure.
- **Responsive**: verified at 1280px (desktop), 768px (tablet preset), and
  375px (mobile preset) — sidebar collapses to a hamburger-triggered
  drawer with backdrop, no horizontal page overflow, filter bars and KPI
  grids reflow to fewer columns.
- **Backend regression**: all 10 pre-existing endpoints plus the new
  `/analytics/summary` returned `200` against the live server (see the
  command list in this phase's completion report).

A bug was found and fixed during this verification: the sidebar's active
route highlighting used React Router's default prefix matching, so
`/projects/:id/risk-summary` and `/projects/:id/simulator` (which share
the `/projects/...` prefix) incorrectly highlighted "Projects" instead of
"AI Risk Summary"/"What-if Simulator". Fixed with explicit per-item
`isActive(pathname)` predicates in `Sidebar.jsx` instead of relying on
prefix matching.

## Known limitations

- The Projects page's search/sort/filter/pagination is entirely
  client-side over a session-cached full project list, because `GET
  /projects` has no free-text search parameter. This is fine at 400
  projects; it would not scale to a much larger portfolio without a real
  backend search endpoint.
- "Ongoing Projects" is always 0 given the current dataset — an
  already-disclosed property of the synthetic generator (every project's
  trajectory runs to completion), not a frontend bug; the KPI card shows
  this explicitly rather than hiding or explaining it away.
- The What-if Simulator exposes a curated subset of the 45 valid predictor
  columns (the 10 delay-factor fields, contractor productivity, and the 4
  progress-percentage fields) rather than all 45 — chosen because the
  remaining fields are either identifiers/targets (not valid overrides at
  all) or engineered/derived columns (e.g. `recent_progress_trend_3m`)
  that are valid backend overrides but not meaningful things for a human
  reviewer to hypothesize about directly.
- No authentication, no real-time updates/polling, no PDF export (the
  Reports page is print-friendly via the browser's own print dialog, not a
  generated PDF file).
