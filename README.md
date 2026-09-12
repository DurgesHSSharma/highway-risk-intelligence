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

## Status: Phase 2 complete (data foundation)

Phase 1 delivered the project skeleton: a FastAPI backend, a React/Vite
frontend, and a verified health-check connection between them — see
[docs/architecture.md](docs/architecture.md), and
[docs/local_llm_feasibility.md](docs/local_llm_feasibility.md) for the
local-LLM hardware assessment.

Phase 2 adds the data foundation for later ML work: a reproducible
synthetic highway-project monthly-snapshot generator
([scripts/generate_dataset.py](scripts/generate_dataset.py)), a validation
pipeline ([scripts/validate_dataset.py](scripts/validate_dataset.py)), and a
metadata manifest of real public infrastructure documents. **No ML
training, RAG, or LLM inference is implemented yet** — see
[data/README.md](data/README.md) for what the data is and where it came
from, and [docs/DATASET_REPORT.md](docs/DATASET_REPORT.md) /
[docs/SYNTHETIC_DATA_METHODOLOGY.md](docs/SYNTHETIC_DATA_METHODOLOGY.md)
for the dataset's statistics and generation methodology.

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

Run the Phase 2 test suite (from the repo root):

```bash
./backend/.venv/Scripts/python.exe -m pytest -v
```

## Project layout

See [docs/architecture.md](docs/architecture.md).

## License / disclaimer

Educational/portfolio project. Not affiliated with, endorsed by, or
representing NHAI, MoRTH, or any government body. Any data used in later
phases will be clearly labeled as real (public source cited) or synthetic —
never presented as official.
