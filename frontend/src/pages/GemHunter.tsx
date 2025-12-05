import { useEffect, useState, useCallback } from 'react';
import {
  Search, Target, TrendingUp, DollarSign,
  RefreshCw, Eye, XCircle, BarChart3, Sun, Moon, Sunrise
} from 'lucide-react';
import {
  getGemHunterState,
  getGemWatchlist,
  getGemPositions,
  getGemTradeHistory,
  triggerGemScan,
  addToGemWatchlist,
  removeFromGemWatchlist,
  closeGemPosition,
  getMarketHours,
  type GemHunterState,
  type GemWatchlistEntry,
  type GemPosition,
  type GemTradeHistory,
  type MarketHoursStatus,
} from '../services/api';
import { MetricCard } from '../components/MetricCard';

const getSessionInfo = (session: string) => {
  const info: Record<string, { icon: typeof Sun; label: string; color: string }> = {
    regular: { icon: Sun, label: 'Regular Hours', color: 'text-green-400' },
    pre_market: { icon: Sunrise, label: 'Pre-Market', color: 'text-yellow-400' },
    after_hours: { icon: Sunrise, label: 'After-Hours', color: 'text-yellow-400' },
    closed: { icon: Moon, label: 'Closed', color: 'text-slate-400' },
    weekend: { icon: Moon, label: 'Weekend', color: 'text-slate-400' },
    holiday: { icon: Moon, label: 'Holiday', color: 'text-slate-400' },
  };
  return info[session] || info.closed;
};

