"""Lightweight standard-library logging setup for the FastAPI backend.

Phase 16 finding: the backend had no logging configuration at all --
`app/main.py` never called `logging.basicConfig` (or anything else), so
there was no INFO-level record of startup/initialization succeeding, and an
unexpected exception's real cause was visible only via uvicorn's own default
crash output to stderr, not through any log a deployment could reliably
collect. This wires up Python's standard `logging` module (no new
dependency, per the project's zero-cost/no-over-engineering rule) once, on
import of `app.main`.

Never logs request bodies, passwords, tokens, or other secrets -- callers
should log identifiers (project_id, reporting_month, task name) and
exception messages only.
"""

from __future__ import annotations

import logging
import sys

_CONFIGURED = False


def configure_logging() -> None:
    """Idempotent: safe to call multiple times (e.g. once from app.main,
    once from a test importing it directly) -- only the first call attaches
    a handler."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(
        logging.Formatter(fmt="%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%Y-%m-%dT%H:%M:%S")
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)
