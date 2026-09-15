# Highway Risk Intelligence

A **prototype decision-support system inspired by highway infrastructure
project monitoring** — a portfolio/resume project, not an official NHAI or
government system, and not affiliated with NHAI/MoRTH.

Combines (planned across phases): tabular ML for delay-risk and cost-overrun
prediction with SHAP explainability, document-grounded RAG with citations
over public highway-sector PDFs, cross-document contradiction detection, a
what-if scenario simulator, and an executive-style AI synthesis layer — all
built under a strict **zero-cost constraint** (no paid APIs, no paid hosting,
no paid datasets).

## Status: Phase 14 complete (portfolio-level analytics with historical/predicted separation)

Phase 1 delivered the project skeleton: a FastAPI backend, a React/Vite
frontend, and a verified health-check connection between them — see
[docs/architecture.md](docs/architecture.md), and
[docs/local_llm_feasibility.md](docs/local_llm_feasibility.md) for the
local-LLM hardware assessment.

Phase 2 adds the data foundation for later ML work: a reproducible
synthetic highway-project monthly-snapshot generator
([scripts/generate_dataset.py](scripts/generate_dataset.py)), a validation
pipeline ([scripts/validate_dataset.py](scripts/validate_dataset.py)), and a
metadata manifest of real public infrastructure documents — see
[data/README.md](data/README.md) for what the data is and where it came
from, and [docs/DATASET_REPORT.md](docs/DATASET_REPORT.md) /
[docs/SYNTHETIC_DATA_METHODOLOGY.md](docs/SYNTHETIC_DATA_METHODOLOGY.md)
for the dataset's statistics and generation methodology.

Phase 3 adds EDA and leakage-safe feature engineering
([scripts/eda_report.py](scripts/eda_report.py),
[scripts/prepare_features.py](scripts/prepare_features.py)) — see
[docs/EDA_REPORT.md](docs/EDA_REPORT.md) and
[docs/FEATURE_ENGINEERING.md](docs/FEATURE_ENGINEERING.md).

Phase 4 adds the first ML baseline and a reusable, leakage-safe
train/validation/test framework: a project-level chronological split
([scripts/data_split.py](scripts/data_split.py)) and Dummy/Logistic/Linear
baseline models for all four prediction tasks
([scripts/train_baseline_models.py](scripts/train_baseline_models.py)).
See [docs/TRAIN_VAL_TEST_STRATEGY.md](docs/TRAIN_VAL_TEST_STRATEGY.md) for
the split methodology and [docs/BASELINE_MODEL_REPORT.md](docs/BASELINE_MODEL_REPORT.md)
for the full baseline results (performance on the synthetic prototype
dataset only).

Phase 5 adds Random Forest and XGBoost models for all four tasks, trained
and evaluated on the identical frozen Phase 4 split
([scripts/train_tree_models.py](scripts/train_tree_models.py)), plus SHAP
explainability for the strongest tree model per task
([scripts/explain_models.py](scripts/explain_models.py)). Tree models beat
the Phase 4 baseline for 2 of 4 tasks (delay classification, delay
regression); the Phase 4 baseline remains the honestly recommended model
for the other 2 (cost classification, cost regression), where tree models
did not improve on it. **No prediction API, dashboard integration, RAG, or
LLM inference is implemented yet.** See
[docs/MODEL_COMPARISON_REPORT.md](docs/MODEL_COMPARISON_REPORT.md) for the
full comparison (including overfitting analysis and suspicious-performance
checks) and [docs/SHAP_EXPLAINABILITY_REPORT.md](docs/SHAP_EXPLAINABILITY_REPORT.md)
for the explainability results (performance/explanations on the synthetic
prototype dataset only).

Phase 6 adds a SQLite data layer and a FastAPI ML prediction service, with
**no new modeling** — it exposes the frozen Phase 2 dataset and the
already-trained Phase 4/5 models via HTTP. `scripts/load_db.py` loads
`data/synthetic/highway_project_snapshots.csv` into `projects` /
`project_snapshots` tables (SQLAlchemy models in
[backend/app/db/models.py](backend/app/db/models.py)); read-only CRUD
endpoints (`GET /projects`, `/projects/{id}`, `/projects/{id}/snapshots`,
`/projects/{id}/snapshots/{reporting_month}`) and a prediction endpoint
(`GET /projects/{id}/predict`) were added to the existing FastAPI app. The
prediction endpoint uses the Phase 5-recommended model per task (Random
Forest for delay classification, XGBoost for delay regression, and the
Phase 4 baseline for both cost tasks — verified against
[docs/MODEL_COMPARISON_REPORT.md](docs/MODEL_COMPARISON_REPORT.md), not
assumed) and returns recorded actual outcomes instead of a prediction for
terminal snapshots. See [docs/API_AND_DATABASE.md](docs/API_AND_DATABASE.md)
and [docs/MODEL_SERVING.md](docs/MODEL_SERVING.md). **No RAG, SHAP-serving,
dashboard/frontend integration, authentication, or what-if simulator is
implemented yet.**

