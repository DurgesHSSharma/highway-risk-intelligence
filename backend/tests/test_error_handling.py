"""Phase 16 production-readiness tests: centralized exception handling.

Before this phase, an unexpected (non-HTTPException) exception anywhere in
the request path fell through to Starlette's own default
`ServerErrorMiddleware` behavior: a bare `text/plain` "Internal Server
Error" body with no server-side log of the real cause. This asserts the new
`app.main.unhandled_exception_handler` behavior instead: a safe, generic
JSON 500 body (never a traceback, file path, or exception message), while
FastAPI's own 404/422 handling for legitimate client errors is unaffected.

`raise_server_exceptions=False` is required on the TestClient used here --
Starlette's `ServerErrorMiddleware` always re-raises the original exception
after invoking the registered handler (so process-level tools like a real
ASGI server or Sentry still see it), which is exactly why real HTTP clients
(browsers, curl, uvicorn) only ever see the JSON response and never that
exception -- see docs/PRODUCTION_READINESS.md.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.db.base import get_db
from app.main import app

KNOWN_PROJECT_ID = "HRI-0006"
UNKNOWN_PROJECT_ID = "HRI-9999"
NON_TERMINAL_MONTH = "2022-12"


@pytest.fixture()
def unraising_client():
    """A dedicated TestClient (not the shared session-scoped `client`
    fixture) with `raise_server_exceptions=False`, so a genuinely unhandled
    exception's HTTP response can be inspected directly instead of
    propagating into the test itself."""
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def broken_db_dependency():
    """Forces the `get_db` dependency to raise a plain RuntimeError carrying
    a fake secret/path, standing in for any genuinely unexpected internal
    failure -- never triggered by real user input, only by this override."""

    def _boom():
        raise RuntimeError("boom: C:/Users/durge/secret_api_key=sk-fake-12345 should never leak")

    app.dependency_overrides[get_db] = _boom
    yield
    del app.dependency_overrides[get_db]


def test_unhandled_exception_returns_safe_json_500(unraising_client, broken_db_dependency):
    resp = unraising_client.get("/projects")
    assert resp.status_code == 500
    assert resp.headers["content-type"].startswith("application/json")
    body = resp.json()
    assert body == {"detail": "Internal server error."}


def test_unhandled_exception_response_never_leaks_internals(unraising_client, broken_db_dependency):
    resp = unraising_client.get("/projects")
    text = resp.text
    assert "Traceback" not in text
    assert "File \"" not in text
    assert "RuntimeError" not in text
    assert "secret_api_key" not in text
    assert "C:/Users/durge" not in text
    assert "C:\\Users\\durge" not in text


def test_404_still_returns_normal_detail_message(client):
    """Confirms the new catch-all handler does not shadow FastAPI's own
    HTTPException handling (it's matched first via exception-class MRO
    lookup, before falling back to the generic Exception handler)."""
    resp = client.get(f"/projects/{UNKNOWN_PROJECT_ID}")
    assert resp.status_code == 404
    assert resp.json() == {"detail": f"Project '{UNKNOWN_PROJECT_ID}' not found."}


def test_422_still_returns_normal_validation_detail(client):
    """Confirms the new catch-all handler does not shadow FastAPI's own
    RequestValidationError handling."""
    resp = client.get(f"/projects/{KNOWN_PROJECT_ID}/predict", params={"reporting_month": "not-a-month"})
    assert resp.status_code == 422
    body = resp.json()
    assert isinstance(body["detail"], list)
    assert body["detail"][0]["loc"] == ["query", "reporting_month"]
