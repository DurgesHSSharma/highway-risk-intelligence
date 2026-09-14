import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import DocumentSearch from './DocumentSearch'
import { searchDocuments } from '../api/endpoints'

vi.mock('../api/endpoints', () => ({
  searchDocuments: vi.fn(),
}))

function typeAndSubmit(query) {
  fireEvent.change(screen.getByLabelText('Question'), { target: { value: query } })
  fireEvent.click(screen.getByRole('button', { name: /search/i }))
}

describe('DocumentSearch page', () => {
  it('shows the exact backend not-found message when nothing clears the threshold', async () => {
    searchDocuments.mockResolvedValue({
      query: 'What is the recipe for chocolate cake?',
      top_k: 5,
      threshold: 0.35,
      not_found: true,
      results: [],
      answer: 'Not found in the available documents.',
      corpus_disclaimer: 'This corpus contains only 4 real public documents.',
    })

    render(<DocumentSearch />)
    typeAndSubmit('What is the recipe for chocolate cake?')

    expect(await screen.findByText('Not found in the available documents.')).toBeInTheDocument()
  })

  it('renders citation-grounded results when the corpus has a match', async () => {
    searchDocuments.mockResolvedValue({
      query: 'How much money has NHAI raised through InvIT?',
      top_k: 5,
      threshold: 0.35,
      not_found: false,
      results: [
        {
          rank: 1,
          similarity_score: 0.75,
          chunk_id: 'DOC-003-p27-c1',
          document_id: 'DOC-003',
          page_number: 27,
          section_heading: 'Financing',
          extraction_method: 'native_text',
          quality_flag: null,
          source_filename: 'nhai_annual_report.pdf',
          citation: '[DOC-003, p. 27]',
          text: 'NHAI raised funds through the InvIT mode.',
        },
      ],
      answer: 'From [DOC-003, p. 27]: NHAI raised funds through the InvIT mode.',
      corpus_disclaimer: 'This corpus contains only 4 real public documents.',
    })

    render(<DocumentSearch />)
    typeAndSubmit('How much money has NHAI raised through InvIT?')

    expect(await screen.findByText('[DOC-003, p. 27]')).toBeInTheDocument()
    expect(screen.getAllByText(/NHAI raised funds through the InvIT mode/).length).toBeGreaterThan(0)
  })
})
