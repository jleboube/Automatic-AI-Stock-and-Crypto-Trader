import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';
import { format } from 'date-fns';
import type { PnLChartData } from '../types';

interface PnLChartProps {
  data: PnLChartData[];
  title?: string;
}

export function PnLChart({ data, title = 'P&L Performance' }: PnLChartProps) {
  const formattedData = data.map(d => ({
    ...d,
    date: format(new Date(d.date), 'MMM d'),
    fullDate: format(new Date(d.date), 'MMM d, yyyy'),
  }));

  const maxPnL = Math.max(...data.map(d => d.cumulative_pnl), 0);
  const minPnL = Math.min(...data.map(d => d.cumulative_pnl), 0);

  return (
    <div className="card">
      <h3 className="text-lg font-semibold text-white mb-4">{title}</h3>
      {data.length === 0 ? (
        <div className="h-64 flex items-center justify-center text-slate-400">
          No P&L data available
        </div>
      ) : (
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={formattedData} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis
                dataKey="date"
                stroke="#94a3b8"
                fontSize={12}
                tickLine={false}
              />
              <YAxis
                stroke="#94a3b8"
                fontSize={12}
                tickLine={false}
                tickFormatter={(value) => `$${value}`}
                domain={[minPnL * 1.1, maxPnL * 1.1]}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#1e293b',
                  border: '1px solid #334155',
                  borderRadius: '8px',
                }}
                labelStyle={{ color: '#f8fafc' }}
                formatter={(value: number) => [`$${value.toFixed(2)}`, 'Cumulative P&L']}
                labelFormatter={(label, payload) =>
                  payload?.[0]?.payload?.fullDate || label
                }
              />
              <ReferenceLine y={0} stroke="#475569" strokeDasharray="3 3" />
              <Line
                type="monotone"
                dataKey="cumulative_pnl"
                stroke="#0ea5e9"
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 6, fill: '#0ea5e9' }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