Phase 7 adds a reusable PDF ingestion pipeline
([scripts/ingest_documents.py](scripts/ingest_documents.py)) that turns the
real public highway-sector PDFs under `data/documents/raw/` into a
citation-ready, chunk-level dataset
(`data/processed/document_chunks.csv`): PyMuPDF native-text extraction,
a documented pdfplumber table-aware fallback, a Tesseract OCR fallback
(genuinely exercised on real scanned/image pages in the corpus, not just
implemented), best-effort heading detection, and deterministic
paragraph/sentence-aware chunking. Three additional real government PDFs
(CAG, NHAI, MoRTH) were downloaded in this phase, verified byte-exact
against their HTTP `Content-Length`; two PIB press releases remain
unavailable (blocked by bot-protection, and not direct PDF links regardless
— see [docs/DOCUMENT_INGESTION.md](docs/DOCUMENT_INGESTION.md)). **This
phase produces a chunk dataset only — no embeddings, vector store,
retrieval, or LLM integration is implemented yet.**

Phase 8 adds local embeddings + a FAISS vector index over the Phase 7 chunk
dataset, with a **required, zero-LLM extractive** answer mode as the
default (`scripts/build_rag_index.py`, `backend/app/rag/`):
`sentence-transformers/all-MiniLM-L6-v2` (free, local, 384-dim, CPU-only)
embeds all 861 usable chunks (0 excluded — Phase 7 already drops truly empty
OCR pages before they become chunk rows; `suspicious_text`/`low_ocr_quality`
chunks are kept and flagged, not dropped), indexed with an exact
`faiss.IndexFlatIP` (cosine similarity via inner product on L2-normalized
vectors — no approximate index, the corpus is far too small to need one). A
relevance threshold of 0.35 (empirically chosen — see
[docs/RAG_SYSTEM.md](docs/RAG_SYSTEM.md) section 9) separates genuine
in-corpus matches from out-of-corpus queries, which correctly return `"Not
found in the available documents."` instead of a fabricated answer. A local
LLM was evaluated and **not enabled** — measured free RAM (~1-1.8 GB of
15.69 GB total) was well below the phase's stated comfort threshold; see
[docs/RAG_SYSTEM.md](docs/RAG_SYSTEM.md) section 19. **No contradiction
detection, what-if simulator, decision-support synthesis, or dashboard/
frontend integration is implemented yet.**

Phase 13 adds real server-side project search (`GET /projects?q=...`,
performed in SQL, replacing the Phase 12 frontend's client-side search over
a pre-fetched full project list), genuine backend-generated PDF reports
(`GET /projects/{id}/report.pdf`, built with ReportLab from the same
`run_risk_summary` data/service the on-screen Reports/AI Risk Summary pages
already use -- no second prediction/SHAP/RAG pipeline), and a focused
production-hardening pass. See [docs/PHASE_13.md](docs/PHASE_13.md) for the
full contract, a real bug found and fixed along the way, and known
limitations.

## Prerequisites

- Python 3.11+ (developed/tested with 3.12.4 in a local venv)
- Node.js 20+ and npm
- Git

## Backend setup

```bash
cd backend
python -m venv .venv
./.venv/Scripts/pip install -r requirements.txt
./.venv/Scripts/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Backend runs at `http://127.0.0.1:8000`. Check `/health`.

Run backend tests:

```bash
cd backend
./.venv/Scripts/python -m pytest -v
```

## Frontend setup

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at `http://localhost:5173` and calls the backend's `/health`
endpoint on load, displaying live connection status.

## Configuration

Copy `.env.example` to `.env` in the repo root (backend) and/or in
`frontend/` as needed — see each `.env.example` for the variables used.
Phase 1 requires no API keys or paid services of any kind.

## Hardware check / local LLM feasibility

```bash
cd scripts
../backend/.venv/Scripts/python hardware_check.py
```

Reports real measured CPU/RAM/disk specs, used to ground the local-LLM
feasibility assessment in [docs/local_llm_feasibility.md](docs/local_llm_feasibility.md).

## Data foundation (Phase 2)

```bash
cd scripts
../backend/.venv/Scripts/python.exe generate_dataset.py
../backend/.venv/Scripts/python.exe validate_dataset.py
```

