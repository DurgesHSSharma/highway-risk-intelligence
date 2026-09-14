import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import RiskBadge, { riskLevelFromProbability } from './RiskBadge'

describe('riskLevelFromProbability', () => {
  it('buckets probabilities into high/medium/low using fixed thresholds', () => {
    expect(riskLevelFromProbability(0.85)).toBe('high')
    expect(riskLevelFromProbability(0.6)).toBe('high')
    expect(riskLevelFromProbability(0.45)).toBe('medium')
    expect(riskLevelFromProbability(0.3)).toBe('medium')
    expect(riskLevelFromProbability(0.1)).toBe('low')
  })

  it('returns null for missing values', () => {
    expect(riskLevelFromProbability(null)).toBeNull()
    expect(riskLevelFromProbability(undefined)).toBeNull()
  })
})

describe('RiskBadge', () => {
  it('always renders text alongside color (never color alone)', () => {
    render(<RiskBadge level="high" />)
    expect(screen.getByText('High')).toBeInTheDocument()
  })

  it('accepts a custom label override', () => {
    render(<RiskBadge level="medium" label="Potential inconsistency requiring verification" />)
    expect(screen.getByText('Potential inconsistency requiring verification')).toBeInTheDocument()
  })
})
