import { useApi } from '../hooks/useApi'
import { getInconsistencies } from '../api/endpoints'
import AsyncSection, { EmptyState } from '../components/StateViews'
import InconsistencyCard from '../components/InconsistencyCard'
import DisclaimerBox from '../components/DisclaimerBox'
import { formatNumber } from '../utils/format'

export default function Inconsistencies() {
  const report = useApi((signal) => getInconsistencies(signal), [])

  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h1>Inconsistencies</h1>
          <p>
            Hybrid rule-based cross-document detector output. Every item below is a{' '}
            <strong>potential inconsistency requiring human verification</strong> — never a confirmed error in
            either source.
          </p>
        </div>
      </div>

      <AsyncSection
        status={report.status}
        error={report.error}
        data={report.data}
        onRetry={report.reload}
        loadingLabel="Loading contradiction/inconsistency report…"
        errorTitle="Unable to load the inconsistency report."
      >
        {(data) => (
          <>
            <div className="grid kpi-grid">
              <div className="kpi-card">
                <div className="kpi-label">Chunks Considered</div>
                <div className="kpi-value">{formatNumber(data.total_chunks_considered)}</div>
              </div>
              <div className="kpi-card">
                <div className="kpi-label">Claims Extracted</div>
                <div className="kpi-value">{formatNumber(data.total_claims_extracted)}</div>
              </div>
              <div className="kpi-card">
                <div className="kpi-label">Comparable Pairs Evaluated</div>
                <div className="kpi-value">{formatNumber(data.comparable_claim_pairs_evaluated)}</div>
              </div>
              <div className="kpi-card">
                <div className="kpi-label">Flagged</div>
                <div className="kpi-value">{formatNumber(data.flagged_count)}</div>
                <div className="kpi-note">of {formatNumber(data.candidate_chunk_pairs)} candidate chunk pairs</div>
              </div>
            </div>

            <div className="card card-padded">
              <div className="card-header">
                <h2>Claim Type Breakdown</h2>
              </div>
              <div className="grid three-col-grid">
                {Object.entries(data.claim_type_counts).map(([type, count]) => (
                  <div className="metric-row" key={type}>
                    <span>{type}</span>
                    <strong>{formatNumber(count)}</strong>
                  </div>
                ))}
              </div>
              <p className="muted" style={{ fontSize: 11.5, marginTop: 10, marginBottom: 0 }}>
                {formatNumber(data.contextual_differences_excluded)} candidate difference(s) were excluded as
                contextual (e.g. planned-vs-actual wording, differing reporting-cutoff dates) rather than flagged.
              </p>
            </div>

            <div className="card card-padded">
              <div className="card-header">
                <h2>Flagged Items</h2>
              </div>
              {data.flags.length === 0 ? (
                <EmptyState
                  title="No potential inconsistencies flagged."
                  message="A zero-flag result is a valid, explicit outcome of the detector — not an error."
                />
              ) : (
                <div className="stack" style={{ gap: 10 }}>
                  {data.flags.map((flag) => (
                    <InconsistencyCard key={flag.flag_id} flag={flag} />
                  ))}
                </div>
              )}
            </div>

            <DisclaimerBox>{data.disclaimer}</DisclaimerBox>
          </>
        )}
      </AsyncSection>
    </div>
  )
}
