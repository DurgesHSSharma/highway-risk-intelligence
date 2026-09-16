import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import Projects from './Projects'
import { ProjectsCacheProvider } from '../context/ProjectsCacheContext'
import { archiveProject, listProjects, reactivateProject } from '../api/endpoints'

// Phase 13: Projects search moved from a client-side filter over a
// pre-fetched full project list to real backend search (GET /projects?q=).
// These tests assert that the page sends `q`/filters/pagination to the
// backend rather than filtering an in-memory list -- see
// backend/tests/test_projects_api.py for the real SQL-level search tests.
vi.mock('../api/endpoints', () => ({
  listProjects: vi.fn(),
  archiveProject: vi.fn(),
  reactivateProject: vi.fn(),
}))

const PROJECTS = [
  { project_id: 'HRI-0006', project_name: 'Delhi-Dehradun Expressway', state: 'Uttarakhand', project_type: 'Expressway', contractor: 'ACME', project_length_km: 210.4, original_contract_value_inr_cr: 4500, current_status: 'Completed', is_archived: false },
  { project_id: 'HRI-0019', project_name: 'Bangalore-Chennai Expressway', state: 'Karnataka', project_type: 'Expressway', contractor: 'BuildCo', project_length_km: 262.0, original_contract_value_inr_cr: 5200, current_status: 'Completed', is_archived: false },
  { project_id: 'HRI-0023', project_name: 'Amritsar-Jamnagar Expressway', state: 'Rajasthan', project_type: 'Expressway', contractor: 'RoadWorks', project_length_km: 429.1, original_contract_value_inr_cr: 8300, current_status: 'Completed', is_archived: true },
]

function renderProjects() {
  render(
    <MemoryRouter initialEntries={['/projects']}>
      <ProjectsCacheProvider>
        <Routes>
          <Route path="/projects" element={<Projects />} />
          <Route path="/projects/new" element={<div>add project page</div>} />
        </Routes>
      </ProjectsCacheProvider>
    </MemoryRouter>
  )
}

function tableCalls() {
  // Distinguishes this page's own request (page_size from PAGE_SIZE_OPTIONS,
  // default 20) from ProjectsCacheContext's unrelated hydration call
  // (fixed page_size 100, used only for filter-dropdown option lists).
  return listProjects.mock.calls.filter(([params]) => params.page_size !== 100)
}

beforeEach(() => {
  listProjects.mockReset()
  listProjects.mockResolvedValue({ items: PROJECTS, page: 1, page_size: 20, total: PROJECTS.length })
  archiveProject.mockReset()
  reactivateProject.mockReset()
})

