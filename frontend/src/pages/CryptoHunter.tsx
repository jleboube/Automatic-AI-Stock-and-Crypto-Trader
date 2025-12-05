import { useEffect, useState, useCallback } from 'react';
import {
  Search, Bitcoin, TrendingUp, DollarSign,
  RefreshCw, Eye, XCircle, BarChart3, Activity, Wallet,
  Settings, Save, X, Play, Pause, Square
} from 'lucide-react';
import {
  getCryptoHunterState,
  getCryptoWatchlist,
  getCryptoPositions,
  getCryptoTradeHistory,
  triggerCryptoScan,
  addToCryptoWatchlist,
  removeFromCryptoWatchlist,
  closeCryptoPosition,
  getCryptoStatus,
  getCryptoAccount,
  getCryptoHoldings,
  getCryptoHunterConfig,
  updateCryptoHunterConfig,
  getCryptoAgents,
  startCryptoAgent,
  stopCryptoAgent,
  pauseCryptoAgent,
  getSchedulerStatus,
  startCryptoScheduler,
  stopCryptoScheduler,
  type CryptoHunterState,
  type CryptoWatchlistEntry,
  type CryptoPosition,
  type CryptoTradeHistory,
  type CryptoAccount,
  type CryptoHolding,
  type CryptoHunterConfig,
  type CryptoAgent,
  type SchedulerStatus,
} from '../services/crypto-api';
import { MetricCard } from '../components/MetricCard';

