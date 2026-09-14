import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import AsyncSection, { EmptyState, ErrorState, LoadingState } from './StateViews'

describe('StateViews', () => {
  it('LoadingState shows a status role and label', () => {
    render(<LoadingState label="Loading projects…" />)
    expect(screen.getByRole('status')).toHaveTextContent('Loading projects…')
  })

  it('ErrorState shows a retry button that calls onRetry', () => {
    const onRetry = vi.fn()
    render(<ErrorState title="Unable to load project data." onRetry={onRetry} />)
    expect(screen.getByRole('alert')).toHaveTextContent('Unable to load project data.')
    fireEvent.click(screen.getByRole('button', { name: /retry/i }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('EmptyState renders a title and message', () => {
    render(<EmptyState title="No projects found." message="Try clearing filters." />)
    expect(screen.getByText('No projects found.')).toBeInTheDocument()
    expect(screen.getByText('Try clearing filters.')).toBeInTheDocument()
  })

  it('AsyncSection renders loading, then error, then empty, then success in sequence', () => {
    const { rerender } = render(
      <AsyncSection status="loading" loadingLabel="Loading…">
        {() => <div>content</div>}
      </AsyncSection>
    )
    expect(screen.getByText('Loading…')).toBeInTheDocument()

    rerender(
      <AsyncSection status="error" error={{ message: 'boom' }} errorTitle="Failed.">
        {() => <div>content</div>}
      </AsyncSection>
    )
    expect(screen.getByText('Failed.')).toBeInTheDocument()
    expect(screen.getByText('boom')).toBeInTheDocument()

    rerender(
      <AsyncSection status="success" data={[]} isEmpty={(d) => d.length === 0} emptyTitle="Nothing here.">
        {() => <div>content</div>}
      </AsyncSection>
    )
    expect(screen.getByText('Nothing here.')).toBeInTheDocument()

    rerender(
      <AsyncSection status="success" data={[1]} isEmpty={(d) => d.length === 0}>
        {() => <div>real content</div>}
      </AsyncSection>
    )
    expect(screen.getByText('real content')).toBeInTheDocument()
  })
})
