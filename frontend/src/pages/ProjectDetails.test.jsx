import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import ProjectDetails from './ProjectDetails'
import { ApiError } from '../api/client'
import { getProject, listProjectSnapshots } from '../api/endpoints'

vi.mock('../api/endpoints', () => ({
  getProject: vi.fn(),
  listProjectSnapshots: vi.fn(),
}))

function renderAt(projectId) {
  render(
    <MemoryRouter initialEntries={[`/projects/${projectId}`]}>
      <Routes>
        <Route path="/projects/:projectId" element={<ProjectDetails />} />
      </Routes>
    </MemoryRouter>
  )
}

describe('ProjectDetails page', () => {
  it('shows an explicit not-found state for an unknown project ID (never a blank screen)', async () => {
    getProject.mockRejectedValue(new ApiError("Project 'HRI-9999' not found.", { status: 404 }))
    listProjectSnapshots.mockResolvedValue([])

    renderAt('HRI-9999')

    expect(await screen.findByText('Project "HRI-9999" was not found.')).toBeInTheDocument()
  })

  it('renders project info and the latest snapshot once loaded', async () => {
    getProject.mockResolvedValue({
      project_id: 'HRI-0006',
      data_provenance: 'synthetic',
      project_name: 'Delhi-Dehradun Expressway',
      highway_number: 'NH-58',
      state: 'Uttarakhand',
      project_type: 'Expressway',
      contractor: 'ACME Infra',
      project_length_km: 210.4,
      original_contract_value_inr_cr: 4500,
      planned_start_date: '2021-01-01',
      planned_completion_date: '2024-12-31',
      planned_duration_months: 48,
      current_status: 'Ongoing',
    })
    listProjectSnapshots.mockResolvedValue([
      {
        project_id: 'HRI-0006',
        reporting_month: '2022-12',
        months_since_start: 24,
        project_status: 'Ongoing',
        is_terminal_snapshot: false,
        planned_physical_progress_pct: 55,
        actual_physical_progress_pct: 48,
        physical_progress_variance_pct: -7,
        planned_financial_progress_pct: 50,
        actual_financial_progress_pct: 44,
        financial_progress_variance_pct: -6,
        planned_cost_to_date_inr_cr: 2000,
        actual_cost_to_date_inr_cr: 1800,
        actual_expenditure_inr_cr: 300,
        material_cost_inr_cr: 100,
        labour_cost_inr_cr: 80,
        equipment_cost_inr_cr: 40,
        delay_related_cost_inr_cr: 20,
        land_acquisition_delay_days: 40,
        utility_shifting_delay_days: 10,
        environment_clearance_delay_days: 5,
        material_delay_days: 3,
        labour_shortage_days: 0,
        equipment_unavailability_days: 0,
        weather_disruption_days: 8,
        traffic_diversion_delay_days: 2,
        design_change_delay_days: 0,
        approval_delay_days: 6,
        contractor_productivity_factor: 0.98,
      },
    ])

    renderAt('HRI-0006')

    expect(await screen.findByText(/Delhi-Dehradun Expressway/)).toBeInTheDocument()
    expect(screen.getByText('ACME Infra')).toBeInTheDocument()
    expect(screen.getByText('Land Acquisition')).toBeInTheDocument()
  })
})
