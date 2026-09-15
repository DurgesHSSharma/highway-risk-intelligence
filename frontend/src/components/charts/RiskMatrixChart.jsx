import { CartesianGrid, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from 'recharts'

const LEVEL_COLOR = {
  LOW: 'var(--risk-low, #067647)',
  MEDIUM: 'var(--risk-medium, #b54708)',
  HIGH: 'var(--risk-high, #b42318)',
  CRITICAL: 'var(--risk-critical, #6941c6)',
}

function Tip({ active, payload }) {
  if (!active || !payload?.length) return null
  const p = payload[0].payload
  return (
    <div className="chart-tooltip">
      <strong>{p.project_id}</strong> — {p.project_name}
      <div>Delay risk: {(p.delay_risk * 100).toFixed(0)}%</div>
      <div>Cost risk: {(p.cost_risk * 100).toFixed(0)}%</div>
      <div>Risk level: {p.risk_level}</div>
    </div>
  )
}

/**
 * Delay Risk (x) vs Cost Risk (y) scatter -- each point is one real
 * currently-scored non-terminal project from GET /analytics/risk-projects.
 * Points are colored AND the risk level is always available in the
 * tooltip text, so the distinction never relies on color alone.
 */
export default function RiskMatrixChart({ points, height = 360 }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ScatterChart margin={{ top: 10, right: 20, bottom: 10, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
        <XAxis
          type="number"
          dataKey="delay_risk"
          domain={[0, 1]}
          tickFormatter={(v) => `${Math.round(v * 100)}%`}
          name="Delay risk"
          tick={{ fontSize: 11 }}
          label={{ value: 'Delay risk', position: 'insideBottom', offset: -6, fontSize: 12 }}
        />
        <YAxis
          type="number"
          dataKey="cost_risk"
          domain={[0, 1]}
          tickFormatter={(v) => `${Math.round(v * 100)}%`}
          name="Cost risk"
          tick={{ fontSize: 11 }}
          label={{ value: 'Cost risk', angle: -90, position: 'insideLeft', fontSize: 12 }}
        />
        <Tooltip content={<Tip />} cursor={{ strokeDasharray: '3 3' }} />
        {['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'].map((level) => (
          <Scatter
            key={level}
            name={level}
            data={points.filter((p) => p.risk_level === level)}
            fill={LEVEL_COLOR[level]}
          />
        ))}
      </ScatterChart>
    </ResponsiveContainer>
  )
}
