from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime
from app.models.agent import AgentStatus, RegimeType


class AgentBase(BaseModel):
    name: str
    agent_type: str
    description: Optional[str] = None
    config: Optional[Dict[str, Any]] = {}


class AgentCreate(AgentBase):
    pass


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[AgentStatus] = None
    is_active: Optional[bool] = None
    config: Optional[Dict[str, Any]] = None


class AgentResponse(AgentBase):
    id: int
    status: AgentStatus
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    last_run_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AgentRunResponse(BaseModel):
    id: int
    agent_id: int
    started_at: datetime
    ended_at: Optional[datetime] = None
    status: AgentStatus
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None

    class Config:
        from_attributes = True


class TradeCreate(BaseModel):
    agent_id: int
    trade_type: str
    symbol: str = "QQQ"
    short_strike: Optional[float] = None
    long_strike: Optional[float] = None
    contracts: int
    premium_received: Optional[float] = None
    premium_paid: Optional[float] = None
    max_risk: Optional[float] = None
    expiration: Optional[datetime] = None
    notes: Optional[str] = None


class TradeResponse(BaseModel):
    id: int
    agent_id: int
    trade_type: str
    symbol: str
    short_strike: Optional[float] = None
    long_strike: Optional[float] = None
    contracts: int
    premium_received: Optional[float] = None
    premium_paid: Optional[float] = None
    max_risk: Optional[float] = None
    pnl: Optional[float] = None
    status: str
    opened_at: datetime
    closed_at: Optional[datetime] = None
    expiration: Optional[datetime] = None

    class Config:
        from_attributes = True


class RegimeResponse(BaseModel):
    id: int
    regime_type: RegimeType
    started_at: datetime
    ended_at: Optional[datetime] = None
    qqq_price_at_start: Optional[float] = None
    recovery_strike: Optional[float] = None
    is_active: bool

    class Config:
        from_attributes = True
