/**
 * Crypto Hunter API functions
 *
 * Provides API calls for the Robinhood Crypto trading agent.
 */

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

// Types
export interface CryptoHunterState {
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

export interface CryptoWatchlistEntry {
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

export interface CryptoPosition {
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

export interface CryptoTradeHistory {
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

export interface CryptoScanResult {
  timestamp: string;
  screened: number;
  analyzed: number;
  added_to_watchlist: number;
  trades_executed: number;
  positions_closed: number;
  errors: string[];
}

export interface CryptoQuote {
  symbol: string;
  price: number;
  bid: number | null;
  ask: number | null;
  volume_24h: number | null;
  high_24h: number | null;
  low_24h: number | null;
  change_24h: number | null;
  change_pct_24h: number | null;
  timestamp: string;
}

export interface CryptoAccount {
  buying_power: number;
  buying_power_currency: string;
  equity: number;
  equity_currency: string;
}

export interface CryptoHolding {
  symbol: string;
  quantity: number;
  quantity_available: number;
  average_price: number;
  cost_basis: number;
}

export interface CryptoAgent {
  id: number;
  name: string;
  agent_type: string;
  status: string;
  is_active: boolean;
  config: Record<string, unknown>;
}

export interface TradingPair {
  symbol: string;
  name: string;
  tradable: boolean;
  min_order_quantity: number;
  max_order_quantity: number;
  quantity_precision: number;
  price_precision: number;
}

// Connection & Account
export const getCryptoStatus = () =>
  fetchJson<{ connected: boolean; configured: boolean; message: string }>('/crypto/status');

export const getCryptoAccount = () =>
  fetchJson<CryptoAccount>('/crypto/account');

export const getCryptoHoldings = () =>
  fetchJson<CryptoHolding[]>('/crypto/holdings');

// Crypto Hunter State
export const getCryptoHunterState = () =>
  fetchJson<CryptoHunterState>('/crypto/hunter/state');

export const getCryptoWatchlist = () =>
  fetchJson<CryptoWatchlistEntry[]>('/crypto/hunter/watchlist');

export const getCryptoPositions = () =>
  fetchJson<CryptoPosition[]>('/crypto/hunter/positions');

export const getCryptoTradeHistory = (limit = 50) =>
  fetchJson<CryptoTradeHistory[]>(`/crypto/hunter/history?limit=${limit}`);

export const triggerCryptoScan = () =>
  fetchJson<CryptoScanResult>('/crypto/hunter/scan', { method: 'POST' });

export const addToCryptoWatchlist = (symbol: string) =>
  fetchJson<{ success: boolean; message: string }>('/crypto/hunter/watchlist/add', {
    method: 'POST',
    body: JSON.stringify({ symbol }),
  });

export const removeFromCryptoWatchlist = (symbol: string) =>
  fetchJson<{ success: boolean; message: string }>(`/crypto/hunter/watchlist/${symbol}/remove`, {
    method: 'POST',
  });

export const closeCryptoPosition = (positionId: number) =>
  fetchJson<{ success: boolean; message: string }>(`/crypto/hunter/positions/${positionId}/close`, {
    method: 'POST',
  });

// Market Data
export const getCryptoQuotes = (symbols: string[]) =>
  fetchJson<CryptoQuote[]>('/crypto/quotes', {
    method: 'POST',
    body: JSON.stringify({ symbols }),
  });

export const getCryptoQuote = (symbol: string) =>
  fetchJson<CryptoQuote>(`/crypto/quotes/${symbol}`);

export const getTradingPairs = () =>
  fetchJson<TradingPair[]>('/crypto/pairs');

// Orders
export const getCryptoOrders = (status?: string) => {
  const params = status ? `?status=${status}` : '';
  return fetchJson<Array<{
    id: string;
    symbol: string;
    side: string;
    order_type: string;
    quantity: number;
    limit_price: number | null;
    status: string;
    filled_quantity: number;
    filled_price: number | null;
    created_at: string;
  }>>(`/crypto/orders${params}`);
};

export const cancelCryptoOrder = (orderId: string) =>
  fetchJson<{ success: boolean; message: string }>(`/crypto/orders/${orderId}`, {
    method: 'DELETE',
  });

// Crypto Agents
export const getCryptoAgents = () =>
  fetchJson<CryptoAgent[]>('/crypto/agents');

export const startCryptoAgent = (id: number) =>
  fetchJson<CryptoAgent>(`/crypto/agents/${id}/start`, { method: 'POST' });

export const stopCryptoAgent = (id: number) =>
  fetchJson<CryptoAgent>(`/crypto/agents/${id}/stop`, { method: 'POST' });

export const pauseCryptoAgent = (id: number) =>
  fetchJson<CryptoAgent>(`/crypto/agents/${id}/pause`, { method: 'POST' });

// Configuration
export interface CryptoHunterConfig {
  allocated_capital: number;
  max_positions: number;
  min_composite_score: number;
  position_size_percent: number;
  stop_loss_percent: number;
  take_profit_percent: number;
  trading_enabled: boolean;
  auto_trade: boolean;
  entry_triggers: string[];
  scan_interval_minutes: number;
  rebalance_threshold_percent: number;
  max_daily_trades: number;
  cooldown_after_loss_minutes: number;
}

export const getCryptoHunterConfig = () =>
  fetchJson<Partial<CryptoHunterConfig>>('/crypto/hunter/config');

export const updateCryptoHunterConfig = (config: Partial<CryptoHunterConfig>) =>
  fetchJson<Partial<CryptoHunterConfig>>('/crypto/hunter/config', {
    method: 'PATCH',
    body: JSON.stringify(config),
  });

export const updateCryptoAgent = (id: number, data: {
  name?: string;
  description?: string;
  is_active?: boolean;
  config?: Record<string, unknown>;
}) =>
  fetchJson<CryptoAgent>(`/crypto/agents/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data)
  });

// Scheduler Control
export interface SchedulerJob {
  id: string;
  name: string;
  next_run: string | null;
  trigger: string;
}

export interface SchedulerStatus {
  running: boolean;
  jobs: SchedulerJob[];
  active_agents: string[];
}

export const getSchedulerStatus = () =>
  fetchJson<SchedulerStatus>('/crypto/scheduler/status');

export const startCryptoScheduler = () =>
  fetchJson<{ success: boolean; message: string }>('/crypto/scheduler/start', {
    method: 'POST',
  });

export const stopCryptoScheduler = () =>
  fetchJson<{ success: boolean; message: string }>('/crypto/scheduler/stop', {
    method: 'POST',
  });
