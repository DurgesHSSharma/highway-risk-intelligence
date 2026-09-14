// One typed-by-JSDoc function per backend endpoint actually implemented in
// backend/app/routers/*.py. Nothing here is speculative -- every path and
// query/body param matches the FastAPI route signature it calls.
import { apiGet, apiPost } from './client'

export const getHealth = (signal) => apiGet('/health', undefined, signal)

/**
 * GET /projects
 * @param {{page?: number, page_size?: number, state?: string, project_type?: string, project_status?: string}} params
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

/** GET /documents/search?q=...&top_k=5 */
export const searchDocuments = (query, topK, signal) => apiGet('/documents/search', { q: query, top_k: topK }, signal)

/** GET /documents/inconsistencies */
export const getInconsistencies = (signal) => apiGet('/documents/inconsistencies', undefined, signal)

/** GET /analytics/summary (Phase 12 addition, see backend/app/routers/analytics.py) */
export const getPortfolioSummary = (signal) => apiGet('/analytics/summary', undefined, signal)
