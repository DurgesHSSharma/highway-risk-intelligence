# Phase 16 — Production Readiness & Quality Gate

This phase is a **hardening and verification pass** over the existing
Phase 1–15 system, not a feature phase. No ML retraining, no RAG rebuild,
no database migration, no new paid services, no deployment work (that is
Phase 17). Every fix below addresses a concrete, verified gap found by
reading the actual code and exercising the actual running app — nothing
here was fixed speculatively.

## 1. Audit method

Two read-only reconnaissance passes (frontend state-handling + API client;
database integrity + dependency versions) were run first, followed by a
direct code audit of backend configuration, logging, exception handling,
`reporting_month` validation across every router, ML/RAG artifact
resilience, and security posture. Every finding below was reproduced
(a real request against a real running `uvicorn` process, or a real
`pytest`/`TestClient` run) before being called a "gap" — see each
section for the reproduction.

## 2. Confirmed gaps fixed this phase

### 2.1 No structured logging (Section 10)

Before this phase, `backend/app/` had zero `logging` calls anywhere.
Added `backend/app/logging_config.py` (stdlib `logging` only, no new
dependency): one `StreamHandler` to stdout, `INFO` level, idempotent
`configure_logging()`. `app/main.py` now logs INFO on startup begin/
complete, and `logger.exception(...)` (full traceback, to the log only —
never the HTTP response) on a startup initialization failure or an
unhandled request exception. Never logs request bodies, secrets, or
credentials — only identifiers and exception messages.

### 2.2 No centralized exception handler (Section 11)

