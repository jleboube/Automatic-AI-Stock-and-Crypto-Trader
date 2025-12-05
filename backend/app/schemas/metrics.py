from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime


class MetricResponse(BaseModel):
    metric_name: str
    metric_value: float
    recorded_at: datetime
    agent_id: Optional[int] = None

    class Config:
        from_attributes = True


class AgentStatusSummary(BaseModel):
    agent_id: int
    agent_name: str
    agent_type: str
    status: str
    total_runs: int
    successful_runs: int
    failed_runs: int
    total_trades: int
    open_trades: int
    total_pnl: float


class TradeSummary(BaseModel):
    total_trades: int
    open_trades: int
    closed_trades: int
    total_pnl: float
    win_rate: float
    avg_premium: float


class DashboardResponse(BaseModel):
    current_regime: Optional[str] = None
    regime_started_at: Optional[datetime] = None
    qqq_price: Optional[float] = None
    vix: Optional[float] = None
    account_value: Optional[float] = None
    buying_power: Optional[float] = None
    deployed_capital_pct: Optional[float] = None
    month_pnl: Optional[float] = None
    ytd_pnl: Optional[float] = None
    drawdown_pct: Optional[float] = None
    agents: List[AgentStatusSummary] = []
    trade_summary: Optional[TradeSummary] = None
    recent_trades: List[Dict[str, Any]] = []
    recent_alerts: List[Dict[str, Any]] = []
