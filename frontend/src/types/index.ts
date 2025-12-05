export type AgentStatus = 'idle' | 'running' | 'paused' | 'error' | 'stopped';

export type RegimeType = 'normal_bull' | 'defense_trigger' | 'recovery_mode' | 'recovery_complete';

export interface Agent {
  id: number;
  name: string;
  agent_type: string;
  description: string | null;
  status: AgentStatus;
  is_active: boolean;
  config: Record<string, unknown>;
  created_at: string;
  updated_at: string | null;
  last_run_at: string | null;
}

export interface AgentRun {
  id: number;
  agent_id: number;
  started_at: string;
  ended_at: string | null;
  status: AgentStatus;
  result: Record<string, unknown> | null;
  error_message: string | null;
}

export interface Trade {
  id: number;
  agent_id: number;
  trade_type: string;
  symbol: string;
  short_strike: number | null;
  long_strike: number | null;
  contracts: number;
  premium_received: number | null;
  premium_paid: number | null;
  max_risk: number | null;
  pnl: number | null;
  status: string;
  opened_at: string;
  closed_at: string | null;
  expiration: string | null;
}

export interface Regime {
  id: number;
  regime_type: RegimeType;
  started_at: string;
  ended_at: string | null;
  qqq_price_at_start: number | null;
  recovery_strike: number | null;
  is_active: boolean;
}

export interface AgentStatusSummary {
  agent_id: number;
  agent_name: string;
  agent_type: string;
  status: string;
  total_runs: number;
  successful_runs: number;
  failed_runs: number;
  total_trades: number;
  open_trades: number;
  total_pnl: number;
}

export interface TradeSummary {
  total_trades: number;
  open_trades: number;
  closed_trades: number;
  total_pnl: number;
  win_rate: number;
  avg_premium: number;
}

export interface DashboardData {
  current_regime: RegimeType | null;
  regime_started_at: string | null;
  qqq_price: number | null;
  vix: number | null;
  account_value: number | null;
  buying_power: number | null;
  deployed_capital_pct: number | null;
  month_pnl: number | null;
  ytd_pnl: number | null;
  drawdown_pct: number | null;
  agents: AgentStatusSummary[];
  trade_summary: TradeSummary | null;
  recent_trades: Trade[];
  recent_alerts: Alert[];
}

export interface Alert {
  type: string;
  level: string;
  message: string;
  timestamp: string;
}

export interface PnLChartData {
  date: string;
  pnl: number;
  cumulative_pnl: number;
}

export interface WebSocketMessage {
  type: 'agent_update' | 'trade_update' | 'regime_change' | 'alert' | 'pong';
  agent_id?: number;
  trade_id?: number;
  status?: string;
  action?: string;
  old_regime?: string;
  new_regime?: string;
  level?: string;
  message?: string;
  data?: Record<string, unknown>;
}
