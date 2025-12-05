import { useEffect, useState, useCallback } from 'react';
import { DollarSign, TrendingUp, Percent, BarChart3 } from 'lucide-react';
import { getDashboard, getPnLChart, startAgent, stopAgent, pauseAgent } from '../services/api';
import type { DashboardData, PnLChartData, Alert, WebSocketMessage } from '../types';
import { MetricCard } from '../components/MetricCard';
import { AgentCard } from '../components/AgentCard';
import { TradesTable } from '../components/TradesTable';
import { PnLChart } from '../components/PnLChart';
import { RegimeBadge } from '../components/StatusBadge';
import { AlertsList } from '../components/AlertBanner';
import { useWebSocket } from '../hooks/useWebSocket';

export function Dashboard() {
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [pnlData, setPnlData] = useState<PnLChartData[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const handleWebSocketMessage = useCallback((msg: WebSocketMessage) => {
    if (msg.type === 'alert') {
      setAlerts(prev => [
        {
          type: msg.message || 'Alert',
          level: msg.level || 'info',
          message: msg.message || '',
          timestamp: new Date().toISOString(),
        },
        ...prev.slice(0, 9),
      ]);
    } else if (msg.type === 'regime_change') {
      // Refresh dashboard on regime change
      fetchData();
    } else if (msg.type === 'agent_update' || msg.type === 'trade_update') {
      // Refresh dashboard on updates
      fetchData();
    }
  }, []);

  useWebSocket(handleWebSocketMessage);

  const fetchData = async () => {
    try {
      const [dashboardData, pnlChartData] = await Promise.all([
        getDashboard(),
        getPnLChart(30),
      ]);
      setDashboard(dashboardData);
      setPnlData(pnlChartData);
      setError(null);
    } catch (err) {
      setError('Failed to load dashboard data');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000); // Refresh every 30s
    return () => clearInterval(interval);
  }, []);

  const handleStartAgent = async (id: number) => {
    try {
      await startAgent(id);
      fetchData();
    } catch (err) {
      console.error('Failed to start agent:', err);
    }
  };

  const handleStopAgent = async (id: number) => {
    try {
      await stopAgent(id);
      fetchData();
    } catch (err) {
      console.error('Failed to stop agent:', err);
    }
  };

  const handlePauseAgent = async (id: number) => {
    try {
      await pauseAgent(id);
      fetchData();
    } catch (err) {
      console.error('Failed to pause agent:', err);
    }
  };

  const dismissAlert = (index: number) => {
    setAlerts(prev => prev.filter((_, i) => i !== index));
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-slate-400">Loading dashboard...</div>
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

  if (!dashboard) return null;

  return (
    <div className="space-y-6">
      {/* Alerts */}
      <AlertsList alerts={alerts} onDismiss={dismissAlert} />

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-white">Dashboard</h2>
          <p className="text-slate-400">Real-time trading overview</p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-slate-400 text-sm">Current Regime:</span>
          <RegimeBadge regime={dashboard.current_regime} />
        </div>
      </div>

      {/* Key Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          title="QQQ Price"
          value={dashboard.qqq_price ? `$${dashboard.qqq_price.toFixed(2)}` : null}
          icon={<TrendingUp className="w-5 h-5 text-primary-400" />}
        />
        <MetricCard
          title="Total P&L"
          value={dashboard.trade_summary?.total_pnl ? `$${dashboard.trade_summary.total_pnl.toFixed(2)}` : '$0.00'}
          valueColor={dashboard.trade_summary?.total_pnl && dashboard.trade_summary.total_pnl >= 0 ? 'success' : 'danger'}
          icon={<DollarSign className="w-5 h-5 text-green-400" />}
          trend={dashboard.trade_summary?.total_pnl && dashboard.trade_summary.total_pnl >= 0 ? 'up' : 'down'}
        />
        <MetricCard
          title="Win Rate"
          value={dashboard.trade_summary?.win_rate ? `${dashboard.trade_summary.win_rate.toFixed(1)}%` : '0%'}
          icon={<Percent className="w-5 h-5 text-blue-400" />}
        />
        <MetricCard
          title="Open Trades"
          value={dashboard.trade_summary?.open_trades ?? 0}
          subtitle={`${dashboard.trade_summary?.total_trades ?? 0} total trades`}
          icon={<BarChart3 className="w-5 h-5 text-purple-400" />}
        />
      </div>

      {/* P&L Chart */}
      <PnLChart data={pnlData} />

      {/* Agents Grid */}
      <div>
        <h3 className="text-lg font-semibold text-white mb-4">Trading Agents</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {dashboard.agents.map((agent) => (
            <AgentCard
              key={agent.agent_id}
              agent={agent}
              onStart={handleStartAgent}
              onStop={handleStopAgent}
              onPause={handlePauseAgent}
            />
          ))}
        </div>
      </div>

      {/* Recent Trades */}
      <TradesTable trades={dashboard.recent_trades as any} />
    </div>
  );
}
