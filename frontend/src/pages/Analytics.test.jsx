import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import Analytics from './Analytics'
import { ProjectsCacheProvider } from '../context/ProjectsCacheContext'
import {
  getPortfolioDrivers,
  getPortfolioOverview,
  getPortfolioSegments,
  getPortfolioSummary,
  getPortfolioTrends,
  getRiskProjects,
  listProjects,
} from '../api/endpoints'
import { ApiError } from '../api/client'

// Phase 14: extends the existing Phase 12 Analytics page with portfolio-
// level historical/predicted analytics. These tests cover rendering,
// structural historical/predicted separation, and the loading/error/empty
// states of the five new endpoints -- real backend contract/math
// correctness is covered by backend/tests/test_portfolio_analytics_api.py
// and test_independent_math_verification.py.
vi.mock('../api/endpoints', () => ({
  getPortfolioSummary: vi.fn(),
  getPortfolioOverview: vi.fn(),
  getRiskProjects: vi.fn(),
  getPortfolioSegments: vi.fn(),
  getPortfolioDrivers: vi.fn(),
  getPortfolioTrends: vi.fn(),
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

const OVERVIEW = {
  total_projects: 400,
  historical: {
    label: 'HISTORICAL / ACTUAL',
    completed_project_count: 400,
    significant_delay_count: 197,
    significant_delay_rate: 0.4925,
    cost_overrun_count: 153,
    cost_overrun_rate: 0.3825,
    mean_final_delay_days: 65.0,
    mean_final_cost_overrun_pct: 7.5,
  },
  predicted: {
    label: 'CURRENT MODEL-PREDICTED',
    status: 'ok',
    message: null,
    scored_project_count: 400,
    avg_significant_delay_probability: 0.544,
    avg_cost_overrun_probability: 0.346,
    avg_final_delay_days_predicted: 67.5,
    avg_final_cost_overrun_pct_predicted: 7.6,
    risk_level_counts: { LOW: 100, MEDIUM: 100, HIGH: 100, CRITICAL: 100 },
    computed_at: '2026-09-15T08:36:15',
  },
  risk_distribution: [
    { task_key: 'significant_delay', bucket_strategy: 'fixed_probability_bands', buckets: [{ label: '0-25%', lower: 0, upper: 0.25, count: 120 }], raw_values: [] },
    { task_key: 'final_delay_days', bucket_strategy: 'cohort_quartiles', buckets: [{ label: 'Q1 (lowest)', lower: -117, upper: 6, count: 100 }], raw_values: [] },
    { task_key: 'cost_overrun', bucket_strategy: 'fixed_probability_bands', buckets: [{ label: '0-25%', lower: 0, upper: 0.25, count: 200 }], raw_values: [] },
    { task_key: 'final_cost_overrun_pct', bucket_strategy: 'cohort_quartiles', buckets: [{ label: 'Q1 (lowest)', lower: -14, upper: -1, count: 100 }], raw_values: [] },
  ],
  top_risks: [
    {
      project_id: 'HRI-0328',
      project_name: 'NH-868 Expressway Package 18',
      state: 'Karnataka',
      project_type: 'Expressway',
      contractor: 'Rashtriya Builders Pvt Ltd',
      reporting_month: '2025-08',
      risk_score: 93.1,
      risk_level: 'CRITICAL',
      delay_risk: 0.96,
      cost_risk: 1.0,
      significant_delay_probability: 0.96,
      final_delay_days_predicted: 543.0,
      cost_overrun_probability: 1.0,
      final_cost_overrun_pct_predicted: 27.7,
    },
  ],
  executive_insights: [
    'Historical significant-delay rate across 400 completed projects is 49.2%.',
    "'contractor_productivity_factor' is the strongest portfolio-wide model-attributed feature.",
  ],
  synthetic_data_disclaimer: 'These are recorded final outcomes...',
}

const RISK_PROJECTS = {
  cache_status: 'ok',
  cache_message: null,
  total: 400,
  cohort_metadata: { cohort_size: 400, final_delay_days_min: -117, final_delay_days_max: 543, final_cost_overrun_pct_min: -14, final_cost_overrun_pct_max: 41, risk_level_thresholds: { q1: 15, q2: 36, q3: 65 } },
  items: OVERVIEW.top_risks,
  synthetic_data_disclaimer: 'model-predicted disclaimer',
}

const SEGMENTS = {
  dimension: 'state',
  min_sample_threshold: 15,
  entries: [
    {
      dimension: 'state',
      value: 'Madhya Pradesh',
      min_sample_threshold: 15,
      small_sample: false,
      historical: { project_count: 31, significant_delay_rate: 0.355, cost_overrun_rate: 0.226, mean_final_delay_days: 46, mean_final_cost_overrun_pct: 5.1 },
      predicted: { scored_project_count: 31, avg_significant_delay_probability: 0.465, avg_cost_overrun_probability: 0.193, avg_final_delay_days_predicted: 50, avg_final_cost_overrun_pct_predicted: 6.0, avg_composite_risk_score: 40, risk_level_counts: { LOW: 11, MEDIUM: 8, HIGH: 7, CRITICAL: 5 } },
    },
    {
      dimension: 'state',
      value: 'Punjab',
      min_sample_threshold: 15,
      small_sample: true,
      historical: { project_count: 11, significant_delay_rate: 0.455, cost_overrun_rate: 0.364, mean_final_delay_days: 61, mean_final_cost_overrun_pct: 8.0 },
      predicted: { scored_project_count: 11, avg_significant_delay_probability: 0.483, avg_cost_overrun_probability: 0.277, avg_final_delay_days_predicted: 58, avg_final_cost_overrun_pct_predicted: 7.0, avg_composite_risk_score: 38, risk_level_counts: { LOW: 3, MEDIUM: 4, HIGH: 1, CRITICAL: 3 } },
    },
  ],
  synthetic_data_disclaimer: 'historical disclaimer',
}

const DRIVERS = {
  tasks: [
    {
      task_key: 'significant_delay',
      label: 'Task A: Significant Delay Classification',
      model_family_explained: 'random_forest',
      matches_serving_model: true,
      drivers: [{ rank: 1, feature: 'contractor_productivity_factor', raw_feature: 'numeric__contractor_productivity_factor', mean_abs_shap: 0.1019 }],
    },
    {
      task_key: 'cost_overrun',
      label: 'Task C: Cost Overrun Classification',
      model_family_explained: 'xgboost',
      matches_serving_model: false,
      drivers: [{ rank: 1, feature: 'cost_tracking_gap_inr_cr', raw_feature: 'numeric__cost_tracking_gap_inr_cr', mean_abs_shap: 1.345 }],
    },
  ],
  methodology_note: 'These are PORTFOLIO-WIDE, model-family-level SHAP importances reused verbatim from Phase 5.',
}

const TRENDS = {
  historical: [
    { period: '2019', project_count: 76, significant_delay_rate: 0.4, cost_overrun_rate: 0.3, mean_final_delay_days: 50, mean_final_cost_overrun_pct: 5, small_sample: false },
  ],
  historical_label: 'HISTORICAL / ACTUAL',
  predicted_status: 'ok',
  predicted_message: null,
  predicted: [
    { period: '2019', scored_project_count: 1, avg_significant_delay_probability: 0.5, avg_cost_overrun_probability: 0.3, avg_composite_risk_score: 40, small_sample: true },
  ],
  predicted_label: 'CURRENT MODEL-PREDICTED',
  synthetic_data_disclaimer: 'trend disclaimer',
}

function renderAnalytics() {
  render(
    <MemoryRouter>
      <ProjectsCacheProvider>
        <Analytics />
      </ProjectsCacheProvider>
    </MemoryRouter>
  )
}

const SAMPLE_PROJECTS = [
  { project_id: 'HRI-0001', project_length_km: 50, original_contract_value_inr_cr: 500, state: 'Madhya Pradesh', project_type: 'Expressway' },
  { project_id: 'HRI-0002', project_length_km: 80, original_contract_value_inr_cr: 800, state: 'Punjab', project_type: 'Bridge/ROB/Flyover' },
]

beforeEach(() => {
  vi.clearAllMocks()
  listProjects.mockResolvedValue({ items: SAMPLE_PROJECTS, page: 1, page_size: 100, total: SAMPLE_PROJECTS.length })
  getPortfolioSummary.mockResolvedValue(SUMMARY)
  getPortfolioOverview.mockResolvedValue(OVERVIEW)
  getRiskProjects.mockResolvedValue(RISK_PROJECTS)
  getPortfolioSegments.mockResolvedValue(SEGMENTS)
  getPortfolioDrivers.mockResolvedValue(DRIVERS)
  getPortfolioTrends.mockResolvedValue(TRENDS)
})

describe('Analytics page', () => {
  it('renders the existing Phase 12 portfolio summary section', async () => {
    renderAnalytics()
    expect(await screen.findByText('Analytics')).toBeInTheDocument()
    await waitFor(() => expect(screen.getAllByText('400').length).toBeGreaterThan(0))
  })

  it('renders the historical section labeled HISTORICAL / ACTUAL', async () => {
    renderAnalytics()
    expect(await screen.findByText('Historical Performance')).toBeInTheDocument()
    // The label appears more than once on the page (Historical Performance
    // + Historical Trend both carry it) -- that repetition is itself part
    // of the "obvious without relying on color alone" requirement.
    const labels = await screen.findAllByText('HISTORICAL / ACTUAL')
    expect(labels.length).toBeGreaterThan(0)
    expect(screen.getByText(/49.3%/)).toBeInTheDocument()
  })

  it('renders the predicted section labeled CURRENT MODEL-PREDICTED', async () => {
    renderAnalytics()
    expect(await screen.findByText('Current Predicted Risk')).toBeInTheDocument()
    const labels = await screen.findAllByText('CURRENT MODEL-PREDICTED')
    expect(labels.length).toBeGreaterThan(0)
    expect(screen.getByText(/54.4%/)).toBeInTheDocument()
  })

  it('keeps historical and predicted sections structurally distinct (different labels, not one blended block)', async () => {
    renderAnalytics()
    const historicalLabels = await screen.findAllByText('HISTORICAL / ACTUAL')
    const predictedLabels = await screen.findAllByText('CURRENT MODEL-PREDICTED')
    expect(historicalLabels.length).toBeGreaterThan(0)
    expect(predictedLabels.length).toBeGreaterThan(0)
    // Historical rate (49.3%) and predicted probability (54.4%) must both
    // be visible simultaneously, never collapsed into one ambiguous number.
    expect(screen.getByText(/49.3%/)).toBeInTheDocument()
    expect(screen.getByText(/54.4%/)).toBeInTheDocument()
  })

  it('shows a cache-unavailable disclaimer instead of predicted KPIs when the cache is empty', async () => {
    getPortfolioOverview.mockResolvedValue({
      ...OVERVIEW,
      predicted: { ...OVERVIEW.predicted, status: 'cache_unavailable', message: 'Run scripts/batch_score_portfolio.py.' },
    })
    renderAnalytics()
    expect(await screen.findByText(/Run scripts\/batch_score_portfolio\.py/)).toBeInTheDocument()
    expect(screen.queryByText(/54.4%/)).not.toBeInTheDocument()
  })

  it('renders the risk distribution buckets for all four tasks', async () => {
    renderAnalytics()
    expect(await screen.findByText('Risk Distribution')).toBeInTheDocument()
    expect(await screen.findByText('Significant Delay Probability')).toBeInTheDocument()
    expect(screen.getByText('Predicted Delay Days')).toBeInTheDocument()
    expect(screen.getByText('Cost Overrun Probability')).toBeInTheDocument()
    expect(screen.getByText('Predicted Cost Overrun %')).toBeInTheDocument()
  })

  it('renders executive insights as real computed sentences', async () => {
    renderAnalytics()
    expect(await screen.findByText(/Historical significant-delay rate across 400 completed projects/)).toBeInTheDocument()
  })

  it('renders the top-risk table with real ranked project data', async () => {
    renderAnalytics()
    expect(await screen.findByText('Top Risk Projects')).toBeInTheDocument()
    expect(await screen.findByText('HRI-0328')).toBeInTheDocument()
    expect(screen.getByText('93.1')).toBeInTheDocument()
  })

  it('re-fetches risk projects when a filter changes', async () => {
    renderAnalytics()
    await screen.findByText('HRI-0328')
    getRiskProjects.mockClear()

    const stateSelect = screen.getByLabelText('State')
    fireEvent.change(stateSelect, { target: { value: 'Punjab' } })

    await waitFor(() => expect(getRiskProjects).toHaveBeenCalled())
    const [params] = getRiskProjects.mock.calls[0]
    expect(params.state).toBe('Punjab')
  })

  it('renders segment analytics with small-sample flagging', async () => {
    renderAnalytics()
    expect(await screen.findByText('Segment Analytics')).toBeInTheDocument()
    const table = (await screen.findByText('Historical delay rate')).closest('table')
    expect(within(table).getByText('Madhya Pradesh')).toBeInTheDocument()
    const punjabRow = within(table).getByText('Punjab').closest('tr')
    expect(within(punjabRow).getByText('Small sample')).toBeInTheDocument()
  })

  it('switches segment dimension and refetches on tab click', async () => {
    renderAnalytics()
    await screen.findByText('Historical delay rate')
    getPortfolioSegments.mockClear()
    getPortfolioSegments.mockResolvedValue({ ...SEGMENTS, dimension: 'contractor', min_sample_threshold: 8, entries: [] })

    screen.getByRole('button', { name: 'Contractor' }).click()

    await waitFor(() => expect(getPortfolioSegments).toHaveBeenCalledWith('contractor', expect.anything()))
  })

  it('renders portfolio-wide drivers and discloses model-family mismatches', async () => {
    renderAnalytics()
    expect(await screen.findByText('Portfolio-Wide Model Drivers')).toBeInTheDocument()
    expect(await screen.findByText('contractor_productivity_factor')).toBeInTheDocument()
    expect(await screen.findByText(/Explains xgboost, not the serving model/)).toBeInTheDocument()
  })

  it('renders historical and predicted trend charts separately', async () => {
    renderAnalytics()
    expect(await screen.findByText('Historical Trend')).toBeInTheDocument()
    expect(await screen.findByText('Predicted Trend')).toBeInTheDocument()
  })

  it('shows a predicted-trend-unavailable message when the cache has not been generated', async () => {
    getPortfolioTrends.mockResolvedValue({ ...TRENDS, predicted_status: 'cache_unavailable', predicted_message: 'Cache not generated.', predicted: [] })
    renderAnalytics()
    expect(await screen.findByText('Cache not generated.')).toBeInTheDocument()
  })

  it('shows a loading state before the portfolio overview resolves', async () => {
    let resolveFn
    getPortfolioOverview.mockReturnValue(new Promise((resolve) => { resolveFn = resolve }))
    renderAnalytics()
    expect(await screen.findByText('Loading portfolio risk overview…')).toBeInTheDocument()
    resolveFn(OVERVIEW)
    await screen.findByText('Historical Performance')
  })

  it('shows an error state with retry when the portfolio overview request fails', async () => {
    getPortfolioOverview.mockRejectedValue(new ApiError('Unable to reach the HRI backend.', { status: 0 }))
    renderAnalytics()
    expect(await screen.findByText('Unable to load portfolio risk overview.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Retry/i })).toBeInTheDocument()
  })

  it('shows an empty state when segment analytics return no entries', async () => {
    getPortfolioSegments.mockResolvedValue({ dimension: 'state', min_sample_threshold: 15, entries: [] })
    renderAnalytics()
    expect(await screen.findByText('No segment data available.')).toBeInTheDocument()
  })

  it('shows an error state when the drivers request fails, independent of other sections', async () => {
    getPortfolioDrivers.mockRejectedValue(new ApiError('Unable to reach the HRI backend.', { status: 0 }))
    renderAnalytics()
    expect(await screen.findByText('Unable to load model drivers.')).toBeInTheDocument()
    // Other sections must still render fine -- one failed endpoint doesn't
    // take down the whole page.
    expect(await screen.findByText('Historical Performance')).toBeInTheDocument()
  })
})
