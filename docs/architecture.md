# Architecture (Phase 1)

## Scope of this document

Reflects what exists after Phase 1 only: a minimal backend/frontend skeleton
with a health check. It intentionally does **not** describe ML, RAG, or
scenario-simulation components — those are Phase 2+ and are not implemented.

## System overview

```
┌─────────────────────┐        HTTP (fetch)        ┌──────────────────────┐
│   frontend/          │  ───────────────────────▶  │   backend/            │
│   React + Vite       │   GET /health, GET /        │   FastAPI (uvicorn)   │
│   http://localhost   │  ◀───────────────────────  │   http://127.0.0.1    │
│   :5173              │        JSON response        │   :8000               │
└─────────────────────┘                              └──────────────────────┘
```

- **Frontend** (`frontend/`): React + Vite single-page app. On load, calls
  the backend's `/health` endpoint and renders the connection status. No
  routing/state library yet — deliberately minimal for Phase 1.
- **Backend** (`backend/`): FastAPI app with two endpoints (`/` and
  `/health`), CORS configured for the Vite dev origin, settings loaded via
  `pydantic-settings` from an optional `.env` file.
- **No database, no ML models, no RAG index yet** — these are out of scope
  for Phase 1 by explicit instruction.

## Directory layout

```
highway-risk-intelligence/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py        # FastAPI app, CORS, /, /health
│   │   └── config.py      # pydantic-settings Settings
│   ├── tests/
│   │   └── test_health.py # pytest + FastAPI TestClient
│   ├── requirements.txt
│   ├── pytest.ini
│   └── .venv/              # local virtualenv (not committed)
├── frontend/
│   ├── src/
│   │   ├── App.jsx         # health-check UI
│   │   ├── App.css
│   │   ├── index.css
│   │   └── main.jsx
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
├── docs/
│   ├── architecture.md          (this file)
│   └── local_llm_feasibility.md
├── scripts/
│   └── hardware_check.py
├── .env.example
├── .gitignore
└── README.md
```

## Why this stack (zero-cost constraint)

Every piece is free/open-source and runs entirely on the local machine — no
paid tier, no card-on-file service, per the project's zero-cost rule:

- **FastAPI + uvicorn**: free, MIT-licensed, no external service dependency.
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

See [local_llm_feasibility.md](local_llm_feasibility.md) for the measured
hardware assessment. No LLM runtime is installed in Phase 1.

## What's explicitly deferred to Phase 2+

- ML models (delay-risk classification, delay-duration regression,
  cost-overrun prediction) and SHAP explainability
- RAG pipeline over highway-sector PDFs with citations
- Cross-document contradiction detection
- What-if scenario simulator
- Executive decision-support synthesis layer
- Any local LLM installation/inference
