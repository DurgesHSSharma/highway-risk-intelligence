# Phase 13 — Backend Search, Real PDF Reports, Production Hardening

**This is a prototype decision-support system inspired by highway
infrastructure project monitoring, built on a SYNTHETIC dataset -- it is
not an official NHAI system.** See
[SYNTHETIC_DATA_METHODOLOGY.md](SYNTHETIC_DATA_METHODOLOGY.md).

## 1. Scope

Phase 13 is exactly three things, over the frozen Phase 1-12 backend/
frontend:

1. Real, server-side (SQL) search on `GET /projects`, replacing the Phase
   12 frontend's client-side search over a pre-fetched full project list.
2. Genuine backend-generated PDF reports (ReportLab), downloadable from the
   Reports page.
3. A focused production-hardening pass (validation, error handling, a real
   performance bug found and fixed).

No authentication, no new ML models, no changes to Phase 4/5 modeling,
SHAP, RAG, contradiction detection, or simulator methodology. No Phase 14
work.

## 2. Backend search: `GET /projects?q=...`

### Contract

```
GET /projects?q=<text>&page=<n>&page_size=<n>&state=<s>&project_type=<t>&project_status=<st>
```

- `q` (optional): case-insensitive, partial-match search performed in SQL
  (SQLite, via `.ilike()`), OR-ed across the fields below. Leading/trailing
  whitespace is stripped; an empty or whitespace-only `q` behaves exactly
  like omitting it (backward compatible with every pre-Phase-13 call).
- Searchable fields (`backend/app/routers/projects.py::SEARCHABLE_COLUMNS`):
  `project_id`, `project_name`, `highway_number`, `state`, `contractor`,
  `project_type`. This is the brief's candidate list filtered to columns
  that actually exist on `Project` -- there is no `highway` column, the
  real one is `highway_number` (see `backend/app/db/models.py`).
- `%`/`_`/`\` inside `q` are escaped before being wrapped in `%...%`, so a
  literal search term can't be misread as a SQL LIKE pattern.
- `q` composes with the existing `state`/`project_type`/`project_status`
  filters via AND (all filters apply together, in SQL, before counting or
  paginating).
- Pagination (`page`/`page_size`) is applied **after** filtering, exactly
  like the pre-existing filters -- `total` in the response reflects the
  filtered count, not the full portfolio.
- A search with no matches returns `{"items": [], "page": 1, "page_size":
  ..., "total": 0}` -- a valid empty response, not an error.

### Tests

`backend/tests/test_projects_api.py` adds 19 new tests: no-search backward
compatibility, exact/partial ID match, name match, highway match, state
match, contractor match, case-insensitivity, whitespace handling (padded
and whitespace-only), empty string, no-result search, search combined with
each existing filter, search-then-paginated, and invalid-pagination (page
0, page_size 0, page_size over the configured max).

### Frontend

`frontend/src/pages/Projects.jsx` was rewritten to call `GET /projects`
directly with `{page, page_size, q, state, project_type, project_status}`
on every relevant change -- it no longer reads from
`ProjectsCacheContext` for its table data, and the search input is
debounced (300ms) so fast typing doesn't fire one request per keystroke.
Changing the search text or any filter resets to page 1 batched into the
*same* state update as the filter change itself (not a separate reactive
effect -- see "A real bug found" below). A small "×" button clears the
search and its `?q=` URL param.

`ProjectsCacheContext` itself is **unchanged** -- Dashboard and Analytics
still use it for client-side histograms/sample rows the `/analytics/
summary` endpoint doesn't provide, and it already hydrates once per app
load regardless of which page is open. The Projects page still reads it,
but **only** to populate the State/Project Type/Status filter dropdown
*option lists* (distinct values to choose from) -- never to filter or
search the displayed rows, which always come from a fresh, real `GET
/projects` call.

`ProjectPicker` (the small "jump to a project" widget embedded in the
Risk Summary / Simulator / Reports pages when no project is selected) was
**deliberately left unchanged** -- it's a distinct top-25-suggestions
widget, not "the Projects search feature" the brief describes, and
touching it would expand scope beyond what was asked.

**Known, disclosed behavior change:** the Phase 12 Projects page had a
"Sort by" dropdown that re-sorted the entire (client-side, fully-fetched)
filtered list before paginating. With pagination now happening in SQL, the
frontend only ever holds one page of rows at a time, so a "sort by
contract value" control could only reorder the ~20 rows currently on
screen -- not the whole portfolio -- which would be misleading. The sort
control was removed rather than kept in a misleading, page-local form;
results are returned in the backend's stable `project_id` order (unchanged
from Phase 6).

## 3. Real PDF reports

### Architecture

```
GET /projects/{id}/report.pdf?reporting_month=YYYY-MM
        |
        v
app.reports.report_data.build_report_data()
        |          \
        v           \-- reuses app.decision_support.synthesizer.run_risk_summary()
