"""Phase 12 read-only portfolio analytics response schema:
GET /analytics/summary.

New in Phase 12 -- not part of Phases 1-11. See
app/routers/analytics.py for why this endpoint exists.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.schemas.predictions import SYNTHETIC_DATA_DISCLAIMER_ACTUAL


class PortfolioSummaryResponse(BaseModel):
    total_projects: int
    status_counts: dict[str, int]
    state_counts: dict[str, int]
    project_type_counts: dict[str, int]
    significant_delay_count: int
    cost_overrun_count: int
    avg_final_delay_days: float
    avg_final_cost_overrun_pct: float
    synthetic_data_disclaimer: str = SYNTHETIC_DATA_DISCLAIMER_ACTUAL
