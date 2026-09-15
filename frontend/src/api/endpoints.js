// One typed-by-JSDoc function per backend endpoint actually implemented in
// backend/app/routers/*.py. Nothing here is speculative -- every path and
// query/body param matches the FastAPI route signature it calls.
import { apiGet, apiGetBlob, apiPost } from './client'

export const getHealth = (signal) => apiGet('/health', undefined, signal)

/**
 * GET /projects
 * @param {{page?: number, page_size?: number, q?: string, state?: string, project_type?: string, project_status?: string}} params
 * `q` (Phase 13) is a case-insensitive partial-match search performed in
 * SQL on the backend across project_id/project_name/highway_number/state/
 * contractor/project_type -- never a client-side filter.
 */
export const listProjects = (params, signal) => apiGet('/projects', params, signal)

/** GET /projects/{project_id} */
export const getProject = (projectId, signal) => apiGet(`/projects/${encodeURIComponent(projectId)}`, undefined, signal)

/** GET /projects/{project_id}/snapshots */
export const listProjectSnapshots = (projectId, signal) =>
  apiGet(`/projects/${encodeURIComponent(projectId)}/snapshots`, undefined, signal)

/** GET /projects/{project_id}/snapshots/{reporting_month} */
export const getProjectSnapshot = (projectId, reportingMonth, signal) =>
  apiGet(`/projects/${encodeURIComponent(projectId)}/snapshots/${encodeURIComponent(reportingMonth)}`, undefined, signal)

/** GET /projects/{project_id}/predict?reporting_month=YYYY-MM */
export const getPrediction = (projectId, reportingMonth, signal) =>
  apiGet(`/projects/${encodeURIComponent(projectId)}/predict`, { reporting_month: reportingMonth }, signal)

/**
 * POST /projects/{project_id}/simulate?reporting_month=YYYY-MM
 * @param {Record<string, number|string>} overrides absolute-value overrides only
 */
export const runSimulation = (projectId, reportingMonth, overrides, signal) =>
  apiPost(
    `/projects/${encodeURIComponent(projectId)}/simulate`,
    overrides || {},
    { reporting_month: reportingMonth },
    signal
  )

/** GET /projects/{project_id}/risk-summary?reporting_month=YYYY-MM */
export const getRiskSummary = (projectId, reportingMonth, signal) =>
  apiGet(`/projects/${encodeURIComponent(projectId)}/risk-summary`, { reporting_month: reportingMonth }, signal)

/**
 * GET /projects/{project_id}/decision-intelligence?reporting_month=YYYY-MM
 * (Phase 15) -- composes the Phase 11 risk-summary response above with
 * Phase 14 portfolio context (risk_positioning, peer_context,
 * driver_alignment) and a merged recommended_reviews list. See
 * backend/app/routers/decision_intelligence.py.
 */
export const getDecisionIntelligence = (projectId, reportingMonth, signal) =>
  apiGet(`/projects/${encodeURIComponent(projectId)}/decision-intelligence`, { reporting_month: reportingMonth }, signal)

/** GET /documents/search?q=...&top_k=5 */
export const searchDocuments = (query, topK, signal) => apiGet('/documents/search', { q: query, top_k: topK }, signal)

/** GET /documents/inconsistencies */
export const getInconsistencies = (signal) => apiGet('/documents/inconsistencies', undefined, signal)

/** GET /analytics/summary (Phase 12 addition, see backend/app/routers/analytics.py) */
export const getPortfolioSummary = (signal) => apiGet('/analytics/summary', undefined, signal)

/**
 * GET /analytics/portfolio (Phase 14) -- historical + predicted overview,
 * risk distribution, top risks preview, executive insights. See
 * backend/app/routers/portfolio_analytics.py.
 */
export const getPortfolioOverview = (signal) => apiGet('/analytics/portfolio', undefined, signal)

/**
 * GET /analytics/risk-projects (Phase 14) -- ranked, filterable predicted
 * risk list. Backs both the Top-Risk table and the Risk Matrix.
 * @param {{state?: string, project_type?: string, contractor?: string, risk_level?: string, limit?: number, offset?: number}} params
 */
export const getRiskProjects = (params, signal) => apiGet('/analytics/risk-projects', params, signal)

/**
 * GET /analytics/segments?dimension=state|project_type|contractor (Phase 14)
 */
export const getPortfolioSegments = (dimension, signal) => apiGet('/analytics/segments', { dimension }, signal)

/** GET /analytics/drivers (Phase 14) -- portfolio-wide model-attributed SHAP drivers. */
export const getPortfolioDrivers = (signal) => apiGet('/analytics/drivers', undefined, signal)

/** GET /analytics/trends (Phase 14) -- historical (actual) + predicted (model) trends. */
export const getPortfolioTrends = (signal) => apiGet('/analytics/trends', undefined, signal)

/**
 * GET /projects/{project_id}/report.pdf?reporting_month=YYYY-MM (Phase 13)
 * Resolves to `{blob, filename}` for a genuine backend-generated PDF (see
 * backend/app/routers/reports.py) -- never a client-side/print-based export.
 */
export const downloadReportPdf = (projectId, reportingMonth, signal) =>
  apiGetBlob(`/projects/${encodeURIComponent(projectId)}/report.pdf`, { reporting_month: reportingMonth }, signal)