**Reproduced before fixing**: with `app.dependency_overrides` forcing
`get_db` to raise a plain `RuntimeError`, a real request to `GET /projects`
returned `500 text/plain "Internal Server Error"` — Starlette's own
default `ServerErrorMiddleware` behavior when no handler is registered.
Inconsistent content-type vs. every other endpoint (`application/json`),
and the real exception was never logged anywhere (only ever visible via
uvicorn's own stderr dump, if a process supervisor even kept it).

**Fix**: `@app.exception_handler(Exception)` in `app/main.py` logs the
real exception server-side and returns a fixed, safe
`{"detail": "Internal server error."}` at `500` with `application/json`.
This handler is registered for the generic `Exception` class, which
Starlette routes to `ServerErrorMiddleware` (the outermost layer) — it
does **not** shadow FastAPI's own `HTTPException`/`RequestValidationError`
handling (those are matched first via exception-class MRO lookup), so
404/422/etc. are unaffected. Verified with `TestClient(app,
raise_server_exceptions=False)` — this flag is required to observe the
handler's actual HTTP response in a test, because Starlette's
`ServerErrorMiddleware` always re-raises the original exception after
sending the response (intentional upstream behavior, so process-level
tools still see it); a real client (browser, curl, uvicorn) only ever
sees the JSON response. Tests: `backend/tests/test_error_handling.py`.

### 2.3 Inconsistent `reporting_month` validation (Section 12)

**Reproduced before fixing**: of the six places a `reporting_month` is
accepted, only `reports.py` validated it at the request layer (via
`Query(..., pattern=...)`), and even that pattern (`^\d{4}-\d{2}$`)
accepted an out-of-range month like `2025-13`. `predictions.py`,
`simulation.py`, `decision_support.py`, and `decision_intelligence.py`
accepted a bare `str`, so a malformed value fell through to a 404
("no snapshot found") instead of a 422 ("malformed input") — the wrong
status code for the wrong reason, and inconsistent with the rest of the
API's contract for the same parameter name.

**Fix**: one shared pattern, `app/validation.py::MONTH_PATTERN =
r"^\d{4}-(0[1-9]|1[0-2])$"`, applied via `Query(..., pattern=...)` (or
`Path(..., pattern=...)` for `projects.py`'s
`/{project_id}/snapshots/{reporting_month}` path parameter) in all six
places. Tests: `backend/tests/test_reporting_month_validation.py`
(parametrized over `"2025"`, `"2025-9"`, `"2025/09"`, `"abc"`,
`"2025-99"`, `"2025-00"`, `"2025-13"`, and `""`, across all five routers
plus the path parameter; also asserts well-formed values still work).

### 2.4 Three frontend sections missing error/retry wiring (Section 19)

A dedicated read-only frontend audit found the shared `AsyncSection` +
`useApi` pattern (loading/error/empty/retry) already covers the large
majority of the app correctly, but three call sites passed `data`/
`status` without also passing `error`/`onRetry`, silently degrading to a
generic, retry-less "Unable to load data." on failure:

- `Dashboard.jsx` — Sample Projects table (backed by
  `ProjectsCacheContext`, which already exposes `error`/`reload`; just
  not destructured/passed through).
- `Analytics.jsx` — the Risk Matrix section (its own higher-limit
  `useApi` call, `riskMatrix`, already had `.error`/`.reload`).
- `Analytics.jsx` — the Predicted Trend chart and the bottom Project
  Length/Contract Value Distribution section (same omission pattern).

**Fix**: wired the already-available `error`/`onRetry` through in all
four call sites — no new state, no new component, no redesign. Verified
live in the browser (see §4) and with new tests:
`frontend/src/pages/Dashboard.test.jsx` (new file — Dashboard had no
tests before this phase) and two new tests in
`frontend/src/pages/Analytics.test.jsx`.

### 2.5 Mobile horizontal-overflow regression on Analytics (Section 20)

**Found during live 375px browser verification** (not by inspection
alone): `/analytics` overflowed horizontally by 22px
(`scrollWidth: 397` vs. `clientWidth: 375`) at mobile width. Root cause:
`.card` (used inside `.stack`, a column flexbox, and `.two-col-grid`, a
CSS grid) had no `min-width: 0`. Both flexbox and grid items default to
`min-width: auto`, meaning a flex/grid item refuses to shrink below its
content's intrinsic width — so the Segment Analytics table's own
`.table-scroll` wrapper (which does have `overflow-x: auto` and was
already used correctly, e.g. on Dashboard's Sample Projects table) never
got the chance to activate; the whole page grew instead. The Segment
Analytics table (8 columns) is the widest table in the app, which is why
this specific card was the one that manifested it — other pages' tables
fit within 375px without needing to shrink.

**Fix**: added `min-width: 0` to `.card` in
`frontend/src/styles/global.css` (the same fix already applied to
`.app-main` at the top-level layout, for the identical reason). Verified
in the browser: `scrollWidth === clientWidth === 375` on `/analytics`
afterward, and the Segment Analytics/Top Risk tables now correctly
scroll horizontally *within* their own `.table-scroll` box
(`scrollWidth: 1120`/`1392` vs. `clientWidth: 302`, confirmed via
`getBoundingClientRect`/DOM inspection, not a screenshot — this pane has
a known compositing artifact at non-desktop widths, already documented
in Phases 14/15). All 10 routes re-checked clean at 375px after the fix.
This is a CSS-only layout fix with no meaningful way to assert
`scrollWidth`/`clientWidth` in `happy-dom` (it doesn't perform real
layout), so it is verified by live browser inspection here, not a unit
test — consistent with how the Phase 15 mobile CSS fix was verified.

## 3. Audited and found already solid (no change made)

- **Configuration** (Section 9): `backend/app/config.py`'s `Settings`
  class has 7 fields; `.env.example` already documents all of them
  (`APP_ENV`, `CORS_ORIGINS`, `DATABASE_PATH`, `DATASET_CSV_PATH`,
  `MODELS_DIR`) with placeholder values, no secrets, and `.env`/
  `.env.local` are already in `.gitignore`. No changes needed.
- **Database integrity** (Section 14): audited via a dedicated read-only
  pass over `backend/app/db/{models,base,loader}.py`. SQLite foreign-key
  enforcement is genuinely turned on per-connection (a real
  `PRAGMA foreign_keys=ON` `event.listens_for(engine, "connect")` hook in
  `base.py`, not just declared in the ORM). `ProjectSnapshot` has a real
  DB-level `UniqueConstraint(project_id, reporting_month)`.
  `PortfolioPredictionCache.project_id` has `unique=True` (one row per
  project, enforced). The loader's clear-and-reload runs inside one
  transaction with `rollback()` on any exception (interruption never
  leaves a half-deleted/half-inserted state). Every equality/group-by
  column an actual router query touches (`state`, `project_type`,
  `project_status`, `is_terminal_snapshot`, `project_id`,
  `reporting_month`) already has an index. No missing index, no
  unenforced constraint found. No changes made.
- **ML artifact resilience** (Section 15): `app/ml/registry.py::load_models`
  already fails loudly (raises `ModelArtifactMissingError`, aborting
  startup) if any Phase 4/5 model artifact is missing or the path is
  wrong — verified live by starting the real server (§4). Never
  substitutes a different model, never fabricates a prediction.
- **RAG resilience** (Section 16): `app/rag/retrieval.py::load_retrieval_service`
  fails loudly (`RagIndexNotBuiltError`) if the FAISS index/embeddings/
  metadata are missing, or if their row counts are inconsistent with each
  other. `RetrievalService.retrieve` rejects an empty/whitespace-only
  query or `top_k < 1` (`InvalidQueryError` → 422). Out-of-corpus queries
  return the fixed `"Not found in the available documents."` string,
  never a fabricated answer (unchanged Phase 8 behavior, re-verified
  live). `ShapArtifactMissingError` (Phase 14's portfolio SHAP artifact)
  degrades gracefully in Decision Intelligence's driver-alignment
  comparison (portfolio side comes back `None`/empty, live side is
  unaffected) rather than 500ing the whole endpoint — this was already
  correct Phase 15 behavior, re-verified, not touched.
- **Input validation elsewhere** (Section 13): pagination (`page`,
  `page_size`) already has `ge=1`/`le=settings.max_page_size` bounds.
  `/documents/search`'s `q` already has `min_length=1` and `top_k` is
  bounded `[1, 20]`; a whitespace-only `q` is separately rejected by
  `RetrievalService.retrieve` itself (422). No gap found.
- **Security baseline** (Section 17): no path-traversal surface (no
  endpoint accepts a filesystem path or filename from a caller — RAG
  results and PDF reports are served from an in-memory index/generated
  bytes, never a user-supplied path). No SQL-injection surface (every
  query goes through SQLAlchemy's parameterized query builder; the one
  free-text `ILIKE` search escapes `%`/`_`/the escape character itself).
  No `eval`/`exec`/`subprocess`/`os.system` anywhere in `backend/app/`.
  See §5 for the auth/rate-limiting/TrustedHost/HTTPS decision and the
  one noted (unreachable) transitive dependency advisory.
- **Frontend API client** (Section 18): `frontend/src/api/client.js`
  already handles network failure, non-2xx status, malformed/non-JSON
  bodies, and all three shapes of FastAPI's `detail` field (string,
  pydantic validation list, structured object) — unit-tested in
  `client.test.js`. No retry logic exists and none was added (retrying a
  non-idempotent `POST /simulate` automatically would be unsafe; a GET
  retry isn't needed for a local single-user dev tool). No timeout was
  added — not clearly useful for a local backend on the same machine.
- **Dependency audit** (Section 22): every pinned backend version in
  `requirements.txt` matches what's actually installed (76 packages,
  checked via `pip list --format=freeze`). `pip-audit` is not installed
  in the venv and was not installed to check (per the zero-blind-install
  rule) — no automated backend CVE scan was run. `npm audit --json` ran
  clean: `0` vulnerabilities across all 261 frontend dependencies
  (prod + dev + optional + peer). One transitive advisory is known by
  inspection, not audited: `starlette` is pinned to `0.38.6` by
  `fastapi==0.115.0`, and versions before `0.40.0` have a disclosed
  multipart/form-data DoS (GHSA-2c2j-9gv5-cj73). This app has **no**
  `UploadFile`/`File(...)` endpoint anywhere (confirmed by grep), so the
  vulnerable code path is not reachable through this API. Documented
  here rather than silently upgraded — bumping `fastapi` is not "minimal"
  (it would pull in other transitive changes needing a full regression)
  and isn't justified by an unreachable vector; revisit if a file-upload
  endpoint is ever added.
- **Line-ending drift** (Section 8): verified twice, from two different
  angles, with a corrected methodology the second time. `git status
  --short`/`git diff --stat` for every file the master prompt named as
  historically affected show **zero** diff — the working tree already
  matches `HEAD`. A first pass that piped `git show HEAD:<path>` through
  a shell `grep -c $'\r'` appeared to find CRLF in every line of these
  files, but that turned out to be a false positive caused by MSYS/Git
  Bash's text-mode pipe translation on Windows silently reinserting `\r`
  bytes into piped output — not a property of the actual git blob.
  Re-verified with Python's `subprocess.run(capture_output=True)`
  reading the *raw bytes* git actually wrote (bypassing any shell pipe),
  across all 264 tracked text files (`.py`/`.js`/`.jsx`/`.json`/`.csv`/
  `.md`/`.css`/`.html`/`.svg`/`.ini`/`.txt`/`.example`/`.gitignore`):
  **zero contain a `\r` byte anywhere in their committed HEAD blob.**
  The repository's stored content was already 100% LF; only the
  *working tree* (what's checked out on this Windows machine, under
  `core.autocrlf=true`) displays CRLF, which is normal, expected,
  invisible to any other clone, and not drift. `git add --renormalize`
  correctly staged zero changes for the same reason: there was nothing
  to renormalize. `.gitattributes` (LF normalization for tracked text
  files, explicit binary markers for `.png`/`.joblib`/`.pdf`/`.npy`/
  `.faiss`) was still added, as a forward-looking hardening measure so
  this stays true regardless of any future contributor's own
  `core.autocrlf` setting — not because content drift was found.

## 4. Live verification performed this phase

Real backend (`uvicorn`, port 8000) and real frontend (`vite`, port
5173) were started for real (never just `TestClient`/unit tests) against
the real committed dataset/models/RAG index/DB.

**API smoke** (all `200`, real data, `HRI-0006`/`2022-12` non-terminal
unless noted): `GET /health`, `GET /projects`, `GET /projects/HRI-0006`,
`GET /projects/HRI-0006/predict`, `GET /projects/HRI-0006/risk-summary`,
`GET /projects/HRI-0006/decision-intelligence`, `GET /analytics/summary`,
`GET /analytics/portfolio`, `GET /documents/search`,
`GET /documents/inconsistencies`, `POST /projects/HRI-0006/simulate`,
`GET /projects/HRI-0006/report.pdf` (returned a real 14,055-byte PDF).

**Invalid-input smoke** (all safe, correct status, no traceback/path/
secret leakage): malformed `reporting_month` (`2025-99`) → `422`;
unknown project (`HRI-9999`) → `404`; negative `page` → `422`; oversized
`page_size` → `422`; missing required `reporting_month` → `422`; unknown
simulator override field → `422` with the existing structured
`invalid_fields` detail; empty search `q` → `422`.

**Frontend smoke**, all 10 routes (`/`, `/projects`,
`/projects/HRI-0006`, `/projects/HRI-0006/risk-summary`,
`/projects/HRI-0006/simulator`, `/documents`, `/inconsistencies`,
`/analytics`, `/reports/HRI-0006`,
`/projects/HRI-0328/decision-intelligence`): loaded with real data, zero
console errors, zero horizontal overflow at 1280/768/375px (after the
§2.5 fix). `HRI-0328`/`2025-08` (the real CRITICAL example from Phase 15)
reproduced live: 100.0th percentile, 543-day predicted delay, 100% cost-
overrun probability. Terminal-snapshot rendering re-verified
(`HRI-0006`/`2023-06`: "Recorded final outcome", not a live prediction).
The Risk Matrix scatter (the Phase 14 15→100 point fix) re-verified
still rendering 100 points.

Note: the app has no literal `/dashboard` route — `/` **is** the
dashboard (an intentional, pre-existing design, confirmed in
`frontend/src/App.jsx`); navigating to `/dashboard` correctly renders the
app's own `NotFound` page rather than crashing. Not a Phase 16 change.

## 5. Security baseline decision (Section 17) — documented, not defaulted

For this local, single-user, student/portfolio MVP:

- **Authentication**: not added. There is no multi-tenant data and no
  sensitive user data; adding auth would be complexity with no present
  benefit and no user story requiring it.
- **HTTPS redirect**: not added. The app is served over plain HTTP on
  `localhost` for local development; a redirect makes no sense without a
  TLS-terminating reverse proxy, which is a deployment concern.
- **Rate limiting**: not added. No abuse vector currently exists (no
  auth, no per-user quotas, no metered external cost — everything is
  local compute against a local SQLite DB and a local FAISS index).
- **`TrustedHostMiddleware`**: not added. It defends against Host-header
  attacks on a service reachable over an untrusted network; this app is
  bound to `127.0.0.1` for local development and has no such exposure
  today.

All four are explicitly **deferred to Phase 17** (deployment), where the
actual reverse-proxy/hosting model will determine which of these are
actually needed (e.g., `TrustedHostMiddleware` once a real public
hostname exists). This is a documented decision, not an oversight.

## 6. Files changed this phase

New: `.gitattributes`, `backend/app/logging_config.py`,
`backend/app/validation.py`, `backend/tests/test_error_handling.py`,
`backend/tests/test_reporting_month_validation.py`,
`frontend/src/pages/Dashboard.test.jsx`, `docs/PRODUCTION_READINESS.md`.

Modified: `backend/app/main.py` (logging + global exception handler),
`backend/app/routers/{predictions,simulation,decision_support,
decision_intelligence,reports,projects}.py` (shared `reporting_month`
pattern), `frontend/src/pages/{Dashboard,Analytics}.jsx` (error/retry
wiring), `frontend/src/pages/Analytics.test.jsx` (2 new tests),
`frontend/src/styles/global.css` (`.card { min-width: 0 }`), `README.md`.
