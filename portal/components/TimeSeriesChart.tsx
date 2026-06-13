'use client';

import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
} from 'recharts';

export default function TimeSeriesChart({
  data,
  series,
  xKey = 'time',
  height = 260,
}: {
  data: any[];
  series: { key: string; color: string; name?: string }[];
  xKey?: string;
  height?: number;
}) {
  const fmtTime = (t: string) => {
    try {
      return new Date(t).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch {
      return t;
    }
  };
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: -10 }}>
        <CartesianGrid stroke="#232a33" strokeDasharray="3 3" />
        <XAxis dataKey={xKey} tickFormatter={fmtTime} stroke="#8b95a1" fontSize={11} />
        <YAxis stroke="#8b95a1" fontSize={11} />
        <Tooltip
          contentStyle={{ background: '#161b22', border: '1px solid #232a33', borderRadius: 8 }}
          labelFormatter={fmtTime}
        />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        {series.map((s) => (
          <Line
            key={s.key}
            type="monotone"
            dataKey={s.key}
            name={s.name || s.key}
            stroke={s.color}
            dot={false}
            strokeWidth={2}
            isAnimationActive={false}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
