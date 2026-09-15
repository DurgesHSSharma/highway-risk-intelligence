import { IconCheckCircle, IconRisk } from './icons'

// Phase 14: the historical/actual vs. current-model-predicted distinction
// must be obvious WITHOUT relying on color alone (same accessibility rule
// RiskBadge already follows) -- so this always pairs an icon with explicit
// text, never a color chip by itself.
export default function SourceLabel({ kind }) {
  if (kind === 'historical') {
    return (
      <span className="badge badge-neutral" title="Recorded actual outcomes from completed (terminal) projects">
        <IconCheckCircle size={12} />
        HISTORICAL / ACTUAL
      </span>
    )
  }
  return (
    <span
      className="badge badge-info"
      title="Model-generated prediction from each project's latest available non-terminal snapshot"
    >
      <IconRisk size={12} />
      CURRENT MODEL-PREDICTED
    </span>
  )
}
