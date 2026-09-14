import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { PALETTE } from '../../utils/palette'

export default function HorizontalBarList({ data, color = PALETTE.blue, height, valueLabel = 'Projects' }) {
  const chartHeight = height || Math.max(160, data.length * 30)
  return (
    <ResponsiveContainer width="100%" height={chartHeight}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 20, bottom: 4, left: 4 }}>
        <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#e2e8f0" />
        <XAxis type="number" allowDecimals={false} tick={{ fontSize: 11 }} />
        <YAxis type="category" dataKey="name" width={110} tick={{ fontSize: 11.5 }} />
        <Tooltip formatter={(value) => [value, valueLabel]} />
        <Bar dataKey="value" fill={color} radius={[0, 4, 4, 0]} barSize={14} />
      </BarChart>
    </ResponsiveContainer>
  )
}
