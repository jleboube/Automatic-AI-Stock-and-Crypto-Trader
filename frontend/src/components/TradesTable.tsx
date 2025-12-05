import { format } from 'date-fns';
import type { Trade } from '../types';
import { StatusBadge } from './StatusBadge';

interface TradesTableProps {
  trades: Trade[];
  title?: string;
}

export function TradesTable({ trades, title = 'Recent Trades' }: TradesTableProps) {
  if (trades.length === 0) {
    return (
      <div className="card">
        <h3 className="text-lg font-semibold text-white mb-4">{title}</h3>
        <p className="text-slate-400 text-center py-8">No trades found</p>
      </div>
    );
  }

  return (
    <div className="card">
      <h3 className="text-lg font-semibold text-white mb-4">{title}</h3>
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="text-left text-slate-400 text-sm border-b border-slate-700">
              <th className="pb-3 pr-4">Type</th>
              <th className="pb-3 pr-4">Symbol</th>
              <th className="pb-3 pr-4">Strikes</th>
              <th className="pb-3 pr-4">Contracts</th>
              <th className="pb-3 pr-4">Premium</th>
              <th className="pb-3 pr-4">P&L</th>
              <th className="pb-3 pr-4">Status</th>
              <th className="pb-3">Opened</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((trade) => (
              <tr key={trade.id} className="border-b border-slate-700/50 text-sm">
                <td className="py-3 pr-4 capitalize text-slate-300">
                  {trade.trade_type.replace('_', ' ')}
                </td>
                <td className="py-3 pr-4 font-medium text-white">{trade.symbol}</td>
                <td className="py-3 pr-4 text-slate-300">
                  {trade.short_strike && trade.long_strike
                    ? `${trade.short_strike} / ${trade.long_strike}`
                    : trade.short_strike || trade.long_strike || '--'}
                </td>
                <td className="py-3 pr-4 text-slate-300">{trade.contracts}</td>
                <td className="py-3 pr-4 text-slate-300">
                  ${((trade.premium_received || 0) - (trade.premium_paid || 0)).toFixed(2)}
                </td>
                <td className={`py-3 pr-4 font-medium ${
                  trade.pnl === null
                    ? 'text-slate-400'
                    : trade.pnl >= 0
                    ? 'text-green-400'
                    : 'text-red-400'
                }`}>
                  {trade.pnl !== null ? `$${trade.pnl.toFixed(2)}` : '--'}
                </td>
                <td className="py-3 pr-4">
                  <StatusBadge status={trade.status} size="sm" />
                </td>
                <td className="py-3 text-slate-400 text-xs">
                  {format(new Date(trade.opened_at), 'MMM d, yyyy HH:mm')}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
