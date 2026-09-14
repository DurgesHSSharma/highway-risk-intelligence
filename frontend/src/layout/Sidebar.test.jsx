import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import Sidebar from './Sidebar'

describe('Sidebar navigation', () => {
  it('renders every primary nav item with the HRI brand and tagline', () => {
    render(
      <MemoryRouter>
        <Sidebar open={false} onNavigate={() => {}} />
      </MemoryRouter>
    )

    expect(screen.getAllByText('HRI').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Highway Risk Intelligence').length).toBeGreaterThan(0)
    expect(screen.getByText('PREDICT DELAYS • CONTROL COSTS')).toBeInTheDocument()

    const expectedLinks = [
      ['Dashboard', '/'],
      ['Projects', '/projects'],
      ['AI Risk Summary', '/risk-summary'],
      ['What-if Simulator', '/simulator'],
      ['Document Search', '/documents'],
      ['Inconsistencies', '/inconsistencies'],
      ['Analytics', '/analytics'],
      ['Reports', '/reports'],
    ]

    for (const [label, href] of expectedLinks) {
      const link = screen.getByRole('link', { name: new RegExp(label) })
      expect(link).toHaveAttribute('href', href)
    }
  })
})
