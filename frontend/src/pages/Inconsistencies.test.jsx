import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import Inconsistencies from './Inconsistencies'
import { getInconsistencies } from '../api/endpoints'

vi.mock('../api/endpoints', () => ({
  getInconsistencies: vi.fn(),
}))

const FLAG = {
  flag_id: 'FLAG-001',
  document_a: 'DOC-002',
  page_a: 12,
  chunk_a: 'c1',
  raw_claim_a: 'Rs 50,000 crore',
  normalized_value_a: 50000,
  document_b: 'DOC-003',
  page_b: 8,
  chunk_b: 'c2',
  raw_claim_b: 'Rs 35,000 crore',
  normalized_value_b: 35000,
  claim_type: 'currency',
  difference: 15000,
  similarity_score: 0.81,
  tolerance_info: 'exceeds 5% tolerance',
  context_info: 'no contextual exclusion applied',
  confidence: 'moderate',
  description: 'These two documents report different financial-outlay figures for a similarly-described scope.',
}

describe('Inconsistencies page', () => {
  it('never renders "confirmed" language and always uses the hedged wording', async () => {
    getInconsistencies.mockResolvedValue({
      total_chunks_considered: 861,
      total_claims_extracted: 3697,
      claim_type_counts: { currency: 1019, percentage: 629, date: 1861, count: 188 },
      candidate_chunk_pairs: 139,
      comparable_claim_pairs_evaluated: 7,
      contextual_differences_excluded: 3,
      flagged_count: 1,
      flags: [FLAG],
      disclaimer: 'This is a heuristic verification-assistance tool, NOT a fact-checker.',
    })

    render(<Inconsistencies />)

    expect(await screen.findByText('Potential inconsistency requiring verification')).toBeInTheDocument()
    expect(screen.queryByText(/confirmed contradiction/i)).not.toBeInTheDocument()
    expect(screen.queryByText('Confirmed Error')).not.toBeInTheDocument()
    expect(screen.queryByText(/^confirmed$/i)).not.toBeInTheDocument()
  })

  it('renders the zero-flag case as a valid explicit empty state, not an error', async () => {
    getInconsistencies.mockResolvedValue({
      total_chunks_considered: 861,
      total_claims_extracted: 3697,
      claim_type_counts: { currency: 1019, percentage: 629, date: 1861, count: 188 },
      candidate_chunk_pairs: 139,
      comparable_claim_pairs_evaluated: 7,
      contextual_differences_excluded: 7,
      flagged_count: 0,
      flags: [],
      disclaimer: 'This is a heuristic verification-assistance tool, NOT a fact-checker.',
    })

    render(<Inconsistencies />)

    expect(await screen.findByText('No potential inconsistencies flagged.')).toBeInTheDocument()
  })
})