Regenerates the synthetic dataset at
`data/synthetic/highway_project_snapshots.csv` (fixed seed, reproducible)
and runs the validation pipeline against it. See
[data/README.md](data/README.md) for provenance,
[docs/DATASET_REPORT.md](docs/DATASET_REPORT.md) for dataset statistics,
and [docs/SYNTHETIC_DATA_METHODOLOGY.md](docs/SYNTHETIC_DATA_METHODOLOGY.md)
for how it's generated (including leakage prevention).

## Feature engineering (Phase 3)

```bash
cd scripts
../backend/.venv/Scripts/python.exe eda_report.py
../backend/.venv/Scripts/python.exe prepare_features.py
```

Regenerates `docs/EDA_REPORT.md`'s figures and
`data/processed/{delay,cost}_features.csv`. See
[docs/FEATURE_ENGINEERING.md](docs/FEATURE_ENGINEERING.md) for the feature
dictionary.

## Baseline models (Phase 4)

```bash
cd scripts
../backend/.venv/Scripts/python.exe train_baseline_models.py
```

Runs the project-level leakage-safe split, trains Dummy/Logistic/Linear
baselines for all four tasks, and writes
`models/metrics/baseline_metrics.json` and the fitted pipelines under
`models/baseline/`. See
[docs/TRAIN_VAL_TEST_STRATEGY.md](docs/TRAIN_VAL_TEST_STRATEGY.md) and
[docs/BASELINE_MODEL_REPORT.md](docs/BASELINE_MODEL_REPORT.md).

## Tree models and SHAP explainability (Phase 5)

Run from the repo root (these two scripts import `scripts.*` as a package,
so they must be run with `-m`, unlike the `cd scripts` scripts above):

```bash
./backend/.venv/Scripts/python.exe -m scripts.train_tree_models
./backend/.venv/Scripts/python.exe -m scripts.explain_models
```

Trains Random Forest + XGBoost for all four tasks on the identical frozen
Phase 4 split, writes `models/metrics/tree_metrics.json` and the fitted
pipelines under `models/random_forest/` / `models/xgboost/`, then generates
SHAP global summary plots and local (high/low-prediction) waterfall plots
under `docs/artifacts/`. See
[docs/MODEL_COMPARISON_REPORT.md](docs/MODEL_COMPARISON_REPORT.md) and
[docs/SHAP_EXPLAINABILITY_REPORT.md](docs/SHAP_EXPLAINABILITY_REPORT.md).

Run the full test suite (from the repo root):

```bash
./backend/.venv/Scripts/python.exe -m pytest -v
```

## SQLite data layer and prediction API (Phase 6)

Load the database (idempotent — safe to re-run; clears and reloads both
tables from the CSV each time):

```bash
./backend/.venv/Scripts/python.exe -m scripts.load_db
```

Start the API (same command as Phase 1 — the existing app was extended,
not replaced):

```bash
cd backend
./.venv/Scripts/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Starting the API before the database has been loaded is fine — the tables
are created automatically and CRUD endpoints just return empty results —
but if a required Phase 4/5 model artifact under `models/` is missing, the
app refuses to start (with a clear error naming the missing file) rather
than substituting another model.

Try it: `GET /projects`, `GET /projects/HRI-0001`,
`GET /projects/HRI-0001/snapshots`,
`GET /projects/HRI-0001/predict?reporting_month=2023-04`, or open
`http://127.0.0.1:8000/docs` for interactive Swagger docs. See
[docs/API_AND_DATABASE.md](docs/API_AND_DATABASE.md) for the full schema
and endpoint reference and [docs/MODEL_SERVING.md](docs/MODEL_SERVING.md)
for the model-serving design.

## Document ingestion pipeline (Phase 7)

