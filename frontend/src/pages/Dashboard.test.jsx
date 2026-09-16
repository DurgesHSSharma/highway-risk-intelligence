import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import Dashboard from './Dashboard'
import { ProjectsCacheProvider } from '../context/ProjectsCacheContext'
import { getPortfolioSummary, listProjects } from '../api/endpoints'
import { ApiError } from '../api/client'

// Phase 16 production-readiness: the Sample Projects section (backed by
// ProjectsCacheContext, not its own useApi call) previously rendered a
// generic, retry-less error on failure even though the KPI section above it
// (backed by useApi directly) already had one. This file did not exist
// before Phase 16 -- Dashboard had no dedicated tests.
vi.mock('../api/endpoints', () => ({
  getPortfolioSummary: vi.fn(),
  listProjects: vi.fn(),
}))

const SUMMARY = {
  total_projects: 400,
  status_counts: { Completed: 400 },
  state_counts: { 'Madhya Pradesh': 31, Punjab: 11 },
  project_type_counts: { Expressway: 34 },
  significant_delay_count: 197,
  cost_overrun_count: 153,
  avg_final_delay_days: 65.0,
  avg_final_cost_overrun_pct: 7.5,
  synthetic_data_disclaimer: 'These are recorded final outcomes from this project\'s SYNTHETIC dataset trajectory.',
}

const SAMPLE_PROJECTS = [
  { project_id: 'HRI-0001', project_name: 'NH-1 Widening', project_length_km: 50, state: 'Madhya Pradesh', project_type: 'Expressway', current_status: 'Completed' },
]

function renderDashboard() {
  render(
    <MemoryRouter>
      <ProjectsCacheProvider>
        <Dashboard />
      </ProjectsCacheProvider>
    </MemoryRouter>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  getPortfolioSummary.mockResolvedValue(SUMMARY)
  listProjects.mockResolvedValue({ items: SAMPLE_PROJECTS, page: 1, page_size: 100, total: SAMPLE_PROJECTS.length })
})

describe('Dashboard page', () => {
  it('renders portfolio KPIs and the sample projects table', async () => {
    renderDashboard()
    expect(await screen.findByText('AI-Powered Highway Project Intelligence')).toBeInTheDocument()
    expect(await screen.findAllByText('400')).not.toHaveLength(0)
    expect(await screen.findByText('HRI-0001')).toBeInTheDocument()
  })

  it('shows an error state with retry for the KPI section when it fails', async () => {
    getPortfolioSummary.mockRejectedValue(new ApiError('Unable to reach the HRI backend.', { status: 0 }))
    renderDashboard()
    expect(await screen.findByText('Unable to load portfolio KPIs.')).toBeInTheDocument()
    const errorBlock = screen.getByText('Unable to load portfolio KPIs.').closest('[role="alert"]')
    expect(within(errorBlock).getByRole('button', { name: /Retry/i })).toBeInTheDocument()
  })

  it('shows an error state with retry for sample projects, independent of the KPI section', async () => {
    listProjects.mockRejectedValue(new ApiError('Unable to reach the HRI backend.', { status: 0 }))
    renderDashboard()
    expect(await screen.findByText('Unable to load projects.')).toBeInTheDocument()
    const errorBlock = screen.getByText('Unable to load projects.').closest('[role="alert"]')
    expect(within(errorBlock).getByRole('button', { name: /Retry/i })).toBeInTheDocument()
    // The KPI section (a separate fetch) must still render fine.
    expect(await screen.findAllByText('400')).not.toHaveLength(0)
  })
})