export function CryptoHunter() {
  const [state, setState] = useState<CryptoHunterState | null>(null);
  const [watchlist, setWatchlist] = useState<CryptoWatchlistEntry[]>([]);
  const [positions, setPositions] = useState<CryptoPosition[]>([]);
  const [history, setHistory] = useState<CryptoTradeHistory[]>([]);
  const [account, setAccount] = useState<CryptoAccount | null>(null);
  const [holdings, setHoldings] = useState<CryptoHolding[]>([]);
  const [connectionStatus, setConnectionStatus] = useState<{ connected: boolean; configured: boolean; message: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'watchlist' | 'positions' | 'history' | 'holdings' | 'config'>('watchlist');
  const [newSymbol, setNewSymbol] = useState('');

  // Configuration state
  const [config, setConfig] = useState<Partial<CryptoHunterConfig>>({});
  const [isEditingConfig, setIsEditingConfig] = useState(false);
  const [editedConfig, setEditedConfig] = useState('');
  const [configError, setConfigError] = useState<string | null>(null);
  const [savingConfig, setSavingConfig] = useState(false);

  // Agent state
  const [agents, setAgents] = useState<CryptoAgent[]>([]);
  const [agentLoading, setAgentLoading] = useState<number | null>(null);

  // Scheduler state
  const [schedulerStatus, setSchedulerStatus] = useState<SchedulerStatus | null>(null);
  const [schedulerLoading, setSchedulerLoading] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const [statusData, stateData, watchlistData, positionsData, historyData, configData, agentsData, schedulerData] = await Promise.all([
        getCryptoStatus(),
        getCryptoHunterState().catch(() => null),
        getCryptoWatchlist().catch(() => []),
        getCryptoPositions().catch(() => []),
        getCryptoTradeHistory(50).catch(() => []),
        getCryptoHunterConfig().catch(() => ({})),
        getCryptoAgents().catch(() => []),
        getSchedulerStatus().catch(() => null),
      ]);

      setConnectionStatus(statusData);

      if (stateData) {
        setState(stateData);
      }
      setWatchlist(watchlistData);
      setPositions(positionsData);
      setHistory(historyData);
      setConfig(configData);
      setAgents(agentsData);
      if (schedulerData) setSchedulerStatus(schedulerData);

      // Fetch account and holdings if connected
      if (statusData.connected) {
        const [accountData, holdingsData] = await Promise.all([
          getCryptoAccount().catch(() => null),
          getCryptoHoldings().catch(() => []),
        ]);
        if (accountData) setAccount(accountData);
        setHoldings(holdingsData);
      }

      setError(null);
    } catch (err) {
      setError('Failed to load Crypto Hunter data');
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    // Crypto markets are 24/7, so we can poll frequently
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const handleScan = async () => {
    setScanning(true);
    try {
      await triggerCryptoScan();
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
      // Format: BTC-USD, ETH-USD, etc.
      const symbol = newSymbol.trim().toUpperCase();
      const formattedSymbol = symbol.includes('-') ? symbol : `${symbol}-USD`;
      await addToCryptoWatchlist(formattedSymbol);
      setNewSymbol('');
      await fetchData();
    } catch (err) {
      console.error('Failed to add symbol:', err);
    }
  };

  const handleRemoveFromWatchlist = async (symbol: string) => {
    try {
      await removeFromCryptoWatchlist(symbol);
      await fetchData();
    } catch (err) {
      console.error('Failed to remove symbol:', err);
    }
  };

  const handleClosePosition = async (positionId: number) => {
    if (!confirm('Are you sure you want to close this position?')) return;
    try {
      await closeCryptoPosition(positionId);
      await fetchData();
    } catch (err) {
      console.error('Failed to close position:', err);
    }
  };

  // Configuration handlers
  const handleEditConfig = () => {
    setEditedConfig(JSON.stringify(config, null, 2));
    setIsEditingConfig(true);
    setConfigError(null);
  };

  const handleCancelEdit = () => {
    setIsEditingConfig(false);
    setEditedConfig('');
    setConfigError(null);
  };

  const handleSaveConfig = async () => {
    try {
      const parsedConfig = JSON.parse(editedConfig);
      setSavingConfig(true);
      setConfigError(null);
      await updateCryptoHunterConfig(parsedConfig);
      setConfig(parsedConfig);
      setIsEditingConfig(false);
      await fetchData();
    } catch (err) {
      if (err instanceof SyntaxError) {
        setConfigError('Invalid JSON format');
      } else {
        setConfigError('Failed to save configuration');
      }
      console.error('Failed to save config:', err);
    } finally {
      setSavingConfig(false);
    }
  };

  // Agent control handlers
  const handleStartAgent = async (agentId: number) => {
    setAgentLoading(agentId);
    try {
      await startCryptoAgent(agentId);
      await fetchData();
    } catch (err) {
      console.error('Failed to start agent:', err);
    } finally {
      setAgentLoading(null);
    }
  };

  const handleStopAgent = async (agentId: number) => {
    setAgentLoading(agentId);
    try {
      await stopCryptoAgent(agentId);
      await fetchData();
    } catch (err) {
      console.error('Failed to stop agent:', err);
    } finally {
      setAgentLoading(null);
    }
  };

  const handlePauseAgent = async (agentId: number) => {
    setAgentLoading(agentId);
    try {
      await pauseCryptoAgent(agentId);
      await fetchData();
    } catch (err) {
      console.error('Failed to pause agent:', err);
    } finally {
      setAgentLoading(null);
    }
  };

  // Scheduler control handlers
  const handleStartScheduler = async () => {
    setSchedulerLoading(true);
    try {
      await startCryptoScheduler();
      await fetchData();
    } catch (err) {
      console.error('Failed to start scheduler:', err);
    } finally {
      setSchedulerLoading(false);
    }
  };

  const handleStopScheduler = async () => {
    setSchedulerLoading(true);
    try {
      await stopCryptoScheduler();
      await fetchData();
    } catch (err) {
      console.error('Failed to stop scheduler:', err);
    } finally {
      setSchedulerLoading(false);
    }
  };

  const isCryptoSchedulerRunning = () => {
    return schedulerStatus?.active_agents?.includes('crypto_hunter') ?? false;
  };

  const getNextRunTime = () => {
    const job = schedulerStatus?.jobs?.find(j => j.name.includes('Crypto Hunter'));
    if (job?.next_run) {
      return new Date(job.next_run).toLocaleString();
    }
    return null;
  };

  const getAgentStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case 'running': return 'bg-green-500/20 text-green-400';
      case 'paused': return 'bg-yellow-500/20 text-yellow-400';
      case 'stopped': return 'bg-red-500/20 text-red-400';
      case 'error': return 'bg-red-500/20 text-red-400';
      default: return 'bg-slate-500/20 text-slate-400';
    }
  };

  const formatDateTime = (dateStr: string | null) => {
    if (!dateStr) return 'Never';
    return new Date(dateStr).toLocaleString();
  };

  const formatCurrency = (value: number | null | undefined) => {
    if (value === null || value === undefined) return '-';
    return `$${value.toFixed(2)}`;
  };

  const formatCrypto = (value: number | null | undefined, precision = 6) => {
    if (value === null || value === undefined) return '-';
    return value.toFixed(precision);
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
        <div className="text-slate-400">Loading Crypto Hunter...</div>
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
            <Bitcoin className="w-7 h-7 text-orange-400" />
            Crypto Hunter
          </h2>
          <p className="text-slate-400">Autonomous crypto discovery and trading via Robinhood</p>
        </div>
        <div className="flex items-center gap-3">
          {/* 24/7 Trading Indicator */}
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg border bg-green-900/20 border-green-700">
            <Activity className="w-4 h-4 text-green-400" />
            <span className="text-sm text-green-400">24/7 Trading</span>
          </div>

          {/* Connection Status */}
          <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border ${
            connectionStatus?.connected
              ? 'bg-green-900/20 border-green-700'
              : 'bg-red-900/20 border-red-700'
          }`}>
            <Wallet className={`w-4 h-4 ${connectionStatus?.connected ? 'text-green-400' : 'text-red-400'}`} />
            <span className={`text-sm ${connectionStatus?.connected ? 'text-green-400' : 'text-red-400'}`}>
              {connectionStatus?.connected ? 'Robinhood Connected' : 'Not Connected'}
            </span>
          </div>

          <span className={`px-3 py-1 rounded-full text-sm ${state?.is_trading_enabled ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
            {state?.is_trading_enabled ? 'Trading Enabled' : 'Trading Disabled'}
          </span>
          <button
            onClick={handleScan}
            disabled={scanning || !connectionStatus?.connected}
            className="flex items-center gap-2 px-4 py-2 bg-orange-600 hover:bg-orange-700 disabled:bg-slate-600 rounded-lg text-white transition-colors"
            title={!connectionStatus?.connected ? 'Robinhood not connected' : ''}
          >
            {scanning ? (
              <RefreshCw className="w-4 h-4 animate-spin" />
            ) : (
              <Search className="w-4 h-4" />
            )}
            {scanning ? 'Scanning...' : 'Scan Crypto'}
          </button>
        </div>
      </div>

      {/* Not Connected Warning */}
      {connectionStatus && !connectionStatus.configured && (
        <div className="p-3 bg-yellow-900/20 border border-yellow-700 rounded-lg flex items-center gap-3">
          <Wallet className="w-5 h-5 text-yellow-400" />
          <div className="text-sm">
            <span className="text-yellow-400 font-medium">Robinhood API not configured.</span>
            <span className="text-yellow-200/80 ml-2">
              Set ROBINHOOD_API_KEY and ROBINHOOD_PRIVATE_KEY environment variables.
            </span>
          </div>
        </div>
      )}

      {/* Account Info */}
      {account && (
        <div className="p-4 bg-slate-800/50 rounded-xl border border-slate-700">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div>
                <span className="text-sm text-slate-400">Buying Power</span>
                <p className="text-xl font-bold text-white">{formatCurrency(account.buying_power)}</p>
              </div>
              <div className="w-px h-10 bg-slate-600" />
              <div>
                <span className="text-sm text-slate-400">Equity</span>
                <p className="text-xl font-bold text-green-400">{formatCurrency(account.equity)}</p>
              </div>
            </div>
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
            icon={<TrendingUp className="w-5 h-5 text-orange-400" />}
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
          {(['watchlist', 'positions', 'history', 'holdings', 'config'] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors flex items-center gap-2 ${
                activeTab === tab
                  ? 'border-orange-500 text-orange-400'
                  : 'border-transparent text-slate-400 hover:text-white'
              }`}
            >
              {tab === 'config' && <Settings className="w-4 h-4" />}
              {tab === 'config' ? 'Configuration' : tab.charAt(0).toUpperCase() + tab.slice(1)}
              {tab === 'watchlist' && ` (${watchlist.length})`}
              {tab === 'positions' && ` (${positions.length})`}
              {tab === 'history' && ` (${history.length})`}
              {tab === 'holdings' && ` (${holdings.length})`}
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
              placeholder="Add symbol (e.g., BTC or BTC-USD)"
              className="px-4 py-2 bg-slate-800 border border-slate-700 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-orange-500"
            />
            <button
              onClick={handleAddSymbol}
              disabled={!newSymbol.trim()}
              className="px-4 py-2 bg-orange-600 hover:bg-orange-700 disabled:bg-slate-600 rounded-lg text-white transition-colors"
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
                      No crypto on watchlist. Run a scan or add symbols manually.
                    </td>
                  </tr>
                ) : (
                  watchlist.map((entry) => (
                    <tr key={entry.id} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                      <td className="px-4 py-3 font-medium text-white flex items-center gap-2">
                        <Bitcoin className="w-4 h-4 text-orange-400" />
                        {entry.symbol}
                      </td>
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
                <th className="px-4 py-3 text-right text-sm font-medium text-slate-400">Quantity</th>
                <th className="px-4 py-3 text-right text-sm font-medium text-slate-400">Entry</th>
                <th className="px-4 py-3 text-right text-sm font-medium text-slate-400">Current</th>
                <th className="px-4 py-3 text-right text-sm font-medium text-slate-400">Cost</th>
                <th className="px-4 py-3 text-right text-sm font-medium text-slate-400">Value</th>
                <th className="px-4 py-3 text-right text-sm font-medium text-slate-400">P&L</th>
                <th className="px-4 py-3 text-right text-sm font-medium text-slate-400">P&L %</th>
                <th className="px-4 py-3 text-center text-sm font-medium text-slate-400">Actions</th>
              </tr>
            </thead>
            <tbody>
              {positions.length === 0 ? (
                <tr>
                  <td colSpan={9} className="px-4 py-8 text-center text-slate-500">
                    No open crypto positions.
                  </td>
                </tr>
              ) : (
                positions.map((pos) => {
                  const costBasis = pos.allocated_amount;
                  const marketValue = pos.current_price ? pos.quantity * pos.current_price : null;
                  const pnlPercent = costBasis > 0 && pos.unrealized_pnl !== null
                    ? (pos.unrealized_pnl / costBasis) * 100
                    : null;

                  return (
                    <tr key={pos.id} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                      <td className="px-4 py-3 font-medium text-white flex items-center gap-2">
                        <Bitcoin className="w-4 h-4 text-orange-400" />
                        {pos.symbol}
                      </td>
                      <td className="px-4 py-3 text-right text-slate-300">{formatCrypto(pos.quantity)}</td>
                      <td className="px-4 py-3 text-right text-slate-300">
                        {pos.entry_price < 0.01 ? `$${pos.entry_price.toPrecision(4)}` : `$${pos.entry_price.toFixed(2)}`}
                      </td>
                      <td className="px-4 py-3 text-right text-white">
                        {pos.current_price
                          ? (pos.current_price < 0.01 ? `$${pos.current_price.toPrecision(4)}` : `$${pos.current_price.toFixed(2)}`)
                          : '-'}
                      </td>
                      <td className="px-4 py-3 text-right text-slate-300">
                        ${costBasis.toFixed(2)}
                      </td>
                      <td className="px-4 py-3 text-right text-white font-medium">
                        {marketValue !== null ? `$${marketValue.toFixed(2)}` : '-'}
                      </td>
                      <td className={`px-4 py-3 text-right font-medium ${getPnlColor(pos.unrealized_pnl)}`}>
                        {pos.unrealized_pnl !== null
                          ? `${pos.unrealized_pnl >= 0 ? '+' : ''}$${pos.unrealized_pnl.toFixed(2)}`
                          : '-'}
                      </td>
                      <td className={`px-4 py-3 text-right font-medium ${getPnlColor(pnlPercent)}`}>
                        {pnlPercent !== null
                          ? `${pnlPercent >= 0 ? '+' : ''}${pnlPercent.toFixed(2)}%`
                          : '-'}
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
                  );
                })
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
                    No crypto trade history yet.
                  </td>
                </tr>
              ) : (
                history.map((trade) => (
                  <tr key={trade.id} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                    <td className="px-4 py-3 font-medium text-white flex items-center gap-2">
                      <Bitcoin className="w-4 h-4 text-orange-400" />
                      {trade.symbol}
                    </td>
                    <td className="px-4 py-3 text-right text-slate-300">{formatCrypto(trade.quantity)}</td>
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

      {/* Holdings Tab (Robinhood Holdings) */}
      {activeTab === 'holdings' && (
        <div className="bg-slate-800/50 rounded-xl border border-slate-700 overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-slate-700">
                <th className="px-4 py-3 text-left text-sm font-medium text-slate-400">Symbol</th>
                <th className="px-4 py-3 text-right text-sm font-medium text-slate-400">Quantity</th>
                <th className="px-4 py-3 text-right text-sm font-medium text-slate-400">Available</th>
                <th className="px-4 py-3 text-right text-sm font-medium text-slate-400">Avg Price</th>
                <th className="px-4 py-3 text-right text-sm font-medium text-slate-400">Cost Basis</th>
              </tr>
            </thead>
            <tbody>
              {holdings.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-slate-500">
                    No crypto holdings in Robinhood.
                  </td>
                </tr>
              ) : (
                holdings.map((holding, idx) => (
                  <tr key={idx} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                    <td className="px-4 py-3 font-medium text-white flex items-center gap-2">
                      <Bitcoin className="w-4 h-4 text-orange-400" />
                      {holding.symbol}
                    </td>
                    <td className="px-4 py-3 text-right text-slate-300">{formatCrypto(holding.quantity, 8)}</td>
                    <td className="px-4 py-3 text-right text-slate-300">{formatCrypto(holding.quantity_available, 8)}</td>
                    <td className="px-4 py-3 text-right text-slate-300">
                      ${holding.average_price.toFixed(2)}
                    </td>
                    <td className="px-4 py-3 text-right text-white">
                      ${holding.cost_basis.toFixed(2)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Configuration Tab */}
      {activeTab === 'config' && (
        <div className="space-y-6">
          {/* Autonomous Trading Scheduler Section */}
          <div className="bg-slate-800/50 rounded-xl border border-slate-700 overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-700 flex items-center justify-between">
              <h3 className="text-lg font-medium text-white flex items-center gap-2">
                <RefreshCw className="w-5 h-5 text-orange-400" />
                Autonomous Trading Scheduler
              </h3>
              <div className="flex items-center gap-3">
                {isCryptoSchedulerRunning() ? (
                  <span className="px-3 py-1 rounded-full text-sm bg-green-500/20 text-green-400 flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
                    Running
                  </span>
                ) : (
                  <span className="px-3 py-1 rounded-full text-sm bg-slate-500/20 text-slate-400">
                    Stopped
                  </span>
                )}
              </div>
            </div>
            <div className="p-4">
              <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
                <div className="space-y-2">
                  <p className="text-slate-400 text-sm">
                    When enabled, the Crypto Hunter will automatically scan the market and execute trades
                    at the interval specified in your configuration (<code className="text-orange-300">scan_interval_minutes</code>).
                  </p>
                  {isCryptoSchedulerRunning() && getNextRunTime() && (
                    <p className="text-sm">
                      <span className="text-slate-500">Next scan: </span>
                      <span className="text-orange-400 font-medium">{getNextRunTime()}</span>
                    </p>
                  )}
                  {!isCryptoSchedulerRunning() && (
                    <p className="text-yellow-400 text-sm flex items-center gap-2">
                      <Activity className="w-4 h-4" />
                      Start the scheduler to enable 24/7 autonomous trading
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  {isCryptoSchedulerRunning() ? (
                    <button
                      onClick={handleStopScheduler}
                      disabled={schedulerLoading || !connectionStatus?.connected}
                      className="px-6 py-3 bg-red-600 hover:bg-red-700 disabled:bg-slate-600 rounded-lg text-white transition-colors flex items-center gap-2"
                    >
                      {schedulerLoading ? (
                        <RefreshCw className="w-4 h-4 animate-spin" />
                      ) : (
                        <Square className="w-4 h-4" />
                      )}
                      Stop Scheduler
                    </button>
                  ) : (
                    <button
                      onClick={handleStartScheduler}
                      disabled={schedulerLoading || !connectionStatus?.connected}
                      className="px-6 py-3 bg-green-600 hover:bg-green-700 disabled:bg-slate-600 rounded-lg text-white transition-colors flex items-center gap-2"
                      title={!connectionStatus?.connected ? 'Robinhood not connected' : ''}
                    >
                      {schedulerLoading ? (
                        <RefreshCw className="w-4 h-4 animate-spin" />
                      ) : (
                        <Play className="w-4 h-4" />
                      )}
                      Start Autonomous Trading
                    </button>
                  )}
                </div>
              </div>

              {/* Scheduler Requirements */}
              <div className="mt-4 p-3 bg-slate-700/30 rounded-lg text-sm">
                <h4 className="font-medium text-slate-300 mb-2">Requirements for Autonomous Trading:</h4>
                <ul className="space-y-1 text-slate-400">
                  <li className="flex items-center gap-2">
                    <span className={connectionStatus?.connected ? 'text-green-400' : 'text-red-400'}>
                      {connectionStatus?.connected ? '✓' : '✗'}
                    </span>
                    Robinhood API connected
                  </li>
                  <li className="flex items-center gap-2">
                    <span className={config.trading_enabled || config.auto_trade ? 'text-green-400' : 'text-red-400'}>
                      {config.trading_enabled || config.auto_trade ? '✓' : '✗'}
                    </span>
                    Trading enabled in config (<code className="text-orange-300">trading_enabled</code> or <code className="text-orange-300">auto_trade</code>)
                  </li>
                  <li className="flex items-center gap-2">
                    <span className={(config.allocated_capital || 0) > 0 ? 'text-green-400' : 'text-red-400'}>
                      {(config.allocated_capital || 0) > 0 ? '✓' : '✗'}
                    </span>
                    Capital allocated (${(config.allocated_capital || 0).toLocaleString()})
                  </li>
                </ul>
              </div>
            </div>
          </div>

          {/* Agents Section */}
          <div className="bg-slate-800/50 rounded-xl border border-slate-700 overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-700 flex items-center justify-between">
              <h3 className="text-lg font-medium text-white flex items-center gap-2">
                <Activity className="w-5 h-5 text-orange-400" />
                Crypto Agents
              </h3>
            </div>
            <div className="p-4">
              {agents.length === 0 ? (
                <p className="text-slate-500 text-center py-4">No crypto agents found.</p>
              ) : (
                <div className="space-y-3">
                  {agents.map((agent) => (
                    <div
                      key={agent.id}
                      className="flex items-center justify-between p-4 bg-slate-700/50 rounded-lg"
                    >
                      <div className="flex items-center gap-4">
                        <Bitcoin className="w-8 h-8 text-orange-400" />
                        <div>
                          <h4 className="font-medium text-white">{agent.name.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase())}</h4>
                          <p className="text-sm text-slate-400">{agent.agent_type}</p>
                        </div>
                        <span className={`px-3 py-1 rounded-full text-xs font-medium ${getAgentStatusColor(agent.status)}`}>
                          {agent.status}
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        {agent.status !== 'running' && (
                          <button
                            onClick={() => handleStartAgent(agent.id)}
                            disabled={agentLoading === agent.id || !agent.is_active}
                            className="p-2 bg-green-500/20 text-green-400 hover:bg-green-500/30 disabled:opacity-50 rounded-lg transition-colors"
                            title="Start"
                          >
                            <Play className="w-4 h-4" />
                          </button>
                        )}
                        {agent.status === 'running' && (
                          <button
                            onClick={() => handlePauseAgent(agent.id)}
                            disabled={agentLoading === agent.id}
                            className="p-2 bg-yellow-500/20 text-yellow-400 hover:bg-yellow-500/30 disabled:opacity-50 rounded-lg transition-colors"
                            title="Pause"
                          >
                            <Pause className="w-4 h-4" />
                          </button>
                        )}
                        {(agent.status === 'running' || agent.status === 'paused') && (
                          <button
                            onClick={() => handleStopAgent(agent.id)}
                            disabled={agentLoading === agent.id}
                            className="p-2 bg-red-500/20 text-red-400 hover:bg-red-500/30 disabled:opacity-50 rounded-lg transition-colors"
                            title="Stop"
                          >
                            <Square className="w-4 h-4" />
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Configuration Editor Section */}
          <div className="bg-slate-800/50 rounded-xl border border-slate-700 overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-700 flex items-center justify-between">
              <h3 className="text-lg font-medium text-white flex items-center gap-2">
                <Settings className="w-5 h-5 text-orange-400" />
                Agent Configuration
              </h3>
              {!isEditingConfig ? (
                <button
                  onClick={handleEditConfig}
                  className="px-4 py-2 bg-orange-600 hover:bg-orange-700 rounded-lg text-white text-sm transition-colors"
                >
                  Edit Configuration
                </button>
              ) : (
                <div className="flex items-center gap-2">
                  <button
                    onClick={handleCancelEdit}
                    disabled={savingConfig}
                    className="px-4 py-2 bg-slate-600 hover:bg-slate-500 rounded-lg text-white text-sm transition-colors flex items-center gap-2"
                  >
                    <X className="w-4 h-4" />
                    Cancel
                  </button>
                  <button
                    onClick={handleSaveConfig}
                    disabled={savingConfig}
                    className="px-4 py-2 bg-green-600 hover:bg-green-700 disabled:bg-slate-600 rounded-lg text-white text-sm transition-colors flex items-center gap-2"
                  >
                    {savingConfig ? (
                      <RefreshCw className="w-4 h-4 animate-spin" />
                    ) : (
                      <Save className="w-4 h-4" />
                    )}
                    {savingConfig ? 'Saving...' : 'Save'}
                  </button>
                </div>
              )}
            </div>
            <div className="p-4">
              {configError && (
                <div className="mb-4 p-3 bg-red-900/20 border border-red-700 rounded-lg text-red-400 text-sm">
                  {configError}
                </div>
              )}

              {isEditingConfig ? (
                <textarea
                  value={editedConfig}
                  onChange={(e) => setEditedConfig(e.target.value)}
                  className="w-full h-96 p-4 bg-slate-900 border border-slate-600 rounded-lg text-white font-mono text-sm focus:outline-none focus:border-orange-500 resize-y"
                  spellCheck={false}
                />
              ) : (
                <div className="space-y-4">
                  {/* Quick Stats */}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div className="p-4 bg-slate-700/50 rounded-lg">
                      <span className="text-sm text-slate-400">Allocated Capital</span>
                      <p className="text-xl font-bold text-green-400">
                        ${(config.allocated_capital || 0).toLocaleString()}
                      </p>
                    </div>
                    <div className="p-4 bg-slate-700/50 rounded-lg">
                      <span className="text-sm text-slate-400">Max Positions</span>
                      <p className="text-xl font-bold text-white">{config.max_positions || 5}</p>
                    </div>
                    <div className="p-4 bg-slate-700/50 rounded-lg">
                      <span className="text-sm text-slate-400">Min Score</span>
                      <p className="text-xl font-bold text-white">{config.min_composite_score || 65}</p>
                    </div>
                    <div className="p-4 bg-slate-700/50 rounded-lg">
                      <span className="text-sm text-slate-400">Trading</span>
                      <p className={`text-xl font-bold ${config.trading_enabled ? 'text-green-400' : 'text-red-400'}`}>
                        {config.trading_enabled ? 'Enabled' : 'Disabled'}
                      </p>
                    </div>
                  </div>

                  {/* Full Config Display */}
                  <div>
                    <h4 className="text-sm font-medium text-slate-400 mb-2">Full Configuration (JSON)</h4>
                    <pre className="p-4 bg-slate-900 rounded-lg text-slate-300 font-mono text-sm overflow-x-auto">
                      {JSON.stringify(config, null, 2) || '{}'}
                    </pre>
                  </div>

                  {/* Config Help */}
                  <div className="p-4 bg-slate-700/30 rounded-lg">
                    <h4 className="text-sm font-medium text-orange-400 mb-2">Configuration Options</h4>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-sm text-slate-400">
                      <div><code className="text-orange-300">allocated_capital</code>: Total USD to allocate</div>
                      <div><code className="text-orange-300">max_positions</code>: Maximum concurrent positions</div>
                      <div><code className="text-orange-300">min_composite_score</code>: Minimum score to trade (0-100)</div>
                      <div><code className="text-orange-300">position_size_percent</code>: % of capital per position</div>
                      <div><code className="text-orange-300">stop_loss_percent</code>: Stop loss % from entry</div>
                      <div><code className="text-orange-300">take_profit_percent</code>: Take profit % from entry</div>
                      <div><code className="text-orange-300">trading_enabled</code>: Enable/disable live trading</div>
                      <div><code className="text-orange-300">scan_interval_minutes</code>: Auto-scan interval</div>
                      <div><code className="text-orange-300">max_daily_trades</code>: Max trades per day</div>
                      <div><code className="text-orange-300">cooldown_after_loss_minutes</code>: Pause after loss</div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