Requires Tesseract OCR installed and on `PATH` (or at the default Windows
install path) for the OCR fallback to run — install the free, open-source
[UB-Mannheim Tesseract build](https://github.com/UB-Mannheim/tesseract)
(`winget install --id UB-Mannheim.TesseractOCR -e` on Windows). Ingestion
still runs without it for documents that never need OCR, but raises a
clear error if a page actually requires OCR and Tesseract is unavailable.

```bash
./backend/.venv/Scripts/python.exe -m scripts.ingest_documents
```

Reads `data/documents/metadata.csv`, verifies every catalogued PDF is
present under `data/documents/raw/`, and writes
`data/processed/document_chunks.csv`. See
[docs/DOCUMENT_INGESTION.md](docs/DOCUMENT_INGESTION.md) for the extraction
heuristics (PyMuPDF primary, pdfplumber table-aware fallback, Tesseract OCR
fallback), the chunking strategy, and the actual run statistics.

## RAG retrieval (Phase 8)

Build the local FAISS index (skips regeneration if the source chunk CSV and
embedding model are unchanged — pass `--force` to rebuild anyway):

```bash
./backend/.venv/Scripts/python.exe -m scripts.build_rag_index
```

Writes `rag_index/document_chunks.faiss`, `rag_index/embeddings.npy`, and
`rag_index/metadata.json` (the full vector-to-chunk citation mapping).
These files are small (~1.3 MB each) and are committed to the repo for
reproducibility, same as the Phase 4/5 model artifacts.

Start the API (same command as Phase 1/6 — the existing app was extended,
not replaced) and query it:

```bash
cd backend
./.venv/Scripts/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

```
GET /documents/search?q=<your question>&top_k=5
```

Try it, e.g.:
`GET /documents/search?q=How much money has NHAI raised through the InvIT mode?`
or open `http://127.0.0.1:8000/docs` for interactive Swagger docs. See
[docs/RAG_SYSTEM.md](docs/RAG_SYSTEM.md) for the full pipeline, threshold
rationale, test-question methodology, and the local-LLM decision.

## Frontend dashboard (Phase 12)

A full React/Vite dashboard (`frontend/`) branded **HRI — Highway Risk
Intelligence** ("PREDICT DELAYS • CONTROL COSTS") now sits in front of the
Phase 1-11 backend: Dashboard, Projects, Project Details, AI Risk Summary,
What-if Simulator, Document Search, Inconsistencies, Analytics, and Reports.
Every number shown comes from a real backend call (no hard-coded mockup
data); hedged wording ("potential inconsistency requiring verification",
"illustrative, not a recommendation") is preserved verbatim from the
backend, never rewritten client-side. One small, purely additive backend
endpoint was added for this phase — `GET /analytics/summary`
(`backend/app/routers/analytics.py`) — a read-only SQL aggregate over the
existing `projects`/`project_snapshots` tables for portfolio-wide KPI/chart
data that no Phase 1-11 endpoint exposed; no existing endpoint or ML/RAG/
contradiction/simulator logic was changed. See
[docs/FRONTEND_DASHBOARD.md](docs/FRONTEND_DASHBOARD.md) for the full
architecture, design system, and browser-verification results.

Run both servers locally:

```bash
cd backend
./.venv/Scripts/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

```bash
cd frontend
npm run dev
```

Then open `http://127.0.0.1:5173`.

## Project search and PDF reports (Phase 13)

Search is a real backend query parameter -- no separate script to run.
Start the API and frontend as in Phase 12, then:

```
GET /projects?q=<text>&page=1&page_size=20
```

Try it, e.g. `GET /projects?q=kerala` or from the Projects page's search
box (debounced, sent to the backend on every change). Download a real PDF
report from the Reports page's "Download PDF Report" button, or directly:

```
GET /projects/HRI-0006/report.pdf?reporting_month=2022-12
```

See [docs/PHASE_13.md](docs/PHASE_13.md) for the full `q` contract, PDF
contents, terminal-snapshot behavior, and hardening changes.

Run the full test suite (from the repo root, includes Phase 13's new
search and PDF tests):

```
./backend/.venv/Scripts/python.exe -m pytest -v
./backend/.venv/Scripts/python.exe -m pytest backend -v
```

```bash
cd frontend
npm run test
```

## Portfolio-level analytics (Phase 14)

Portfolio-wide risk intelligence, always kept structurally separate into
HISTORICAL / ACTUAL (recorded outcomes) and CURRENT MODEL-PREDICTED
(model output from each project's latest non-terminal snapshot). Start the
API and frontend as in Phase 12/13, then generate the prediction cache
once (batch-scores all eligible projects; re-run after the dataset or
model artifacts change):

```
./backend/.venv/Scripts/python.exe -m scripts.batch_score_portfolio
```

Then explore the new endpoints, e.g.:

```
GET /analytics/portfolio
GET /analytics/risk-projects?risk_level=CRITICAL
GET /analytics/segments?dimension=contractor
GET /analytics/drivers
GET /analytics/trends
```

Or visit the extended Analytics page in the frontend. See
[docs/ADVANCED_ANALYTICS.md](docs/ADVANCED_ANALYTICS.md) for the full
architecture, risk-score formula, minimum-sample rules, and real measured
example numbers.

## Project layout

See [docs/architecture.md](docs/architecture.md).

## License / disclaimer

Educational/portfolio project. Not affiliated with, endorsed by, or
representing NHAI, MoRTH, or any government body. Any data used in later
phases will be clearly labeled as real (public source cited) or synthetic —
never presented as official.
