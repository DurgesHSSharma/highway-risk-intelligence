import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, apiGet, apiPost } from './client'

function mockFetchOnce({ ok, status, body }) {
  global.fetch = vi.fn().mockResolvedValue({
    ok,
    status,
    text: async () => (body === undefined ? '' : JSON.stringify(body)),
  })
}

describe('api client', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('returns parsed JSON on success', async () => {
    mockFetchOnce({ ok: true, status: 200, body: { hello: 'world' } })
    const result = await apiGet('/health')
    expect(result).toEqual({ hello: 'world' })
  })

  it('builds query params, skipping null/undefined/empty values', async () => {
    mockFetchOnce({ ok: true, status: 200, body: {} })
    await apiGet('/projects', { page: 1, state: '', project_type: undefined, project_status: null })
    const calledUrl = global.fetch.mock.calls[0][0]
    expect(calledUrl).toContain('page=1')
    expect(calledUrl).not.toContain('state=')
    expect(calledUrl).not.toContain('project_type=')
    expect(calledUrl).not.toContain('project_status=')
  })

  it('sends a JSON body for POST requests', async () => {
    mockFetchOnce({ ok: true, status: 200, body: {} })
    await apiPost('/projects/HRI-0006/simulate', { contractor_productivity_factor: 0.5 }, { reporting_month: '2022-12' })
    const options = global.fetch.mock.calls[0][1]
    expect(options.method).toBe('POST')
    expect(JSON.parse(options.body)).toEqual({ contractor_productivity_factor: 0.5 })
  })

  it('extracts a plain string detail from an error response', async () => {
    mockFetchOnce({ ok: false, status: 404, body: { detail: "Project 'HRI-9999' not found." } })
    await expect(apiGet('/projects/HRI-9999')).rejects.toMatchObject({
      name: 'ApiError',
      status: 404,
      message: "Project 'HRI-9999' not found.",
    })
  })

  it('extracts a message from an object-shaped detail (simulate 422)', async () => {
    mockFetchOnce({
      ok: false,
      status: 422,
      body: { detail: { message: 'One or more override fields are not permitted predictor fields.', invalid_fields: [{ field: 'x', reason: 'unknown_field' }] } },
    })
    let caught
    try {
      await apiPost('/projects/HRI-0006/simulate', { x: 1 }, { reporting_month: '2022-12' })
    } catch (err) {
      caught = err
    }
    expect(caught).toBeInstanceOf(ApiError)
    expect(caught.message).toBe('One or more override fields are not permitted predictor fields.')
    expect(caught.detail.invalid_fields[0].reason).toBe('unknown_field')
  })

  it('extracts messages from an array-shaped pydantic validation detail', async () => {
    mockFetchOnce({ ok: false, status: 422, body: { detail: [{ msg: 'field required', loc: ['query', 'reporting_month'] }] } })
    await expect(apiGet('/projects/HRI-0006/predict')).rejects.toMatchObject({ status: 422, message: 'field required' })
  })

  it('raises a network-failure ApiError when fetch itself rejects', async () => {
    global.fetch = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'))
    await expect(apiGet('/health')).rejects.toMatchObject({ name: 'ApiError', status: 0 })
  })
})
