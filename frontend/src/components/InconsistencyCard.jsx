import RiskBadge from './RiskBadge'

// Wording is fixed to Phase 9's hedged vocabulary throughout this app:
// every flag is a "potential inconsistency requiring verification", never
// a "confirmed contradiction/error" in either source.
export default function InconsistencyCard({ flag }) {
  return (
    <div className="evidence-card">
      <div className="evidence-meta">
        <RiskBadge level="medium" label="Potential inconsistency requiring verification" />
        <span className="badge badge-neutral">{flag.claim_type}</span>
        {flag.confidence && <span className="badge badge-neutral">confidence: {flag.confidence}</span>}
      </div>
      <div className="grid two-col-grid" style={{ gap: 10, marginTop: 4 }}>
        <div>
          <div className="info-item-label">{flag.document_a} · p.{flag.page_a}</div>
          <div className="evidence-text">"{flag.raw_claim_a}"</div>
          <div className="muted" style={{ fontSize: 11 }}>Normalized: {flag.normalized_value_a}</div>
        </div>
        <div>
          <div className="info-item-label">{flag.document_b} · p.{flag.page_b}</div>
          <div className="evidence-text">"{flag.raw_claim_b}"</div>
          <div className="muted" style={{ fontSize: 11 }}>Normalized: {flag.normalized_value_b}</div>
        </div>
      </div>
      <p className="evidence-text">{flag.description}</p>
      <div className="muted" style={{ fontSize: 11 }}>
        {flag.difference != null && <>Difference: {flag.difference} · </>}
        {flag.tolerance_info} · {flag.context_info}
      </div>
    </div>
  )
}
