# HRI — Highway Risk Intelligence

**PREDICT DELAYS • CONTROL COSTS**

HRI is a full-stack decision-support prototype for highway infrastructure
project monitoring. It combines tabular ML (delay-risk and cost-overrun
prediction with SHAP explainability), a document-grounded retrieval system
over real public highway-sector PDFs, cross-document contradiction
detection, a what-if scenario simulator, portfolio-level analytics, and a
deterministic natural-language query interface ("Ask HRI") — all served by
a FastAPI backend and a React dashboard, built entirely under a **zero-cost
constraint** (no paid APIs, no paid hosting, no paid datasets, no credit
card required anywhere in the stack).

> **This is an independent research/portfolio prototype inspired by
> highway infrastructure monitoring and risk-analysis workflows. It is
> NOT an official NHAI product, not an official government system, not an
> official NHAI prediction service, and not affiliated with or endorsed by
> NHAI, MoRTH, or any government body.** See [Disclaimer](#license--disclaimer)
> for the full statement.

## Why This Project

Public sources confirm highway infrastructure delay and cost overrun is a
real, large-scale problem in India — for example, real aggregate
statistics such as "697 projects were delayed as of July 2024" and "35%
of delays are attributed to land acquisition" are documented and cited in
[docs/SYNTHETIC_DATA_METHODOLOGY.md](docs/SYNTHETIC_DATA_METHODOLOGY.md).
However, no publicly available dataset provides a rich, per-project
**monthly** time series with a consistent schema across hundreds of
projects — the shape of data needed to train and demonstrate supervised ML
models. HRI was built to explore what a decision-support system over that
kind of data could look like end-to-end: ML prediction, explainability,
document-grounded evidence, scenario simulation, and portfolio-level
synthesis, as a single coherent, testable system — not a single notebook
or a single model.

It exists primarily as a **resume/portfolio engineering project**,
demonstrating full-stack ML system design, leakage-safe evaluation
methodology, retrieval-augmented generation without a paid LLM, and
honest, disclosed handling of synthetic data and known limitations.

## Core Capabilities

**Highway project lifecycle management**
- Create, edit, archive, and reactivate projects (non-destructive —
  archiving never deletes data)
- Record monthly progress snapshots for a real project over time
- Read-only synthetic demonstration data and user-entered real projects
  coexist safely (the data loader only ever touches synthetic rows)

**Delay & cost-overrun prediction**
- 4 prediction tasks: significant-delay classification, delay-duration
  (days) regression, cost-overrun classification, cost-overrun-percentage
  regression
- Project-level **chronological** train/validation/test split (no random
  row split — see [Model & Evaluation Methodology](#model--evaluation-methodology))
- Dummy/Logistic/Linear baselines, Random Forest, and XGBoost trained and
  honestly compared per task — the simpler baseline is kept as the
  recommended model wherever the tree models didn't actually improve on it
- Live, per-instance SHAP explanations computed against the exact model
  serving each prediction (not a static, pre-computed artifact)

**Document intelligence (RAG)**
- PDF ingestion: native text extraction, a table-aware fallback, and a
  Tesseract OCR fallback for scanned/image pages
- Deterministic paragraph/sentence-aware chunking
- Local sentence-transformer embeddings + an exact FAISS similarity index
  (no approximate index — the corpus is small)
- Grounded **extractive** answers only — verbatim source text with a
  document/page citation, or an explicit "not found" response; no LLM
  paraphrasing or generation
- Correct out-of-corpus handling (an empirically-set relevance threshold
  separates genuine matches from unrelated queries)

**Cross-document contradiction detection**
- Regex-based extraction of currency/percentage/date/count claims from
  document text
- Embedding-based candidate pairing + context-aware tolerance comparison
- Flags are always reported as "**potential inconsistency requiring
  verification**", never as a confirmed error in either source

**What-if scenario simulator**
- Re-scores a real project snapshot through the same serving models with
  one or more feature values overridden
- Absolute-value overrides only (no implicit deltas); rejects invalid
  fields and out-of-training-range values with an explicit warning

**Decision support & decision intelligence**
- Per-project synthesis combining live prediction, live SHAP drivers,
  RAG evidence, potential inconsistencies, and an illustrative (not
  causal) what-if scenario
- Portfolio context: composite risk score, percentile ranking, and
  peer comparison across state / project type / contractor

**Portfolio analytics**
- Historical (actual, completed-project) statistics kept structurally
  separate from current model-predicted risk — never blended
- Risk distribution, segment analytics (state/project-type/contractor,
  with a minimum-sample rule to avoid misleading small-cohort comparisons),
  portfolio-wide SHAP drivers, and trend charts

**Reporting**
- Genuine backend-generated PDF reports (ReportLab) built from the same
  data/service the on-screen Risk Summary page uses — no separate
  pipeline

**Ask HRI**
- A **deterministic** natural-language query-routing interface over the
  capabilities above — see [Limitations](#limitations) for what it is and
  is not, and [docs/ASK_HRI_AGENT.md](docs/ASK_HRI_AGENT.md) for the full
  design

**Dashboard**
- A responsive React single-page app covering all of the above (verified
  at desktop, tablet, and mobile widths)

## System Architecture

```
Project data (synthetic dataset + user-entered projects)
        │
        ▼
Ingestion / data engineering  ── PDF ingestion (OCR fallback) for documents
        │                         feature engineering for ML
        ▼
Feature engineering  ── leakage-audited predictor columns, rolling/derived features
        │
        ▼
ML prediction  ── baseline / Random Forest / XGBoost, per-task recommended model
        │
        ▼
SHAP explainability  ── live, per-instance, matched to the actual serving model
        │
        ▼
Portfolio context  ── composite risk score, percentile, peer/segment comparison
        │
        ├──────────────► RAG / document intelligence  ── embeddings + FAISS,
        │                  extractive citations, contradiction detection
        │
        ├──────────────► What-if simulation  ── override + re-score
        │
        ▼
Decision intelligence  ── synthesizes prediction + SHAP + RAG + inconsistencies
        │                   + portfolio context into one project-level view
        ▼
Dashboard / Ask HRI / PDF reports  ── React frontend, deterministic query
                                        router, ReportLab reports
```

Backend: FastAPI app (`backend/app/`) with 11 routers, backed by SQLite
(`projects` / `project_snapshots` / `portfolio_prediction_cache` tables),
trained model artifacts under `models/`, and a FAISS index under
`rag_index/`. Frontend: a React + Vite single-page app (`frontend/src/`)
with 13 page components across 17 routes. See [docs/architecture.md](docs/architecture.md) for the
full component breakdown and directory layout.

## Technology Stack

| Layer | Technology |
|---|---|
| Backend | Python, FastAPI, uvicorn, Pydantic / pydantic-settings |
| Database | SQLite via SQLAlchemy 2.0 |
| ML | scikit-learn, XGBoost, SHAP, pandas, numpy |
| Document processing | PyMuPDF, pdfplumber, Tesseract OCR (via pytesseract) |
| Retrieval | sentence-transformers (local embeddings), FAISS |
| Reporting | ReportLab (PDF generation) |
| Frontend | React 19, Vite 6, React Router 7, Recharts |
| Testing | pytest + httpx (backend), Vitest + Testing Library (frontend) |

Every dependency is free and open-source; nothing requires an API key,
billing account, or paid tier.

## Data & Provenance

Every dataset in this repository is explicitly labeled by provenance —
see [data/README.md](data/README.md) for the authoritative breakdown.
Three distinct kinds of data are used, and they are never conflated:

1. **Synthetic structured ML data** — `data/synthetic/highway_project_snapshots.csv`
   (400 projects, monthly snapshots), generated by
   [scripts/generate_dataset.py](scripts/generate_dataset.py) with a fixed
   random seed. Every row carries `data_provenance=SYNTHETIC`. **This data
   does not represent real NHAI/MoRTH project records** — it is a
   simulation calibrated against real aggregate public statistics (see
   [docs/SYNTHETIC_DATA_METHODOLOGY.md](docs/SYNTHETIC_DATA_METHODOLOGY.md)),
   generated because no public dataset provides a rich, per-project
   monthly time series suitable for supervised ML training.
2. **Real public infrastructure documents** — four government/
   legislative-research PDFs (CAG Bharatmala performance audit, NHAI
   Annual Report, MoRTH Annual Report, PRS Legislative Research analysis)
   downloaded and verified byte-exact against their HTTP `Content-Length`,
   used as the real-document corpus for the RAG pipeline. Two additional
   catalogued PIB press releases could not be fetched (bot-blocked, and
   not direct PDF links regardless) — disclosed, not hidden, in
   [data/documents/metadata.csv](data/documents/metadata.csv).
3. **Derived/generated artifacts** — engineered feature tables
   (`data/processed/`), document chunks, embeddings, and the FAISS index
   (`rag_index/`), all deterministically derived from (1) or (2) and
   regenerable from the committed source data via the scripts in
   `scripts/`.

## Model & Evaluation Methodology

- **Split**: a project-level **chronological cohort split** (earliest 70%
  of projects by planned start date → train, next 15% → validation, final
  15% → test), never a random row split — because every prediction target
  is constant across a project's own snapshots, a random split would leak
  target identity across a project's rows. Zero project overlap between
  splits is asserted and tested. See
  [docs/TRAIN_VAL_TEST_STRATEGY.md](docs/TRAIN_VAL_TEST_STRATEGY.md).
- **Models compared per task**: Dummy baseline → Logistic/Linear
  Regression baseline → Random Forest → XGBoost, using the identical
  frozen split and the identical 45 leakage-audited predictor columns for
  every model. See
  [docs/MODEL_COMPARISON_REPORT.md](docs/MODEL_COMPARISON_REPORT.md).
- **Honest result, not cherry-picked**: tree models (RF/XGBoost) beat the
  linear baseline for only 2 of the 4 tasks (delay classification, delay
  regression). For the other 2 tasks (cost classification, cost
  regression), the simpler Phase 4 baseline is the model actually
  recommended and served, because the tree models did not improve on it.
- **Explainability**: SHAP values are computed **live, per prediction
  request**, against whichever model actually serves that task — never a
  static pre-computed artifact shown regardless of which model is
  serving. See
  [docs/SHAP_EXPLAINABILITY_REPORT.md](docs/SHAP_EXPLAINABILITY_REPORT.md).
- **All reported metrics are performance on the synthetic prototype
  dataset only** and must not be read as real-world predictive
  performance — see [Limitations](#limitations).

## Quick Start

**Prerequisites**: Python 3.11+ (developed/tested with 3.12.4), Node.js
20+ and npm, Git. Tesseract OCR is only needed if you want to regenerate
the document-ingestion pipeline from scratch (`winget install --id
UB-Mannheim.TesseractOCR` on Windows) — the committed chunk/embedding/
index artifacts already exist, so it is not required just to run the app.

### Backend

From the repo root:

```bash
cd backend
python -m venv .venv
./.venv/Scripts/pip install -r requirements.txt
cd ..
./backend/.venv/Scripts/python.exe -m scripts.load_db    # loads the synthetic dataset into SQLite
cd backend
./.venv/Scripts/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Backend runs at `http://127.0.0.1:8000` — check `/health`, or open
`http://127.0.0.1:8000/docs` for interactive Swagger docs.

Optional, to populate portfolio analytics / decision-intelligence
peer-comparison context (batch-scores every eligible project once — run
from the repo root, not from `backend/`):

```bash
./backend/.venv/Scripts/python.exe -m scripts.batch_score_portfolio
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at `http://localhost:5173` and talks to the backend above.

### Try it

```
GET  /projects?q=kerala
GET  /projects/HRI-0001/predict?reporting_month=2023-04
GET  /projects/HRI-0006/risk-summary?reporting_month=2022-12
GET  /projects/HRI-0006/decision-intelligence?reporting_month=2022-12
GET  /documents/search?q=How much money has NHAI raised through the InvIT mode?
GET  /documents/inconsistencies
POST /agent/query   { "message": "why is HRI-0006 at risk?" }
GET  /projects/HRI-0006/report.pdf?reporting_month=2022-12
```

### Regenerating derived artifacts

Every derived dataset/model/index is reproducible from committed source
data via a dedicated script — see the linked doc for exact commands,
parameters, and output:

| Script | Regenerates | Documented in |
|---|---|---|
| `scripts/generate_dataset.py` | Synthetic project dataset | [docs/DATASET_REPORT.md](docs/DATASET_REPORT.md) |
| `scripts/prepare_features.py` | ML-ready feature tables | [docs/FEATURE_ENGINEERING.md](docs/FEATURE_ENGINEERING.md) |
| `scripts/train_baseline_models.py`, `-m scripts.train_tree_models` | Baseline/RF/XGBoost models | [docs/MODEL_COMPARISON_REPORT.md](docs/MODEL_COMPARISON_REPORT.md) |
| `-m scripts.explain_models` | Global SHAP artifacts | [docs/SHAP_EXPLAINABILITY_REPORT.md](docs/SHAP_EXPLAINABILITY_REPORT.md) |
| `-m scripts.ingest_documents` | Document chunk dataset | [docs/DOCUMENT_INGESTION.md](docs/DOCUMENT_INGESTION.md) |
| `-m scripts.build_rag_index` | FAISS index + embeddings | [docs/RAG_SYSTEM.md](docs/RAG_SYSTEM.md) |
| `-m scripts.batch_score_portfolio` | Portfolio prediction cache | [docs/ADVANCED_ANALYTICS.md](docs/ADVANCED_ANALYTICS.md) |

## Testing

```bash
# Root-level test suite (data/feature/pipeline scripts)
./backend/.venv/Scripts/python.exe -m pytest -v

# Backend test suite
./backend/.venv/Scripts/python.exe -m pytest backend -v

# Frontend test suite
cd frontend && npm run test

# Frontend production build
cd frontend && npm run build
```

Most recently verified results (current commit):

| Suite | Result |
|---|---|
| Root | 162 passed, 0 failed, 0 skipped |
| Backend | 538 passed, 0 failed, 0 skipped |
| Frontend | 100 passed, 0 failed |
| Frontend production build | Succeeded |

These are local test-suite results on the synthetic prototype dataset,
not a production certification or a claim of real-world validation.

## Documentation

The documents below are the source of truth for methodology, thresholds,
exact numbers, and disclosed limitations — this README intentionally
summarizes rather than duplicates them.

**Platform**
| Doc | Covers |
|---|---|
| [docs/architecture.md](docs/architecture.md) | System architecture, directory layout, stack rationale |
| [docs/local_llm_feasibility.md](docs/local_llm_feasibility.md) | Local-LLM hardware feasibility (re-checked across multiple phases; never enabled) |
| [docs/PRODUCTION_READINESS.md](docs/PRODUCTION_READINESS.md) | Logging, error handling, input validation, dependency audit, security posture |
| [docs/PROJECT_LIFECYCLE.md](docs/PROJECT_LIFECYCLE.md) | Project create/edit/archive/monthly-snapshot design |
| [docs/ASK_HRI_AGENT.md](docs/ASK_HRI_AGENT.md) | Ask HRI's intent routing, entity extraction, and response contract |

**Data & ML**
| Doc | Covers |
|---|---|
| [data/README.md](data/README.md) | Full data provenance breakdown (start here for data questions) |
| [docs/SYNTHETIC_DATA_METHODOLOGY.md](docs/SYNTHETIC_DATA_METHODOLOGY.md) | Why/how the synthetic dataset is generated, and what it cannot prove |
| [docs/DATASET_REPORT.md](docs/DATASET_REPORT.md) | Synthetic dataset statistics |
| [docs/EDA_REPORT.md](docs/EDA_REPORT.md) | Exploratory data analysis |
| [docs/FEATURE_ENGINEERING.md](docs/FEATURE_ENGINEERING.md) | Feature dictionary, leakage audit |
| [docs/TRAIN_VAL_TEST_STRATEGY.md](docs/TRAIN_VAL_TEST_STRATEGY.md) | Chronological split methodology |
| [docs/BASELINE_MODEL_REPORT.md](docs/BASELINE_MODEL_REPORT.md) | Baseline model results |
| [docs/MODEL_COMPARISON_REPORT.md](docs/MODEL_COMPARISON_REPORT.md) | Baseline vs. RF vs. XGBoost, per task |
| [docs/SHAP_EXPLAINABILITY_REPORT.md](docs/SHAP_EXPLAINABILITY_REPORT.md) | SHAP methodology and results |
| [docs/API_AND_DATABASE.md](docs/API_AND_DATABASE.md) | Database schema, CRUD endpoints |
| [docs/MODEL_SERVING.md](docs/MODEL_SERVING.md) | Prediction-serving design |

**Documents & Decision Support**
| Doc | Covers |
|---|---|
| [docs/DOCUMENT_INGESTION.md](docs/DOCUMENT_INGESTION.md) | PDF extraction, OCR fallback, chunking |
| [docs/RAG_SYSTEM.md](docs/RAG_SYSTEM.md) | Embeddings, FAISS retrieval, relevance threshold, extractive answers |
| [docs/CONTRADICTION_DETECTION.md](docs/CONTRADICTION_DETECTION.md) | Claim extraction, pairing, comparison, hedged reporting |
| [docs/WHATIF_SIMULATOR.md](docs/WHATIF_SIMULATOR.md) | Override rules, extrapolation warnings |
| [docs/DECISION_SUPPORT.md](docs/DECISION_SUPPORT.md) | Per-project synthesis design |
| [docs/DECISION_INTELLIGENCE.md](docs/DECISION_INTELLIGENCE.md) | Portfolio context, peer comparison, percentile methodology |
| [docs/ADVANCED_ANALYTICS.md](docs/ADVANCED_ANALYTICS.md) | Portfolio risk score, segments, trends |

**Frontend**
| Doc | Covers |
|---|---|
| [docs/FRONTEND_DASHBOARD.md](docs/FRONTEND_DASHBOARD.md) | Dashboard architecture, design system |
| [docs/PHASE_13.md](docs/PHASE_13.md) | Server-side search, PDF reports |

## Limitations

- **All ML training data is synthetic.** No accuracy/precision/recall/R²
  figure in this repository establishes real-world predictive performance
  on actual NHAI/MoRTH highway projects — only performance on a simulated
  dataset calibrated to real aggregate statistics.
- The synthetic corpus simulates every project **through to completion**,
  so there is no genuinely "still ongoing" project by that definition;
  portfolio analytics and decision intelligence instead use each
  project's latest *pre-terminal* snapshot as "current". This is a
  retrospective, latest-known-snapshot analysis — it must not be
  described as live operational forecasting on real, currently-running
  projects.
- **What-if simulation is model re-scoring, not validated causal
  inference.** Changing an input and observing a different prediction
  shows what the model would output, not a proven causal or
  interaction-cascading effect in the real world.
- **Ask HRI is a deterministic intent/entity/tool-routing interface, not
  an LLM-powered chatbot.** It calls existing, already-tested HRI
  services and reports their real output, or returns a fixed "I don't
  have enough information" response — there is no free-text generation
  and no external LLM API call anywhere in the implementation. Its
  natural-language coverage is intentionally narrow (a fixed intent/
  entity whitelist); an unrecognized phrasing is reported as
  unsupported, not guessed at.
- The real-document RAG corpus is small (4 documents) — genuine coverage
  gaps exist, and out-of-corpus queries correctly return "not found"
  rather than a fabricated answer.
- Contradiction detection is heuristic (regex + embedding similarity), not
  an NLI/fact-checking model — flags are reported as "potential
  inconsistency requiring verification", never as confirmed errors.
- **No authentication or authorization** is implemented anywhere in the
  API — this is a local, single-user MVP.
- **No rate limiting, TrustedHost middleware, or HTTPS redirect** is
  configured — out of scope for the current local deployment posture.
- **No CI/CD pipeline** is configured in this repository.
- No automated dependency CVE scanning is run for the backend
  (`pip-audit` is not installed); one transitive advisory was identified
  by manual inspection and documented as unreachable — see
  [docs/PRODUCTION_READINESS.md](docs/PRODUCTION_READINESS.md).
- See each linked doc's own "Known Limitations" section for narrower,
  feature-specific caveats not repeated here.

## Security / Production Readiness

A dedicated hardening pass (structured logging, a centralized exception
handler that never leaks a traceback to the client, consistent
`reporting_month` input validation across every accepting endpoint, and a
dependency audit) was completed and documented in
[docs/PRODUCTION_READINESS.md](docs/PRODUCTION_READINESS.md). What that
pass explicitly did **not** add, by disclosed design decision for a local
single-user MVP: authentication, rate limiting, TrustedHost middleware,
HTTPS redirection, or a CI pipeline. **This hardening pass improves code
quality and failure behavior; it is not a claim of production deployment,
security certification, or real-world validation.**

## Roadmap

Items below are genuine, currently-deferred work — not commitments or
announced features:

- Authentication/authorization for the mutating project-lifecycle
  endpoints
- Rate limiting and stricter network-boundary hardening for a non-local
  deployment
- A CI pipeline (test suite + lint on push)
- Automated backend dependency CVE scanning (`pip-audit`)
- Application screenshots / a recorded demo (see below)
- A license decision (see [License](#license--disclaimer))
- Expanding Ask HRI's what-if natural-language whitelist beyond its
  current fixed set of recognized concepts

## Project Status

Phase 17 complete at commit `c368a3d4ef6c8b2b90a6e8a8305b1908a17870b5`
(project lifecycle management + Ask HRI deterministic query agent). Runs
locally only — no deployment, no configured remote, no live demo.

### Screenshots / Demo

No application screenshots or recorded demo currently exist in this
repository. Screenshots can be added in a future update once the UI is
considered release-ready for that purpose; none are included here rather
than fabricated.

## License & Disclaimer

**License**: No license file currently exists in this repository. A
license decision is still pending before public release — until one is
added, all rights are reserved by default.

**Disclaimer**: HRI is an educational/portfolio project — an independent
research prototype inspired by highway infrastructure monitoring and
risk-analysis workflows. It is **not** an official NHAI product, not an
official government system, not an official NHAI prediction service, and
carries **no affiliation with or endorsement by** NHAI, MoRTH, or any
government body. All data is labeled by provenance throughout the
repository (see [Data & Provenance](#data--provenance)): real data is
cited to its public source, and synthetic data is never presented as
real. No claim in this repository should be read as real-time government
data, a production deployment, a validated real-world accuracy figure, or
an autonomous AI system — see [Limitations](#limitations) for the full,
honest accounting.
