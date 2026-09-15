import { IconAlertTriangle, IconCheckCircle, IconInfo } from '../icons'
import { titleCase } from '../../utils/format'

const TASK_LABELS = {
  significant_delay: 'Significant Delay',
  final_delay_days: 'Delay Duration',
  cost_overrun: 'Cost Overrun',
  final_cost_overrun_pct: 'Cost Overrun %',
}

/** Phase 15: one task's live-project-SHAP-driver vs. portfolio-wide-SHAP
 * -driver comparison row. For non-comparable tasks (matches_serving_model
 * =false -- the two cost tasks, where Phase 14's saved global SHAP
 * explains a different model family than the one actually serving the
 * prediction) this deliberately does NOT render a green/red agree
 * /disagree badge -- only the explicit "Not a meaningful comparison"
 * note, per the master-prompt's non-comparable-cost-task requirement. */
export default function DriverAlignmentRow({ alignment }) {
  const { task_key: taskKey, live_top_driver: live, portfolio_top_driver: portfolio, agreement, comparable, not_comparable_note: note } = alignment
  const label = TASK_LABELS[taskKey] || titleCase(taskKey)

  return (
    <div className="driver-alignment-row" style={{ padding: '10px 0', borderBottom: '1px solid var(--border)' }}>
      <div className="card-header" style={{ marginBottom: 6 }}>
        <span className="section-title" style={{ fontSize: 12.5 }}>
          {label}
        </span>
        {comparable ? (
          agreement === null ? (
            <span className="badge badge-neutral">
              <IconInfo size={12} /> Live driver unavailable
            </span>
          ) : agreement ? (
            <span className="badge badge-low">
              <IconCheckCircle size={12} /> Agrees with portfolio
            </span>
          ) : (
            <span className="badge badge-high">
              <IconAlertTriangle size={12} /> Diverges from portfolio
            </span>
          )
        ) : (
          // Plain sentence, not a short pill label -- .badge's white-space:
          // nowrap would overflow narrow (mobile) viewports, so this
          // intentionally does not reuse the shared .badge class.
          <span className="not-comparable-note">
            <IconInfo size={12} /> {note}
          </span>
        )}
      </div>
      <div className="grid two-col-grid" style={{ gap: 10, marginBottom: 0 }}>
        <div>
          <div className="info-item-label">Live project-specific driver</div>
          <div style={{ fontSize: 12.5 }}>{live ?? '—'}</div>
        </div>
        <div>
          <div className="info-item-label">Portfolio-wide driver</div>
          <div style={{ fontSize: 12.5 }}>{portfolio ?? '—'}</div>
        </div>
      </div>
    </div>
  )
}
