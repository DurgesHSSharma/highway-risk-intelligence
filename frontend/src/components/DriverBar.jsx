const DIRECTION_LABEL = {
  increases: 'increases risk',
  decreases: 'decreases risk',
  negligible: 'negligible effect',
}

export default function DriverBar({ driver, maxAbs }) {
  const pct = maxAbs > 0 ? Math.min(100, (Math.abs(driver.shap_value) / maxAbs) * 48) : 0
  return (
    <div className="driver-row" title={driver.explanation}>
      <span className="driver-feature">{driver.feature}</span>
      <span className="driver-bar-track" aria-label={DIRECTION_LABEL[driver.direction]}>
        <span className={`driver-bar-fill ${driver.direction}`} style={{ width: `${pct}%` }} />
      </span>
      <span className="driver-value">{driver.shap_value.toFixed(3)}</span>
    </div>
  )
}
