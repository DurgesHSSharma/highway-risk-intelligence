import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, apiGet, apiGetBlob, apiPost } from './client'

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

describe('apiGetBlob (Phase 13 PDF report download)', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('resolves to a blob and the server-suggested filename on success', async () => {
    const fakeBlob = new Blob(['%PDF-1.4 fake'], { type: 'application/pdf' })
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers([['Content-Disposition', 'attachment; filename="HRI-0006_2022-12_HRI_report.pdf"']]),
      blob: async () => fakeBlob,
    })

    const result = await apiGetBlob('/projects/HRI-0006/report.pdf', { reporting_month: '2022-12' })
    expect(result.blob).toBe(fakeBlob)
    expect(result.filename).toBe('HRI-0006_2022-12_HRI_report.pdf')
  })

  it('falls back to a default filename when no Content-Disposition header is present', async () => {
    const fakeBlob = new Blob(['%PDF-1.4 fake'], { type: 'application/pdf' })
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers(),
      blob: async () => fakeBlob,
    })

    const result = await apiGetBlob('/projects/HRI-0006/report.pdf', { reporting_month: '2022-12' })
    expect(result.filename).toBe('report.pdf')
  })

  it('raises an ApiError with the parsed JSON detail on a non-2xx response', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      headers: new Headers(),
      text: async () => JSON.stringify({ detail: "Project 'HRI-9999' not found." }),
    })

    await expect(apiGetBlob('/projects/HRI-9999/report.pdf', { reporting_month: '2022-12' })).rejects.toMatchObject({
      name: 'ApiError',
      status: 404,
      message: "Project 'HRI-9999' not found.",
    })
  })

  it('raises a network-failure ApiError when fetch itself rejects', async () => {
    global.fetch = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'))
    await expect(apiGetBlob('/projects/HRI-0006/report.pdf', { reporting_month: '2022-12' })).rejects.toMatchObject({
      name: 'ApiError',
      status: 0,
    })
  })
})