export function GemHunter() {
  const [state, setState] = useState<GemHunterState | null>(null);
  const [watchlist, setWatchlist] = useState<GemWatchlistEntry[]>([]);
  const [positions, setPositions] = useState<GemPosition[]>([]);
  const [history, setHistory] = useState<GemTradeHistory[]>([]);
  const [marketHours, setMarketHours] = useState<MarketHoursStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'watchlist' | 'positions' | 'history'>('watchlist');
  const [newSymbol, setNewSymbol] = useState('');

  const fetchData = useCallback(async () => {
    try {
      const [stateData, watchlistData, positionsData, historyData, marketHoursData] = await Promise.all([
        getGemHunterState(),
        getGemWatchlist(),
        getGemPositions(),
        getGemTradeHistory(50),
        getMarketHours(),
      ]);
      setState(stateData);
      setWatchlist(watchlistData);
      setPositions(positionsData);
      setHistory(historyData);
      setMarketHours(marketHoursData);
      setError(null);
    } catch (err) {
      setError('Failed to load Gem Hunter data');
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const handleScan = async () => {
    setScanning(true);
    try {
      await triggerGemScan();
      await fetchData();
    } catch (err) {
      console.error('Scan failed:', err);
    } finally {
      setScanning(false);
    }
  };

  const handleAddSymbol = async () => {
    if (!newSymbol.trim()) return;
    try {
      await addToGemWatchlist(newSymbol.trim().toUpperCase());
      setNewSymbol('');
      await fetchData();
    } catch (err) {
      console.error('Failed to add symbol:', err);
    }
  };

  const handleRemoveFromWatchlist = async (symbol: string) => {
    try {
      await removeFromGemWatchlist(symbol);
      await fetchData();
    } catch (err) {
      console.error('Failed to remove symbol:', err);
    }
  };

  const handleClosePosition = async (positionId: number) => {
    if (!confirm('Are you sure you want to close this position?')) return;
    try {
      await closeGemPosition(positionId);
      await fetchData();
    } catch (err) {
      console.error('Failed to close position:', err);
    }
  };

  const formatDateTime = (dateStr: string | null) => {
    if (!dateStr) return 'Never';
    return new Date(dateStr).toLocaleString();
  };

  const formatCurrency = (value: number | null) => {
    if (value === null) return '-';
    return `$${value.toFixed(2)}`;
  };

  const getScoreColor = (score: number) => {
    if (score >= 75) return 'text-green-400';
    if (score >= 60) return 'text-yellow-400';
    return 'text-red-400';
  };

  const getPnlColor = (pnl: number | null) => {
    if (pnl === null) return 'text-slate-400';
    return pnl >= 0 ? 'text-green-400' : 'text-red-400';
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-slate-400">Loading Gem Hunter...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-red-400">{error}</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-white flex items-center gap-2">
            <Target className="w-7 h-7 text-primary-400" />
            Gem Hunter
          </h2>
          <p className="text-slate-400">Autonomous stock discovery and trading</p>
        </div>
        <div className="flex items-center gap-3">
          {/* Market Hours Indicator */}
          {marketHours && (() => {
            const sessionInfo = getSessionInfo(marketHours.session);
            const Icon = sessionInfo.icon;
            return (
              <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border ${
                marketHours.can_trade_stocks ? 'bg-green-900/20 border-green-700' : 'bg-slate-800 border-slate-700'
              }`}>
                <Icon className={`w-4 h-4 ${sessionInfo.color}`} />
                <span className={`text-sm ${sessionInfo.color}`}>
                  {sessionInfo.label}
                </span>
              </div>
            );
          })()}
          <span className={`px-3 py-1 rounded-full text-sm ${state?.is_trading_enabled ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
            {state?.is_trading_enabled ? 'Trading Enabled' : 'Trading Disabled'}
          </span>
          <button
            onClick={handleScan}
            disabled={scanning || !marketHours?.can_trade_stocks}
            className="flex items-center gap-2 px-4 py-2 bg-primary-600 hover:bg-primary-700 disabled:bg-slate-600 rounded-lg text-white transition-colors"
            title={!marketHours?.can_trade_stocks ? 'Market is closed' : ''}
          >
            {scanning ? (
              <RefreshCw className="w-4 h-4 animate-spin" />
            ) : (
              <Search className="w-4 h-4" />
            )}
            {scanning ? 'Scanning...' : 'Scan Market'}
          </button>
        </div>
      </div>

      {/* Market Closed Warning */}
      {marketHours && !marketHours.can_trade_stocks && (
        <div className="p-3 bg-yellow-900/20 border border-yellow-700 rounded-lg flex items-center gap-3">
          <Moon className="w-5 h-5 text-yellow-400" />
          <div className="text-sm">
            <span className="text-yellow-400 font-medium">Market is closed.</span>
            <span className="text-yellow-200/80 ml-2">
              Trading will resume during market hours. {marketHours.time_until_open && `Opens in ${marketHours.time_until_open}.`}
            </span>
          </div>
        </div>
      )}

      {/* Key Metrics */}
      {state && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <MetricCard
            title="Allocated Capital"
            value={formatCurrency(state.allocated_capital)}
            subtitle={`${formatCurrency(state.available_capital)} available`}
            icon={<DollarSign className="w-5 h-5 text-green-400" />}
          />
          <MetricCard
            title="Deployed Capital"
            value={formatCurrency(state.deployed_capital)}
            subtitle={`${((state.deployed_capital / state.allocated_capital) * 100).toFixed(1)}% of allocated`}
            icon={<BarChart3 className="w-5 h-5 text-blue-400" />}
          />
          <MetricCard
            title="Daily P&L"
            value={formatCurrency(state.daily_pnl)}
            valueColor={state.daily_pnl >= 0 ? 'success' : 'danger'}
            icon={<TrendingUp className="w-5 h-5 text-primary-400" />}
          />
          <MetricCard
            title="Open Positions"
            value={`${state.open_positions} / ${state.max_positions}`}
            subtitle={`${state.watchlist_count} on watchlist`}
            icon={<Eye className="w-5 h-5 text-purple-400" />}
          />
        </div>
      )}

      {/* Last Activity */}
      {state && (
        <div className="flex items-center gap-6 text-sm text-slate-400">
          <span>Last Scan: {formatDateTime(state.last_scan)}</span>
          <span>Last Trade: {formatDateTime(state.last_trade)}</span>
        </div>
      )}

      {/* Tabs */}
      <div className="border-b border-slate-700">
        <nav className="flex gap-4">
          {(['watchlist', 'positions', 'history'] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab
                  ? 'border-primary-500 text-primary-400'
                  : 'border-transparent text-slate-400 hover:text-white'
              }`}
            >
              {tab.charAt(0).toUpperCase() + tab.slice(1)}
              {tab === 'watchlist' && ` (${watchlist.length})`}
              {tab === 'positions' && ` (${positions.length})`}
              {tab === 'history' && ` (${history.length})`}
            </button>
          ))}
        </nav>
      </div>

      {/* Watchlist Tab */}
      {activeTab === 'watchlist' && (
        <div className="space-y-4">
          {/* Add Symbol */}
          <div className="flex gap-2">
            <input
              type="text"
              value={newSymbol}
              onChange={(e) => setNewSymbol(e.target.value.toUpperCase())}
              onKeyDown={(e) => e.key === 'Enter' && handleAddSymbol()}
              placeholder="Add symbol (e.g., AAPL)"
              className="px-4 py-2 bg-slate-800 border border-slate-700 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-primary-500"
            />
            <button
              onClick={handleAddSymbol}
              disabled={!newSymbol.trim()}
              className="px-4 py-2 bg-primary-600 hover:bg-primary-700 disabled:bg-slate-600 rounded-lg text-white transition-colors"
            >
              Add
            </button>
          </div>

          {/* Watchlist Table */}
          <div className="bg-slate-800/50 rounded-xl border border-slate-700 overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-slate-700">
                  <th className="px-4 py-3 text-left text-sm font-medium text-slate-400">Symbol</th>
                  <th className="px-4 py-3 text-right text-sm font-medium text-slate-400">Score</th>
                  <th className="px-4 py-3 text-right text-sm font-medium text-slate-400">Technical</th>
                  <th className="px-4 py-3 text-right text-sm font-medium text-slate-400">Fundamental</th>
                  <th className="px-4 py-3 text-right text-sm font-medium text-slate-400">Momentum</th>
                  <th className="px-4 py-3 text-right text-sm font-medium text-slate-400">Entry</th>
                  <th className="px-4 py-3 text-right text-sm font-medium text-slate-400">Target</th>
                  <th className="px-4 py-3 text-right text-sm font-medium text-slate-400">Stop</th>
                  <th className="px-4 py-3 text-center text-sm font-medium text-slate-400">Trigger</th>
                  <th className="px-4 py-3 text-center text-sm font-medium text-slate-400">Actions</th>
                </tr>
              </thead>
              <tbody>
                {watchlist.length === 0 ? (
                  <tr>
                    <td colSpan={10} className="px-4 py-8 text-center text-slate-500">
                      No stocks on watchlist. Run a scan or add symbols manually.
                    </td>
                  </tr>
                ) : (
                  watchlist.map((entry) => (
                    <tr key={entry.id} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                      <td className="px-4 py-3 font-medium text-white">{entry.symbol}</td>
                      <td className={`px-4 py-3 text-right font-bold ${getScoreColor(entry.composite_score)}`}>
                        {entry.composite_score.toFixed(0)}
                      </td>
                      <td className="px-4 py-3 text-right text-slate-300">
                        {entry.technical_score?.toFixed(0) ?? '-'}
                      </td>
                      <td className="px-4 py-3 text-right text-slate-300">
                        {entry.fundamental_score?.toFixed(0) ?? '-'}
                      </td>
                      <td className="px-4 py-3 text-right text-slate-300">
                        {entry.momentum_score?.toFixed(0) ?? '-'}
                      </td>
                      <td className="px-4 py-3 text-right text-slate-300">
                        ${entry.entry_price.toFixed(2)}
                      </td>
                      <td className="px-4 py-3 text-right text-green-400">
                        ${entry.target_price.toFixed(2)}
                      </td>
                      <td className="px-4 py-3 text-right text-red-400">
                        ${entry.stop_loss.toFixed(2)}
                      </td>
                      <td className="px-4 py-3 text-center">
                        <span className={`px-2 py-1 rounded text-xs ${
                          entry.entry_trigger === 'immediate' ? 'bg-green-500/20 text-green-400' :
                          entry.entry_trigger === 'breakout' ? 'bg-blue-500/20 text-blue-400' :
                          'bg-yellow-500/20 text-yellow-400'
                        }`}>
                          {entry.entry_trigger}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-center">
                        <button
                          onClick={() => handleRemoveFromWatchlist(entry.symbol)}
                          className="p-1 text-slate-400 hover:text-red-400 transition-colors"
                          title="Remove from watchlist"
                        >
                          <XCircle className="w-4 h-4" />
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Positions Tab */}
      {activeTab === 'positions' && (
        <div className="bg-slate-800/50 rounded-xl border border-slate-700 overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-slate-700">
                <th className="px-4 py-3 text-left text-sm font-medium text-slate-400">Symbol</th>
                <th className="px-4 py-3 text-right text-sm font-medium text-slate-400">Qty</th>
                <th className="px-4 py-3 text-right text-sm font-medium text-slate-400">Entry</th>
                <th className="px-4 py-3 text-right text-sm font-medium text-slate-400">Current</th>
                <th className="px-4 py-3 text-right text-sm font-medium text-slate-400">Stop</th>
                <th className="px-4 py-3 text-right text-sm font-medium text-slate-400">Target</th>
                <th className="px-4 py-3 text-right text-sm font-medium text-slate-400">Unrealized P&L</th>
                <th className="px-4 py-3 text-right text-sm font-medium text-slate-400">Allocated</th>
                <th className="px-4 py-3 text-center text-sm font-medium text-slate-400">Actions</th>
              </tr>
            </thead>
            <tbody>
              {positions.length === 0 ? (
                <tr>
                  <td colSpan={9} className="px-4 py-8 text-center text-slate-500">
                    No open positions.
                  </td>
                </tr>
              ) : (
                positions.map((pos) => (
                  <tr key={pos.id} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                    <td className="px-4 py-3 font-medium text-white">{pos.symbol}</td>
                    <td className="px-4 py-3 text-right text-slate-300">{pos.quantity}</td>
                    <td className="px-4 py-3 text-right text-slate-300">
                      ${pos.entry_price.toFixed(2)}
                    </td>
                    <td className="px-4 py-3 text-right text-white">
                      {pos.current_price ? `$${pos.current_price.toFixed(2)}` : '-'}
                    </td>
                    <td className="px-4 py-3 text-right text-red-400">
                      {pos.stop_loss ? `$${pos.stop_loss.toFixed(2)}` : '-'}
                    </td>
                    <td className="px-4 py-3 text-right text-green-400">
                      {pos.take_profit ? `$${pos.take_profit.toFixed(2)}` : '-'}
                    </td>
                    <td className={`px-4 py-3 text-right font-medium ${getPnlColor(pos.unrealized_pnl)}`}>
                      {pos.unrealized_pnl !== null ? `$${pos.unrealized_pnl.toFixed(2)}` : '-'}
                    </td>
                    <td className="px-4 py-3 text-right text-slate-300">
                      ${pos.allocated_amount.toFixed(2)}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <button
                        onClick={() => handleClosePosition(pos.id)}
                        className="px-3 py-1 bg-red-500/20 text-red-400 hover:bg-red-500/30 rounded text-sm transition-colors"
                      >
                        Close
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* History Tab */}
      {activeTab === 'history' && (
        <div className="bg-slate-800/50 rounded-xl border border-slate-700 overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-slate-700">
                <th className="px-4 py-3 text-left text-sm font-medium text-slate-400">Symbol</th>
                <th className="px-4 py-3 text-right text-sm font-medium text-slate-400">Qty</th>
                <th className="px-4 py-3 text-right text-sm font-medium text-slate-400">Entry</th>
                <th className="px-4 py-3 text-right text-sm font-medium text-slate-400">Exit</th>
                <th className="px-4 py-3 text-right text-sm font-medium text-slate-400">P&L</th>
                <th className="px-4 py-3 text-center text-sm font-medium text-slate-400">Status</th>
                <th className="px-4 py-3 text-left text-sm font-medium text-slate-400">Entry Reason</th>
                <th className="px-4 py-3 text-left text-sm font-medium text-slate-400">Exit Reason</th>
                <th className="px-4 py-3 text-left text-sm font-medium text-slate-400">Closed At</th>
              </tr>
            </thead>
            <tbody>
              {history.length === 0 ? (
                <tr>
                  <td colSpan={9} className="px-4 py-8 text-center text-slate-500">
                    No trade history yet.
                  </td>
                </tr>
              ) : (
                history.map((trade) => (
                  <tr key={trade.id} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                    <td className="px-4 py-3 font-medium text-white">{trade.symbol}</td>
                    <td className="px-4 py-3 text-right text-slate-300">{trade.quantity}</td>
                    <td className="px-4 py-3 text-right text-slate-300">
                      ${trade.entry_price.toFixed(2)}
                    </td>
                    <td className="px-4 py-3 text-right text-slate-300">
                      {trade.exit_price ? `$${trade.exit_price.toFixed(2)}` : '-'}
                    </td>
                    <td className={`px-4 py-3 text-right font-medium ${getPnlColor(trade.realized_pnl)}`}>
                      {trade.realized_pnl !== null ? `$${trade.realized_pnl.toFixed(2)}` : '-'}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <span className={`px-2 py-1 rounded text-xs ${
                        trade.status === 'target_hit' ? 'bg-green-500/20 text-green-400' :
                        trade.status === 'stopped_out' ? 'bg-red-500/20 text-red-400' :
                        'bg-slate-500/20 text-slate-400'
                      }`}>
                        {trade.status.replace('_', ' ')}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-left text-slate-400 text-sm truncate max-w-[150px]">
                      {trade.entry_reason || '-'}
                    </td>
                    <td className="px-4 py-3 text-left text-slate-400 text-sm">
                      {trade.exit_reason || '-'}
                    </td>
                    <td className="px-4 py-3 text-left text-slate-400 text-sm">
                      {trade.closed_at ? new Date(trade.closed_at).toLocaleDateString() : '-'}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