Project + ProjectSnapshot   (the EXACT function GET .../risk-summary calls --
   rows (existing           predictions, live SHAP, RAG evidence, potential
   ORM models)              inconsistencies, illustrative scenario)
        \           /
         v         v
    app.reports.pdf_builder.build_report_pdf()
        |
        v
   ReportLab / reportlab.platypus -> PDF bytes
```

`reportlab==5.0.1` is the only new dependency (`backend/requirements.txt`).
No jsPDF, html2canvas, browser-screenshot-to-PDF, WeasyPrint, or external
PDF API is used -- the PDF is a genuine document built server-side from
`reportlab.platypus` flowables (`Paragraph`/`Table`/`SimpleDocTemplate`).

**No second prediction/SHAP/RAG pipeline was created.** The PDF and the
on-screen Reports/AI Risk Summary pages are backed by the same
`run_risk_summary()` call and the same `Project`/`ProjectSnapshot` rows --
`app/reports/report_data.py` only reads and reshapes, it recomputes
nothing.

### Endpoint

```
GET /projects/{project_id}/report.pdf?reporting_month=YYYY-MM
```

- `reporting_month` must match `^\d{4}-\d{2}$` (422 otherwise); a
  well-formed month with no matching snapshot returns 404, matching the
  existing `/predict`/`/simulate`/`/risk-summary` 404 convention.
- Unknown `project_id` -> 404. A non-terminal snapshot whose feature row
  can't be built -> 422 (`FeatureConstructionError`, same as `/predict`).
- Response: `Content-Type: application/pdf`,
  `Content-Disposition: attachment; filename="<project_id>_<reporting_month>_HRI_report.pdf"`.

### PDF contents

HRI branding, project identity (ID/name/highway/state/type/contractor),
reporting month and status, planned-vs-actual physical/financial progress,
full cost breakdown, full delay-day breakdown, all 4 model prediction
outputs (hedged wording, identical sentences to the on-screen risk
summary), live per-instance SHAP drivers (or the exact skip reason),
RAG evidence with citations, potential inconsistencies (hedged, "requires
verification" wording), the illustrative what-if scenario (or the exact
skip reason), and all 7 disclaimers (system identity, ML limitation,
causality/non-causal-scenario, evidence limitation, inconsistency
limitation, synthetic-data). A field the backend doesn't have for that
snapshot (e.g. `actual_expenditure_inr_cr` on the ~3.8% of snapshots
missing it) renders as "Not available", never a fabricated value.

### Terminal snapshot rule

For a terminal snapshot (`is_terminal_snapshot=true`), the PDF shows
**recorded actual outcomes**, never a forward-looking prediction -- the
Model Prediction Outputs section states "Recorded actual outcome" (not
"Live model prediction"), the SHAP section shows the exact
`shap_skipped_reason` text instead of fabricating drivers, and the
scenario section shows the exact `scenario_skipped_reason` text instead of
fabricating a what-if scenario. This is identical logic to the existing
`GET .../risk-summary` terminal branch (Phase 11 repair) -- the PDF
builder doesn't decide terminal-vs-live itself, it only renders what
`run_risk_summary()` already returns.

### A real bug found and fixed during implementation

ReportLab's built-in Helvetica font uses WinAnsiEncoding (~cp1252), which
does **not** include the ₹ (Indian Rupee, U+20B9) glyph -- an early draft
rendered "₹ Cr" labels with a garbled character in place of ₹ (verified by
extracting the generated PDF's text with PyMuPDF and inspecting it, not
just eyeballing a screenshot). Fixed by dropping the symbol and labeling
these fields "(Cr)", matching the convention the Phase 12 frontend itself
already uses in the Projects table header and Analytics histograms (only
one helper, `utils/format.js`'s `formatCurrency`, used the ₹ symbol, and
it's not used on any page this report mirrors). No font-embedding
dependency was added to work around this.

### Tests

`backend/tests/test_report_pdf.py` (22 tests) parses the generated PDF
with **PyMuPDF (`fitz`)** -- already a Phase 7 dependency for PDF
ingestion, so no new PDF-parsing dependency was added. Covers: HTTP status,
`Content-Type`, non-zero/PDF-signature body, a downloadable filename,
successful parsing by a real local parser, the project ID and reporting
month appearing in the extracted text, real project/snapshot field values
appearing in the text, the PDF's prediction sentences matching the live
`GET .../risk-summary` response byte-for-byte (proving same data source),
disclaimers present, the live-SHAP section present for a non-terminal
snapshot, the full terminal-snapshot rule (recorded-outcome wording, SHAP
skip reason, scenario skip reason, no "Live model prediction" text),
missing-project 404, malformed-month 422, well-formed-but-nonexistent-month
404, missing-param 422, and no raw stack trace in an error body.

### Frontend

Reports page gained a **"Download PDF Report"** button
(`frontend/src/pages/Reports.jsx`) that calls the new endpoint via
`apiGetBlob` (`frontend/src/api/client.js`), builds an object URL from the
returned `Blob`, and triggers a real file download through a
programmatically-clicked `<a download>` -- never `window.print()`. Loading
("Generating PDF…", button disabled), success, and error (inline message
with the backend's real error text) states are all handled; the object URL
is revoked after the click. The pre-existing `window.print()` button is
kept alongside it (still useful for a quick on-screen view), per the
brief's "the previous print functionality may remain" allowance.

## 4. Production hardening

- **Reporting-month format validation** added to the new PDF endpoint
  (`Query(..., pattern=r"^\d{4}-\d{2}$")`) -- not retrofitted onto the
  existing `/predict`/`/simulate`/`/snapshots/{month}` endpoints, since
  changing their existing (looser) contract would be an undisclosed
  behavior change to frozen Phase 6/10/11 endpoints, not a Phase 13
  concern.
- **SQL injection / LIKE-wildcard safety**: search input is escaped
  (`%`, `_`, `\`) before being used in an `ILIKE` pattern; the query itself
  is fully parameterized via SQLAlchemy (no string-built SQL anywhere).
- **A real frontend performance bug found and fixed**: the first draft of
  the Projects page's page-reset-on-search-change logic used a separate
  `useEffect` reacting to the debounced query. Because that effect runs one
  render after the debounce timer's own `setDebouncedQuery` call, `useApi`
  fired an extra, avoidable backend request at the *stale* page number
  before a second request corrected it to page 1 whenever the user searched
  while on page 2+ -- caught by a frontend test asserting on the actual
  sequence of `listProjects` calls, not just the final rendered result.
  Fixed by resetting the page in the *same* state-update scope as each
  filter change (the debounce timeout callback, or each select's `onChange`)
  so React batches them into one render and one request.
- **Error response shape**: the new endpoints reuse the existing
  `HTTPException(status_code=..., detail=str(...))` convention used
  throughout Phases 6-11 -- predictable JSON error bodies, never a raw
  Python traceback (verified by a dedicated test).
- **CORS/config/secrets**: unchanged and re-reviewed -- `cors_origins`
  stays restricted to the local dev origins, no new environment variables
  or secrets were introduced, `.env`/`.gitignore` need no changes.
- Frontend: Projects and Reports pages now cover loading/error/empty
  states end-to-end for their new backend calls (see sections above);
  `apiGetBlob` mirrors `apiGet`'s existing JSON-error-body parsing so a
  failed PDF request surfaces the backend's real message, not a generic
  fetch error.

## 5. Dependencies

- **Added**: `reportlab==5.0.1` (`backend/requirements.txt`) -- PDF
  generation. Free/open-source (BSD), zero-cost, no external service.
- **No new test dependency**: PDF-parsing tests reuse `PyMuPDF`
  (`fitz`), already installed for Phase 7 document ingestion -- adding
  `pypdf` as well was considered and judged unnecessary.
- No other dependency was upgraded, downgraded, or removed.

## 6. Testing summary (real measured results)

Pre-flight baseline (confirmed before any Phase 13 change): 159 root +
206 backend + 29 frontend = **394 passed, 0 failed**.

Final, after Phase 13 (all three suites re-run from a clean state):

| Suite | Baseline | New (Phase 13) | Final | Failed | Skipped |
|---|---|---|---|---|---|
| Root (`pytest -q`) | 159 | 0 | 159 | 0 | 0 |
| Backend (`pytest backend -q`) | 206 | 41 (19 search + 22 PDF) | 247 | 0 | 0 |
| Frontend (`npm run test`) | 29 | 13 | 42 | 0 | 0 |
| **Total** | **394** | **54** | **448** | **0** | **0** |

Root gained no new tests because Phase 13 touched only `backend/` and
`frontend/` -- there was no change to the root-level data/ML pipeline
scripts the root suite covers, so re-running it is a pure regression check
(and it passed unchanged).

## 7. Known limitations

- Search is a simple `ILIKE`-based partial match, not a ranked/fuzzy/
  full-text search -- adequate for a ~400-row portfolio, not intended to
  scale to a much larger real dataset without a proper full-text index.
- The Projects page's former "Sort by" control was removed (see section 2)
  rather than kept as a misleading page-local sort.
- The PDF's visual design is functional, not a polished print-shop
  template -- it prioritizes complete, correctly-sourced content over
  layout polish.
- `ProjectPicker`'s own project-lookup search (used by Risk Summary/
  Simulator/Reports when no project is pre-selected) still does a small
  client-side filter over the cached ~400-project list; it was out of
  scope for this phase (see section 2).

This remains a prototype/decision-support system using synthetic project
data and a small real public-document corpus -- not an official NHAI
system, and not validated against real highway-project outcomes.
