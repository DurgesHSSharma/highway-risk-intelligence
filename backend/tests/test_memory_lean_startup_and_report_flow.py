"""Behavioral proof of the free-tier memory optimizations, in an ISOLATED interpreter.

`sys.modules` in the main pytest process is useless for this: other tests in the
same session legitimately load shap, torch and the embedding model. So each check
runs a fresh child Python process against a throwaway database and inspects which
heavy libraries that process actually imported.

Asserted here:
  * importing the app does NOT import shap (numba/llvmlite/matplotlib come with it) --
    it is imported lazily, on the first request that computes SHAP values;
  * the report flow (terminal AND non-terminal snapshot, risk-summary + report.pdf)
    returns real 200 responses WITHOUT importing torch / transformers /
    sentence_transformers -- the evidence queries are served from the fixed-query
    embedding cache;
  * a genuine free-text document search still DOES load the embedding stack, and
    still returns real cited results -- which also proves the probe above can fail
    (the report-flow assertion is not vacuous).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from app.config import REPO_ROOT

BACKEND_DIR = REPO_ROOT / "backend"

_CHILD = r"""
import json, os, sys
sys.path.insert(0, {backend!r}); sys.path.insert(0, {repo!r})
import warnings; warnings.filterwarnings("ignore")

EMBED_LIBS = ("torch", "transformers", "sentence_transformers")
def loaded(*names): return {{n: (n in sys.modules) for n in names}}

out = {{}}
from app.main import app
out["after_import_app_main"] = loaded("shap", "numba", "matplotlib", *EMBED_LIBS)

from app.db.loader import load_database
from app.config import settings
load_database(settings.dataset_csv_file_path)

from fastapi.testclient import TestClient
with TestClient(app) as client:
    out["after_startup"] = loaded("shap", *EMBED_LIBS)

    terminal = client.get("/projects/HRI-0002/risk-summary", params={{"reporting_month": "2026-01"}})
    terminal_pdf = client.get("/projects/HRI-0002/report.pdf", params={{"reporting_month": "2026-01"}})
    live = client.get("/projects/HRI-0006/risk-summary", params={{"reporting_month": "2022-12"}})
    live_pdf = client.get("/projects/HRI-0006/report.pdf", params={{"reporting_month": "2022-12"}})
    out["report_flow_status"] = [terminal.status_code, terminal_pdf.status_code, live.status_code, live_pdf.status_code]
    out["report_flow_pdf_magic"] = [terminal_pdf.content[:5].decode("latin-1"), live_pdf.content[:5].decode("latin-1")]
    out["report_flow_evidence_chunks"] = [
        sum(len(block["results"]) for block in body.json()["documentary_evidence"]) for body in (terminal, live)
    ]
    out["after_report_flow"] = loaded("shap", *EMBED_LIBS)

    search = client.get("/documents/search", params={{"q": "How much money has NHAI raised through the InvIT mode?"}})
    out["search_status"] = search.status_code
    out["search_results"] = len(search.json()["results"])
    out["after_free_text_search"] = loaded("shap", *EMBED_LIBS)

print("RESULT_JSON=" + json.dumps(out))
"""


def _run_child() -> dict:
    with tempfile.TemporaryDirectory(prefix="hri_lean_flow_") as tmp:
        env = dict(os.environ, DATABASE_PATH=str(Path(tmp) / "lean_flow_test.db"))
        proc = subprocess.run(
            [sys.executable, "-c", _CHILD.format(backend=str(BACKEND_DIR), repo=str(REPO_ROOT))],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(BACKEND_DIR),
            timeout=600,
        )
    assert proc.returncode == 0, f"child process failed:\n{proc.stdout[-2000:]}\n{proc.stderr[-4000:]}"
    line = next(l for l in proc.stdout.splitlines() if l.startswith("RESULT_JSON="))
    return json.loads(line[len("RESULT_JSON=") :])


@pytest.fixture(scope="module")
def result() -> dict:
    """One child process for the whole module (a failing child fails every test once,
    it is not re-run per test)."""
    return _run_child()


def test_importing_the_app_does_not_import_shap(result):
    r = result["after_import_app_main"]
    assert r["shap"] is False
    assert r["numba"] is False and r["matplotlib"] is False  # only ever pulled in via shap


def test_startup_does_not_load_the_embedding_stack(result):
    r = result["after_startup"]
    assert not any(r[lib] for lib in ("torch", "transformers", "sentence_transformers"))


def test_report_flow_returns_real_responses_without_loading_the_embedding_stack(result):
    assert result["report_flow_status"] == [200, 200, 200, 200]
    assert result["report_flow_pdf_magic"] == ["%PDF-", "%PDF-"]
    assert all(n > 0 for n in result["report_flow_evidence_chunks"])  # real retrieved evidence, not skipped
    loaded = result["after_report_flow"]
    assert not any(loaded[lib] for lib in ("torch", "transformers", "sentence_transformers"))


def test_shap_is_imported_on_first_use_by_the_non_terminal_report_flow(result):
    assert result["after_report_flow"]["shap"] is True


def test_free_text_document_search_still_loads_the_embedding_stack_and_works(result):
    assert result["search_status"] == 200
    assert result["search_results"] > 0
    loaded = result["after_free_text_search"]
    assert loaded["sentence_transformers"] is True and loaded["torch"] is True
