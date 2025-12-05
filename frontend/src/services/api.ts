import type { Agent, Trade, DashboardData, PnLChartData, Regime } from '../types';

const API_BASE = '/api';

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${url}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });

  if (!response.ok) {
    throw new Error(`API Error: ${response.status} ${response.statusText}`);
  }

  return response.json();
}

// Agents
export const getAgents = () => fetchJson<Agent[]>('/agents/');

export const getAgent = (id: number) => fetchJson<Agent>(`/agents/${id}`);

export const updateAgent = (id: number, data: { name?: string; description?: string; is_active?: boolean; config?: Record<string, unknown> }) =>
  fetchJson<Agent>(`/agents/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });

export const startAgent = (id: number) =>
  fetchJson<Agent>(`/agents/${id}/start`, { method: 'POST' });

export const stopAgent = (id: number) =>
  fetchJson<Agent>(`/agents/${id}/stop`, { method: 'POST' });

export const pauseAgent = (id: number) =>
  fetchJson<Agent>(`/agents/${id}/pause`, { method: 'POST' });

// Agent Activities
export interface AgentActivity {
  id: number;
  agent_id?: number;
  activity_type: string;
  message: string;
  details: Record<string, unknown> | null;
  created_at: string | null;
}

export const getAgentActivities = (agentId: number, limit = 50) =>
  fetchJson<AgentActivity[]>(`/agents/${agentId}/activities?limit=${limit}`);

export const getAllActivities = (limit = 100) =>
  fetchJson<AgentActivity[]>(`/agents/activities/all?limit=${limit}`);

// Trades
export const getTrades = (limit = 100) =>
  fetchJson<Trade[]>(`/trades/?limit=${limit}`);

export const getOpenTrades = () => fetchJson<Trade[]>('/trades/open');

export const getTradeStats = () =>
  fetchJson<{ total_trades: number; open_trades: number; closed_trades: number; total_pnl: number; win_rate: number; avg_premium: number }>('/trades/stats');

// Metrics
export const getDashboard = () => fetchJson<DashboardData>('/metrics/dashboard');

export const getPnLChart = (days = 30) =>
  fetchJson<PnLChartData[]>(`/metrics/pnl-chart?days=${days}`);

export const getTradesByType = () =>
  fetchJson<Record<string, Trade[]>>('/metrics/trades-by-type');

// Orchestrator
export const getCurrentRegime = () => fetchJson<Regime>('/orchestrator/regime');

export interface MarketHoursStatus {
  session: 'closed' | 'pre_market' | 'regular' | 'after_hours' | 'weekend' | 'holiday';
  is_open: boolean;
  can_trade_stocks: boolean;
  can_trade_options: boolean;
  current_time_et: string;
  time_until_open: string | null;
  time_until_close: string | null;
}

export const getMarketHours = () =>
  fetchJson<MarketHoursStatus & { time_until_open_formatted?: string; time_until_close_formatted?: string }>('/orchestrator/market-hours');

export const getOrchestratorStatus = () =>
  fetchJson<{
    current_regime: string | null;
    regime_started_at: string | null;
    market_data: { qqq_price: number; vix: number; iv_7day_atm: number; timestamp: string };
    market_hours: MarketHoursStatus;
    active_agents: string[];
    total_agents: number;
    pending_recommendations: number;
  }>('/orchestrator/status');

export const executeWeekly = () =>
  fetchJson<{ regime: string; actions: string[]; timestamp: string; market_data: unknown }>('/orchestrator/execute', { method: 'POST' });

export const emergencyShutdown = () =>
  fetchJson<{ status: string; trades_closed: number }>('/orchestrator/shutdown', { method: 'POST' });

// Broker (Interactive Brokers)
export interface BrokerStatus {
  connected: boolean;
  host: string;
  port: number;
  message: string;
}

export interface AccountSummary {
  account_id: string;
  net_liquidation: number;
  buying_power: number;
  available_funds: number;
  excess_liquidity: number;
  maintenance_margin: number;
  unrealized_pnl: number;
  realized_pnl: number;
}

export interface Position {
  symbol: string;
  contract_type: string;
  quantity: number;
  avg_cost: number;
  market_value: number;
  unrealized_pnl: number;
}

export interface PutSpread {
  short_strike: number;
  long_strike: number;
  short_premium: number;
  long_premium: number;
  net_credit: number;
  max_risk: number;
  short_delta: number;
  expiration: string;
  qqq_price: number;
}

export const getBrokerStatus = () => fetchJson<BrokerStatus>('/broker/status');

export const connectBroker = () =>
  fetchJson<{ status: string }>('/broker/connect', { method: 'POST' });

export const disconnectBroker = () =>
  fetchJson<{ status: string }>('/broker/disconnect', { method: 'POST' });

export const getAccountSummary = () => fetchJson<AccountSummary>('/broker/account');

export const getBrokerPositions = () => fetchJson<Position[]>('/broker/positions');

export const getQQQPrice = () => fetchJson<{ symbol: string; price: number }>('/broker/qqq-price');

export const findPutSpread = () => fetchJson<PutSpread>('/broker/find-put-spread');

export const placeSpreadOrder = (data: {
  short_strike: number;
  long_strike: number;
  expiration: string;
  right: string;
  quantity: number;
  limit_price: number;
}) => fetchJson<{ order_id: string; status: string }>('/broker/place-spread', {
  method: 'POST',
  body: JSON.stringify(data),
});

export const getOpenOrders = () => fetchJson<Array<{
  order_id: number;
  symbol: string;
  action: string;
  quantity: number;
  order_type: string;
  limit_price: number | null;
  status: string;
}>>('/broker/open-orders');

export const cancelOrder = (orderId: number) =>
  fetchJson<{ order_id: number; status: string }>(`/broker/orders/${orderId}`, { method: 'DELETE' });

// Trade Recommendations
export interface TradeRecommendation {
  id: number;
  created_at: string | null;
  expires_at: string | null;
  status: 'pending' | 'approved' | 'rejected' | 'executed' | 'expired';
  regime_type: string;
  qqq_price: number;
  vix: number | null;
  action: string;
  trade_type: string | null;
  symbol: string;
  short_strike: number | null;
  long_strike: number | null;
  expiration: string | null;
  contracts: number | null;
  estimated_credit: number | null;
  estimated_debit: number | null;
  max_risk: number | null;
  max_profit: number | null;
  short_delta: number | null;
  reasoning: string | null;
  risk_assessment: string | null;
  approved_at: string | null;
  executed_at: string | null;
  rejected_at: string | null;
  rejection_reason: string | null;
  order_id: string | null;
  execution_price: number | null;
}

export interface AnalyzeResult {
  mode: string;
  regime: string;
  market_data: {
    qqq_price: number;
    vix: number;
    iv_7day_atm: number;
    timestamp: string;
    source: string;
  };
  recommendations_count: number;
  recommendations: Array<{
    id: number;
    action: string;
    trade_type: string | null;
    short_strike: number | null;
    long_strike: number | null;
    contracts: number | null;
    estimated_credit: number | null;
    max_risk: number | null;
    expiration: string | null;
    reasoning: string | null;
    status: string;
  }>;
  timestamp: string;
}

export const analyzeMarket = () =>
  fetchJson<AnalyzeResult>('/orchestrator/analyze', { method: 'POST' });

export const getRecommendations = (pendingOnly = true, limit = 50) =>
  fetchJson<TradeRecommendation[]>(`/orchestrator/recommendations?pending_only=${pendingOnly}&limit=${limit}`);

export const getRecommendation = (id: number) =>
  fetchJson<TradeRecommendation>(`/orchestrator/recommendations/${id}`);

export const approveRecommendation = (id: number) =>
  fetchJson<{ status: string; recommendation_id: number; message: string }>(
    `/orchestrator/recommendations/${id}/approve`,
    { method: 'POST' }
  );

export const rejectRecommendation = (id: number, reason?: string) =>
  fetchJson<{ status: string; recommendation_id: number; reason: string | null }>(
    `/orchestrator/recommendations/${id}/reject`,
    {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }
  );

export const executeRecommendation = (id: number) =>
  fetchJson<{ status: string; recommendation_id: number; order_id: string; execution_price: number; action: string }>(
    `/orchestrator/recommendations/${id}/execute`,
    { method: 'POST' }
  );

// Gem Hunter
export interface GemHunterState {
  agent_id: number;
  status: string;
  allocated_capital: number;
  deployed_capital: number;
  available_capital: number;
  daily_pnl: number;
  total_pnl: number;
  open_positions: number;
  max_positions: number;
  watchlist_count: number;
  last_scan: string | null;
  last_trade: string | null;
  is_trading_enabled: boolean;
}

export interface GemWatchlistEntry {
  id: number;
  symbol: string;
  composite_score: number;
  technical_score: number | null;
  fundamental_score: number | null;
  momentum_score: number | null;
  entry_price: number;
  target_price: number;
  stop_loss: number;
  entry_trigger: string;
  created_at: string | null;
}

export interface GemPosition {
  id: number;
  symbol: string;
  position_type: string;
  quantity: number;
  entry_price: number;
  current_price: number | null;
  stop_loss: number | null;
  take_profit: number | null;
  unrealized_pnl: number | null;
  allocated_amount: number;
  created_at: string | null;
}

export interface GemTradeHistory {
  id: number;
  symbol: string;
  position_type: string;
  quantity: number;
  entry_price: number;
  exit_price: number | null;
  realized_pnl: number | null;
  status: string;
  entry_reason: string | null;
  exit_reason: string | null;
  created_at: string | null;
  closed_at: string | null;
}

export interface GemScanResult {
  timestamp: string;
  screened: number;
  analyzed: number;
  added_to_watchlist: number;
  trades_executed: number;
  positions_closed: number;
  errors: string[];
}

export const getGemHunterState = () =>
  fetchJson<GemHunterState>('/gem-hunter/state');

export const getGemWatchlist = () =>
  fetchJson<GemWatchlistEntry[]>('/gem-hunter/watchlist');

export const getGemPositions = () =>
  fetchJson<GemPosition[]>('/gem-hunter/positions');

export const getGemTradeHistory = (limit = 50) =>
  fetchJson<GemTradeHistory[]>(`/gem-hunter/history?limit=${limit}`);

export const triggerGemScan = () =>
  fetchJson<GemScanResult>('/gem-hunter/scan', { method: 'POST' });

export const addToGemWatchlist = (symbol: string) =>
  fetchJson<{ success: boolean; message: string }>('/gem-hunter/watchlist/add', {
    method: 'POST',
    body: JSON.stringify({ symbol }),
  });

export const removeFromGemWatchlist = (symbol: string) =>
  fetchJson<{ success: boolean; message: string }>(`/gem-hunter/watchlist/${symbol}/remove`, {
    method: 'POST',
  });

export const closeGemPosition = (positionId: number) =>
  fetchJson<{ success: boolean; message: string }>(`/gem-hunter/positions/${positionId}/close`, {
    method: 'POST',
  });

export const getGemHunterConfig = () =>
  fetchJson<Record<string, unknown>>('/gem-hunter/config');

export const updateGemHunterConfig = (config: Record<string, unknown>) =>
  fetchJson<Record<string, unknown>>('/gem-hunter/config', {
    method: 'PATCH',
    body: JSON.stringify(config),
  });
