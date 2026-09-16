"""Shared request-parameter validation used across routers.

Phase 16 finding: `reporting_month` was validated with a FastAPI
`Query(..., pattern=...)` regex in `reports.py` only. `predictions.py`,
`simulation.py`, `decision_support.py`, and `decision_intelligence.py` each
accepted a bare `str`, so a malformed value (e.g. "abc", "2025-13",
"2025/09") slipped past request validation and fell through to a 404
("no snapshot found") deeper in the service layer instead of a 422
("malformed input") -- an inconsistent contract for the same parameter
across the API. `reports.py`'s original pattern (`^\\d{4}-\\d{2}$`) was also
looser than intended: it accepted an out-of-range month like "2025-13".
One shared pattern is defined here and reused everywhere a reporting_month
is accepted, instead of each router (re)defining its own.
"""

from __future__ import annotations

MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"
MONTH_DESCRIPTION = "Reporting month as YYYY-MM (month 01-12), e.g. 2025-09."
