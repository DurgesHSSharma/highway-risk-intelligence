// Single centralized HTTP client for the HRI backend. Every page/component
// should go through the helpers in api/endpoints.js (which use this module)
// rather than calling fetch() directly, so base URL, error parsing, and
// JSON handling stay in one place.

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

export class ApiError extends Error {
  constructor(message, { status, detail } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

// FastAPI error bodies come in a few shapes depending on the endpoint:
//   - plain HTTPException(detail="...")               -> { detail: "string" }
//   - pydantic request validation errors               -> { detail: [{msg, loc, ...}, ...] }
//   - the simulate endpoint's invalid-override 422      -> { detail: { message, invalid_fields } }
// This normalizes all three into a single human-readable string while
// leaving the raw `detail` on the thrown ApiError for callers that need
// the structured version (e.g. invalid_fields).
function extractMessage(detail) {
  if (detail == null) return null
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail.map((d) => (typeof d === 'string' ? d : d.msg || JSON.stringify(d))).join('; ')
  }
  if (typeof detail === 'object') {
    if (typeof detail.message === 'string') return detail.message
    return JSON.stringify(detail)
  }
  return String(detail)
}

function buildUrl(path, params) {
  const url = new URL(path, API_BASE_URL)
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value === undefined || value === null || value === '') continue
      url.searchParams.set(key, value)
    }
  }
  return url.toString()
}

async function request(path, { method = 'GET', params, body, signal } = {}) {
  let response
  try {
    response = await fetch(buildUrl(path, params), {
      method,
      headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal,
    })
  } catch (err) {
    if (err.name === 'AbortError') throw err
    throw new ApiError(
      'Unable to reach the HRI backend. Confirm the FastAPI server is running at ' + API_BASE_URL + '.',
      { status: 0 }
    )
  }

  const text = await response.text()
  let payload = null
  if (text) {
    try {
      payload = JSON.parse(text)
    } catch {
      payload = null
    }
  }

  if (!response.ok) {
    const detail = payload && typeof payload === 'object' && 'detail' in payload ? payload.detail : payload
    const message = extractMessage(detail) || `Request failed with status ${response.status}.`
    throw new ApiError(message, { status: response.status, detail })
  }

  return payload
}

export const apiGet = (path, params, signal) => request(path, { method: 'GET', params, signal })
export const apiPost = (path, body, params, signal) => request(path, { method: 'POST', params, body, signal })
