import { useEffect, useState } from 'react';
import { getTrades, getTradeStats } from '../services/api';
import type { Trade, TradeSummary } from '../types';
import { TradesTable } from '../components/TradesTable';
import { MetricCard } from '../components/MetricCard';
import { DollarSign, TrendingUp, BarChart, Percent } from 'lucide-react';

export function Trades() {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [stats, setStats] = useState<TradeSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<'all' | 'open' | 'closed'>('all');

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [tradesData, statsData] = await Promise.all([
          getTrades(200),
          getTradeStats(),
        ]);
        setTrades(tradesData);
        setStats(statsData);
      } catch (err) {
        console.error('Failed to load trades:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  const filteredTrades = trades.filter((trade) => {
    if (filter === 'all') return true;
    return trade.status === filter;
  });

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-slate-400">Loading trades...</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-white">Trade History</h2>
        <p className="text-slate-400">View and analyze your trading activity</p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          title="Total P&L"
          value={stats?.total_pnl ? `$${stats.total_pnl.toFixed(2)}` : '$0.00'}
          valueColor={stats?.total_pnl && stats.total_pnl >= 0 ? 'success' : 'danger'}
          icon={<DollarSign className="w-5 h-5 text-green-400" />}
        />
        <MetricCard
          title="Win Rate"
          value={stats?.win_rate ? `${stats.win_rate.toFixed(1)}%` : '0%'}
          icon={<Percent className="w-5 h-5 text-blue-400" />}
        />
        <MetricCard
          title="Total Trades"
          value={stats?.total_trades ?? 0}
          subtitle={`${stats?.open_trades ?? 0} open, ${stats?.closed_trades ?? 0} closed`}
          icon={<BarChart className="w-5 h-5 text-purple-400" />}
        />
        <MetricCard
          title="Avg Premium"
          value={stats?.avg_premium ? `$${stats.avg_premium.toFixed(2)}` : '$0.00'}
          icon={<TrendingUp className="w-5 h-5 text-primary-400" />}
        />
      </div>

      {/* Filter */}
      <div className="flex gap-2">
        {(['all', 'open', 'closed'] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-4 py-2 rounded-lg font-medium transition-colors capitalize ${
              filter === f
                ? 'bg-primary-600 text-white'
                : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
            }`}
          >
            {f}
          </button>
        ))}
      </div>

      {/* Trades Table */}
      <TradesTable trades={filteredTrades} title={`${filter === 'all' ? 'All' : filter === 'open' ? 'Open' : 'Closed'} Trades`} />
    </div>
  );
}
