# Architecture

## Scope of this document

Reflects the system as it exists at Phase 17 (commit
`c368a3d4ef6c8b2b90a6e8a8305b1908a17870b5`) — a FastAPI backend, a React
dashboard, a SQLite data layer, trained ML models with live SHAP
explainability, a local RAG pipeline, contradiction detection, a what-if
simulator, portfolio/decision intelligence, project lifecycle management,
and the "Ask HRI" deterministic query-routing agent. For exact
methodology, thresholds, and measured results behind any of these
components, see the phase-specific docs linked from
[README.md](../README.md#documentation) — this document stays at the
system/component level intentionally.

## System overview

```
┌──────────────────────┐        HTTP (fetch)         ┌───────────────────────────┐
│  frontend/            │  ─────────────────────────▶ │  backend/                  │
│  React + Vite         │   /projects, /predict,      │  FastAPI (uvicorn)         │
│  http://localhost      │  /risk-summary, /simulate,  │  http://127.0.0.1          │
│  :5173                │  /documents/search,          │  :8000                     │
│  17 routes             │  /analytics/*, /agent/query  │  11 routers                │
└──────────────────────┘  ◀───────────────────────── └───────────┬───────────────┘
                                   JSON / PDF                      │
                                                                    ▼
                                         ┌─────────────────────────────────────────┐
                                         │  SQLite (projects, project_snapshots,     │
                                         │  portfolio_prediction_cache)              │
                                         │  models/ (baseline, random_forest,        │
                                         │  xgboost joblib pipelines + metrics)      │
                                         │  rag_index/ (FAISS + embeddings +         │
                                         │  chunk-citation metadata)                 │
                                         └─────────────────────────────────────────┘
```

## Intelligence pipeline (conceptual flow)

```
Project data (synthetic dataset + user-entered projects)
        │
        ▼
Ingestion / data engineering ── PDF → text/OCR → chunks (documents)
        │                        CSV → SQLite (projects)
        ▼
Feature engineering ── leakage-audited predictor columns per project-month
        │
        ▼
ML prediction ── baseline / Random Forest / XGBoost, per-task recommended model
        │
        ▼
SHAP explainability ── live, per-instance, matched to the actual serving model
        │
        ▼
Portfolio context ── composite risk score, percentile, peer/segment comparison
        │
        ├──► RAG / document intelligence ── embeddings + FAISS, extractive
        │      citations, cross-document contradiction detection
        │
        ├──► What-if simulation ── absolute-value override + re-score
        │
        ▼
Decision intelligence ── synthesizes prediction + SHAP + RAG evidence +
                          potential inconsistencies + portfolio context
        │
        ▼
Dashboard / Ask HRI / PDF reports
```

## Backend components (`backend/app/`)

| Subpackage / router | Responsibility |
|---|---|
| `db/` | SQLAlchemy models, engine, synthetic-data loader (`loader.py` — deletes/reloads only `data_provenance=SYNTHETIC` rows, never touches user-entered projects) |
| `projects/` + `routers/project_lifecycle.py` | Create/edit/archive/reactivate a project, record monthly snapshots |
| `routers/projects.py`, `routers/predictions.py` | Read-only project/snapshot CRUD, ML prediction endpoint |
| `ml/` | Feature construction (`build_predictor_row`) and the task→model registry used by every prediction call |
| `decision_support/` | Live per-instance SHAP + per-project risk-summary synthesis |
| `rag/` | Embedding model wrapper, FAISS index builder, retrieval service, extractive answer formatting |
| `contradiction/` | Claim extraction, cross-document pairing, tolerance comparison, hedged flag generation |
| `simulation/` | What-if override validation + re-scoring against the serving models |
| `analytics/` | Batch portfolio scoring, composite risk score, segments, trends, drivers |
| `decision_intelligence/` | Combines `decision_support` + `analytics` into one project-level, portfolio-aware view |
| `agent/` | Deterministic intent classification, entity extraction, tool routing, and templated response synthesis for "Ask HRI" |
| `reports/` | ReportLab PDF generation, reusing the `decision_support` data source |
| `logging_config.py`, `validation.py`, `main.py` | Structured logging, shared `reporting_month` validation, app wiring, and the centralized exception handler |

Every router is mounted additively in `main.py` (`app.include_router(...)`)
— no router replaces another. Models and the RAG index are loaded once at
FastAPI startup and fail loudly if a required artifact is missing.

## Frontend components (`frontend/src/`)

React 19 + Vite 6 single-page app, `react-router-dom` for routing,
`recharts` for charts, plain CSS design tokens (no CSS framework).
`pages/` holds one component per route (Dashboard, Projects, ProjectForm,
ProjectDetails, RiskSummary, Simulator, DocumentSearch, Inconsistencies,
Analytics, Reports, DecisionIntelligence, AskHRI); `components/` holds
shared building blocks (risk badges, driver bars, evidence cards,
disclaimer boxes, the monthly-snapshot form, chart primitives). API calls
are centralized in `api/client.js` / `api/endpoints.js`.

## Data & model artifacts

- `data/synthetic/` — the synthetic ML training dataset (see
  [data/README.md](../data/README.md) for full provenance)
- `data/documents/raw/` — real public PDFs used by the RAG pipeline
- `data/processed/` — derived feature tables and document chunks
- `models/` — committed baseline/Random Forest/XGBoost pipelines + metrics
  JSON, for reproducibility
- `rag_index/` — committed FAISS index, embeddings, and citation metadata
- `scripts/` — one CLI per pipeline stage (dataset generation, feature
  engineering, model training, document ingestion, RAG index build,
  database load, portfolio batch scoring) — every derived artifact above
  is reproducible from committed source data via these scripts

## Why this stack (zero-cost constraint)

Every piece is free/open-source and runs entirely on the local machine —
no paid tier, no card-on-file service, per the project's zero-cost rule:

- **FastAPI + uvicorn**: free, MIT-licensed, no external service
  dependency.
- **scikit-learn / XGBoost / SHAP**: free, open-source, run entirely
  locally — no hosted ML API.
- **sentence-transformers + FAISS**: local embeddings and vector search —
  no paid embedding API, no hosted vector DB.
- **React + Vite**: free, MIT-licensed, standard for a resume-facing
  dashboard project; Vite gives fast local dev iteration.
- **pydantic-settings**: free, keeps config out of source (`.env`, not
  committed) without adding a secrets service.

## Known environment issue and resolution

`npm create vite@latest` currently scaffolds Vite 8, which ships a new
`rolldown`-based bundler. On this machine (Node v20.18.0), that build hit a
known npm optional-dependency bug
([npm/cli#4828](https://github.com/npm/cli/issues/4828)) — `vite build`
failed with "Cannot find native binding" even after the documented
`node_modules`/`package-lock.json` clean reinstall. Rather than forcing a
mismatched toolchain, the frontend is pinned to **Vite 6** +
`@vitejs/plugin-react` 4 — the mature, stable release line — which installs
and builds cleanly with no engine warnings. Still entirely free/open-source;
only the specific version differs from the tool's default scaffold.

## Local LLM feasibility

No local LLM is installed anywhere in this project. See
[local_llm_feasibility.md](local_llm_feasibility.md) for the original
hardware assessment; the same RAM-pressure finding was independently
re-measured and reconfirmed when RAG (Phase 8) and Ask HRI (Phase 17)
each separately considered and declined enabling one. Both the RAG answer
mode and Ask HRI are deterministic/extractive by design, not a
disclosed-but-worked-around limitation.

## Deployment status

This system runs **locally only**. There is no configured Git remote, no
CI/CD pipeline, no deployment target, and no live demo URL. See the main
[README.md](../README.md#roadmap) for what is explicitly deferred.
