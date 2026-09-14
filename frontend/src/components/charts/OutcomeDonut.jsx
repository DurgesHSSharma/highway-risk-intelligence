import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'
import { PALETTE } from '../../utils/palette'

export default function OutcomeDonut({ flaggedLabel, flaggedCount, totalProjects, color = PALETTE.red }) {
  const clear = Math.max(totalProjects - flaggedCount, 0)
  const data = [
    { name: flaggedLabel, value: flaggedCount },
    { name: 'No flag', value: clear },
  ]
  const pct = totalProjects ? Math.round((flaggedCount / totalProjects) * 100) : 0

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 18 }}>
      <div style={{ width: 120, height: 120, position: 'relative', flexShrink: 0 }}>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={data} dataKey="value" innerRadius={38} outerRadius={56} paddingAngle={2} stroke="none">
              <Cell fill={color} />
              <Cell fill={PALETTE.slateLight} />
            </Pie>
            <Tooltip formatter={(value, name) => [value, name]} />
          </PieChart>
        </ResponsiveContainer>
        <div
          style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexDirection: 'column',
            pointerEvents: 'none',
          }}
        >
          <strong style={{ fontSize: 18, lineHeight: 1 }}>{pct}%</strong>
        </div>
      </div>
      <dl style={{ margin: 0, fontSize: 12.5 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
          <span style={{ width: 9, height: 9, borderRadius: 999, background: color, display: 'inline-block' }} />
          <span className="muted">{flaggedLabel}</span>
          <strong>{flaggedCount}</strong>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ width: 9, height: 9, borderRadius: 999, background: PALETTE.slateLight, display: 'inline-block' }} />
          <span className="muted">No flag</span>
          <strong>{clear}</strong>
        </div>
      </dl>
    </div>
  )
}
