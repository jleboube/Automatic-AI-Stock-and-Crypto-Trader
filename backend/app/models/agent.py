from sqlalchemy import Column, Integer, String, Float, DateTime, Enum, Boolean, ForeignKey, JSON, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
import enum
from app.core.database import Base


class AgentStatus(str, enum.Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"
    STOPPED = "stopped"


class RegimeType(str, enum.Enum):
    NORMAL_BULL = "normal_bull"
    DEFENSE_TRIGGER = "defense_trigger"
    RECOVERY_MODE = "recovery_mode"
    RECOVERY_COMPLETE = "recovery_complete"


class Agent(Base):
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    agent_type = Column(String(50), nullable=False)  # short_put, short_call, long_call, long_put, risk, orchestrator
    description = Column(Text)
    status = Column(Enum(AgentStatus), default=AgentStatus.IDLE)
    is_active = Column(Boolean, default=True)
    config = Column(JSON, default={})
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_run_at = Column(DateTime(timezone=True))  # Timestamp of last agent run

    runs = relationship("AgentRun", back_populates="agent")
    trades = relationship("Trade", back_populates="agent")


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    ended_at = Column(DateTime(timezone=True))
    status = Column(Enum(AgentStatus), default=AgentStatus.RUNNING)
    result = Column(JSON)
    error_message = Column(Text)
    logs = Column(Text)

    agent = relationship("Agent", back_populates="runs")


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False)
    trade_type = Column(String(50))  # put_spread, call_spread, long_call, etc.
    symbol = Column(String(10), default="QQQ")
    short_strike = Column(Float)
    long_strike = Column(Float)
    contracts = Column(Integer)
    premium_received = Column(Float)
    premium_paid = Column(Float)
    max_risk = Column(Float)
    pnl = Column(Float)
    status = Column(String(20), default="open")  # open, closed, expired
    opened_at = Column(DateTime(timezone=True), server_default=func.now())
    closed_at = Column(DateTime(timezone=True))
    expiration = Column(DateTime(timezone=True))
    notes = Column(Text)

    agent = relationship("Agent", back_populates="trades")


class Regime(Base):
    __tablename__ = "regimes"

    id = Column(Integer, primary_key=True, index=True)
    regime_type = Column(Enum(RegimeType), nullable=False)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    ended_at = Column(DateTime(timezone=True))
    qqq_price_at_start = Column(Float)
    recovery_strike = Column(Float)
    notes = Column(Text)
    is_active = Column(Boolean, default=True)


class RecommendationStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    EXPIRED = "expired"


class TradeRecommendation(Base):
    """Stores trade recommendations for user review before execution"""
    __tablename__ = "trade_recommendations"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True))  # Recommendations expire (e.g., end of day)
    status = Column(Enum(RecommendationStatus), default=RecommendationStatus.PENDING)

    # Market context at time of recommendation
    regime_type = Column(Enum(RegimeType), nullable=False)
    qqq_price = Column(Float, nullable=False)
    vix = Column(Float)
    iv_7day_atm = Column(Float)

    # Recommended trade details
    action = Column(String(50), nullable=False)  # open_put_spread, close_put_spread, open_recovery, etc.
    trade_type = Column(String(50))  # put_spread, call_spread, long_call
    symbol = Column(String(10), default="QQQ")
    short_strike = Column(Float)
    long_strike = Column(Float)
    expiration = Column(String(20))  # YYYYMMDD format
    contracts = Column(Integer)
    estimated_credit = Column(Float)
    estimated_debit = Column(Float)
    max_risk = Column(Float)
    max_profit = Column(Float)
    short_delta = Column(Float)

    # Analysis/reasoning
    reasoning = Column(Text)  # Why this trade is recommended
    risk_assessment = Column(Text)  # Risk analysis

    # Execution tracking
    approved_at = Column(DateTime(timezone=True))
    executed_at = Column(DateTime(timezone=True))
    rejected_at = Column(DateTime(timezone=True))
    rejection_reason = Column(Text)
    order_id = Column(String(50))  # IB order ID if executed
    execution_price = Column(Float)  # Actual fill price


class GemPositionStatus(str, enum.Enum):
    OPEN = "open"
    CLOSED = "closed"
    STOPPED_OUT = "stopped_out"
    TARGET_HIT = "target_hit"
    EXPIRED = "expired"


class GemWatchlistStatus(str, enum.Enum):
    WATCHING = "watching"
    TRIGGERED = "triggered"
    ENTERED = "entered"
    EXPIRED = "expired"
    REMOVED = "removed"


class GemPosition(Base):
    """Tracks positions for the Gem Hunter agent"""
    __tablename__ = "gem_positions"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False)
    symbol = Column(String(10), nullable=False)
    position_type = Column(String(20), nullable=False)  # stock, call, put

    # Entry details
    entry_price = Column(Float, nullable=False)
    quantity = Column(Integer, nullable=False)  # Shares or contracts
    allocated_amount = Column(Float, nullable=False)  # $ allocated to this position

    # Risk management
    stop_loss = Column(Float)  # Stop loss price
    take_profit = Column(Float)  # Take profit price

    # Status and P&L
    status = Column(Enum(GemPositionStatus), default=GemPositionStatus.OPEN)
    realized_pnl = Column(Float)
    exit_price = Column(Float)
    exit_reason = Column(String(50))  # stop_loss, take_profit, manual, expired
    entry_reason = Column(Text)  # Why this position was entered

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    closed_at = Column(DateTime(timezone=True))

    agent = relationship("Agent")


class AgentActivityType(str, enum.Enum):
    """Types of agent activities"""
    STARTED = "started"
    STOPPED = "stopped"
    PAUSED = "paused"
    CYCLE_BEGIN = "cycle_begin"
    CYCLE_END = "cycle_end"
    MARKET_CLOSED = "market_closed"
    ANALYSIS = "analysis"
    TRADE_SIGNAL = "trade_signal"
    ORDER_PLACED = "order_placed"
    ORDER_FILLED = "order_filled"
    ORDER_CANCELLED = "order_cancelled"
    POSITION_OPENED = "position_opened"
    POSITION_CLOSED = "position_closed"
    STOP_TRIGGERED = "stop_triggered"
    TARGET_HIT = "target_hit"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class AgentActivity(Base):
    """Tracks agent activities for visibility into what agents are doing"""
    __tablename__ = "agent_activities"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False)
    activity_type = Column(Enum(AgentActivityType), nullable=False)
    message = Column(Text, nullable=False)
    details = Column(JSON)  # Additional structured data
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    agent = relationship("Agent")


class GemWatchlist(Base):
    """Watchlist of potential gems awaiting entry"""
    __tablename__ = "gem_watchlist"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False)
    symbol = Column(String(10), nullable=False)

    # Scoring
    composite_score = Column(Float, nullable=False)  # Overall score 0-100
    technical_score = Column(Float)  # Technical analysis score
    fundamental_score = Column(Float)  # Fundamental analysis score
    momentum_score = Column(Float)  # Momentum score

    # Price levels
    entry_price = Column(Float)  # Current/entry price
    target_price = Column(Float)  # Expected target
    stop_loss = Column(Float)  # Stop loss level

    # Entry criteria
    entry_trigger = Column(String(30))  # immediate, breakout, pullback, volume_surge

    # Status
    status = Column(Enum(GemWatchlistStatus), default=GemWatchlistStatus.WATCHING)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Analysis (stored as JSON for flexibility)
    analysis_json = Column(JSON)  # Contains reasoning, entry conditions, etc.

    agent = relationship("Agent")
