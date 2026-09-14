import { render, screen, fireEvent, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import Projects from './Projects'
import { ProjectsCacheProvider } from '../context/ProjectsCacheContext'
import { listProjects } from '../api/endpoints'

vi.mock('../api/endpoints', () => ({
  listProjects: vi.fn(),
}))

const PROJECTS = [
  { project_id: 'HRI-0006', project_name: 'Delhi-Dehradun Expressway', state: 'Uttarakhand', project_type: 'Expressway', contractor: 'ACME', project_length_km: 210.4, original_contract_value_inr_cr: 4500, current_status: 'Completed' },
  { project_id: 'HRI-0019', project_name: 'Bangalore-Chennai Expressway', state: 'Karnataka', project_type: 'Expressway', contractor: 'BuildCo', project_length_km: 262.0, original_contract_value_inr_cr: 5200, current_status: 'Completed' },
  { project_id: 'HRI-0023', project_name: 'Amritsar-Jamnagar Expressway', state: 'Rajasthan', project_type: 'Expressway', contractor: 'RoadWorks', project_length_km: 429.1, original_contract_value_inr_cr: 8300, current_status: 'Completed' },
]

function renderProjects() {
  render(
    <MemoryRouter>
      <ProjectsCacheProvider>
        <Projects />
      </ProjectsCacheProvider>
    </MemoryRouter>
  )
}

describe('Projects page', () => {
  it('renders every project from the backend in the table', async () => {
    listProjects.mockResolvedValue({ items: PROJECTS, page: 1, page_size: 100, total: PROJECTS.length })

    renderProjects()

    expect(await screen.findByText('HRI-0006')).toBeInTheDocument()
    expect(screen.getByText('HRI-0019')).toBeInTheDocument()
    expect(screen.getByText('HRI-0023')).toBeInTheDocument()
  })

  it('filters rows client-side by project ID/name search text', async () => {
    listProjects.mockResolvedValue({ items: PROJECTS, page: 1, page_size: 100, total: PROJECTS.length })

    renderProjects()
    await screen.findByText('HRI-0006')

    fireEvent.change(screen.getByLabelText('Search'), { target: { value: 'Bangalore' } })

    const table = screen.getByRole('table')
    expect(within(table).getByText('HRI-0019')).toBeInTheDocument()
    expect(within(table).queryByText('HRI-0006')).not.toBeInTheDocument()
    expect(within(table).queryByText('HRI-0023')).not.toBeInTheDocument()
  })

  it('shows an empty state when no project matches the filters', async () => {
    listProjects.mockResolvedValue({ items: PROJECTS, page: 1, page_size: 100, total: PROJECTS.length })

    renderProjects()
    await screen.findByText('HRI-0006')

    fireEvent.change(screen.getByLabelText('Search'), { target: { value: 'no-such-project-xyz' } })

    expect(await screen.findByText('No projects match your filters.')).toBeInTheDocument()
  })
})