describe('Projects page', () => {
  it('renders every project the backend returns for the current page', async () => {
    renderProjects()

    expect(await screen.findByText('HRI-0006')).toBeInTheDocument()
    expect(screen.getByText('HRI-0019')).toBeInTheDocument()
    expect(screen.getByText('HRI-0023')).toBeInTheDocument()
  })

  it('sends the initial listing request with no search query (backward compatible)', async () => {
    renderProjects()
    await screen.findByText('HRI-0006')

    const calls = tableCalls()
    expect(calls.length).toBeGreaterThan(0)
    expect(calls[0][0]).toMatchObject({ page: 1, page_size: 20, q: '', state: '', project_type: '', project_status: '' })
  })

  it('debounces search input and sends q to the real backend, never filtering a pre-fetched list', async () => {
    renderProjects()
    await screen.findByText('HRI-0006')
    listProjects.mockClear()

    fireEvent.change(screen.getByLabelText('Search'), { target: { value: 'Bangalore' } })

    // Debounced: not sent on the very next tick.
    expect(tableCalls().length).toBe(0)

    await waitFor(
      () => {
        const calls = tableCalls()
        expect(calls.some(([params]) => params.q === 'Bangalore')).toBe(true)
      },
      { timeout: 1000 }
    )
  })

  it('clears the search and re-requests the unfiltered listing', async () => {
    renderProjects()
    await screen.findByText('HRI-0006')

    fireEvent.change(screen.getByLabelText('Search'), { target: { value: 'Bangalore' } })
    await waitFor(() => expect(tableCalls().some(([p]) => p.q === 'Bangalore')).toBe(true), { timeout: 1000 })

    listProjects.mockClear()
    fireEvent.click(screen.getByLabelText('Clear search'))

    expect(screen.getByLabelText('Search')).toHaveValue('')
    await waitFor(() => expect(tableCalls().some(([p]) => p.q === '')).toBe(true), { timeout: 1000 })
  })

  it('resets to page 1 when the search query changes after paging forward', async () => {
    listProjects.mockResolvedValue({ items: PROJECTS, page: 1, page_size: 20, total: 45 })
    renderProjects()
    await screen.findByText('HRI-0006')

    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    await waitFor(() => expect(tableCalls().some(([p]) => p.page === 2)).toBe(true))

    listProjects.mockClear()
    fireEvent.change(screen.getByLabelText('Search'), { target: { value: 'Expressway' } })

    await waitFor(
      () => {
        const call = tableCalls().find(([p]) => p.q === 'Expressway')
        expect(call).toBeTruthy()
        expect(call[0].page).toBe(1)
      },
      { timeout: 1000 }
    )
  })

  it('combines search with state/type/status filters in one request', async () => {
    renderProjects()
    await screen.findByText('HRI-0006')
    listProjects.mockClear()

    fireEvent.change(screen.getByLabelText('State'), { target: { value: 'Karnataka' } })
    fireEvent.change(screen.getByLabelText('Search'), { target: { value: 'Bangalore' } })

    await waitFor(() => {
      const call = tableCalls().find(([p]) => p.q === 'Bangalore')
      expect(call).toBeTruthy()
      expect(call[0].state).toBe('Karnataka')
    }, { timeout: 1000 })
  })

  it('shows an empty state when the backend returns no results for the search', async () => {
    listProjects.mockResolvedValue({ items: [], page: 1, page_size: 20, total: 0 })

    renderProjects()

    expect(await screen.findByText('No projects match your search or filters.')).toBeInTheDocument()
  })

  it('shows an error state when the backend request fails', async () => {
    listProjects.mockRejectedValue(new Error('Unable to reach the HRI backend.'))

    renderProjects()

    expect(await screen.findByText('Unable to load project data.')).toBeInTheDocument()
  })

  it('navigates to the Add Project page', async () => {
    renderProjects()
    await screen.findByText('HRI-0006')

    fireEvent.click(screen.getByRole('button', { name: /add project/i }))

    expect(await screen.findByText('add project page')).toBeInTheDocument()
  })

  it('sends is_archived to the backend when the lifecycle filter changes', async () => {
    renderProjects()
    await screen.findByText('HRI-0006')
    listProjects.mockClear()

    fireEvent.change(screen.getByLabelText('Lifecycle'), { target: { value: 'archived' } })

    await waitFor(() => {
      const call = tableCalls().find(([p]) => p.is_archived === true)
      expect(call).toBeTruthy()
    })
  })

  it('shows an Active/Archived badge per project', async () => {
    renderProjects()
    await screen.findByText('HRI-0006')

    expect(screen.getAllByText('Active').length).toBe(2)
    expect(screen.getByText('Archived')).toBeInTheDocument()
  })

  it('archives an active project and reloads the list', async () => {
    archiveProject.mockResolvedValue({ project_id: 'HRI-0006', is_archived: true })
    renderProjects()
    await screen.findByText('HRI-0006')
    listProjects.mockClear()

    fireEvent.click(screen.getByLabelText('Archive HRI-0006'))

    await waitFor(() => expect(archiveProject).toHaveBeenCalledWith('HRI-0006'))
    await waitFor(() => expect(listProjects).toHaveBeenCalled())
  })

  it('reactivates an archived project', async () => {
    reactivateProject.mockResolvedValue({ project_id: 'HRI-0023', is_archived: false })
    renderProjects()
    await screen.findByText('HRI-0023')

    fireEvent.click(screen.getByLabelText('Reactivate HRI-0023'))

    await waitFor(() => expect(reactivateProject).toHaveBeenCalledWith('HRI-0023'))
  })
})
