"""
Crypto Trading Models

Database models for crypto trading, positions, watchlist, and trades.
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, Enum, Boolean, ForeignKey, JSON, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
import enum
from app.core.database import Base


class CryptoPositionStatus(str, enum.Enum):
    OPEN = "open"
    CLOSED = "closed"
    STOPPED_OUT = "stopped_out"
    TARGET_HIT = "target_hit"


class CryptoWatchlistStatus(str, enum.Enum):
    WATCHING = "watching"
    TRIGGERED = "triggered"
    ENTERED = "entered"
    EXPIRED = "expired"
    REMOVED = "removed"


class CryptoOrderStatus(str, enum.Enum):
    PENDING = "pending"
    OPEN = "open"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELED = "canceled"
    FAILED = "failed"


class CryptoPosition(Base):
    """Tracks crypto positions for the Crypto Hunter agent"""
    __tablename__ = "crypto_positions"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False)
    symbol = Column(String(20), nullable=False)  # e.g., BTC, ETH, SOL
    side = Column(String(10), nullable=False)  # "long" or "short" (short not supported on Robinhood)

    # Entry details
    entry_price = Column(Float, nullable=False)
    quantity = Column(Float, nullable=False)  # Crypto supports fractional amounts
    allocated_amount = Column(Float, nullable=False)  # $ allocated to this position

    # Current state
    current_price = Column(Float)

    # Risk management
    stop_loss = Column(Float)  # Stop loss price
    take_profit = Column(Float)  # Take profit price

    # Status and P&L
    status = Column(Enum(CryptoPositionStatus), default=CryptoPositionStatus.OPEN)
    realized_pnl = Column(Float)
    unrealized_pnl = Column(Float)
    exit_price = Column(Float)
    entry_reason = Column(Text)  # Why this position was entered
    exit_reason = Column(String(50))  # stop_loss, take_profit, manual, time_exit

    # Order tracking
    entry_order_id = Column(String(100))
    exit_order_id = Column(String(100))

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    closed_at = Column(DateTime(timezone=True))

    agent = relationship("Agent")


class CryptoWatchlist(Base):
    """Watchlist of potential crypto trades awaiting entry"""
    __tablename__ = "crypto_watchlist"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False)
    symbol = Column(String(20), nullable=False)

    # Scoring
    composite_score = Column(Float, nullable=False)  # Overall score 0-100
    trend_score = Column(Float)  # Trend analysis score
    fundamental_score = Column(Float)  # Fundamental analysis score
    momentum_score = Column(Float)  # Momentum score

    # Price levels
    entry_price = Column(Float)  # Current/entry price
    target_price = Column(Float)  # Expected target
    stop_loss = Column(Float)  # Stop loss level

    # Entry criteria
    entry_trigger = Column(String(30))  # immediate, breakout, pullback, volume_surge

    # Status
    status = Column(Enum(CryptoWatchlistStatus), default=CryptoWatchlistStatus.WATCHING)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Analysis (stored as JSON for flexibility)
    analysis_json = Column(JSON)  # Contains reasoning, entry conditions, signals, etc.

    agent = relationship("Agent")


class CryptoTrade(Base):
    """Historical record of crypto trades"""
    __tablename__ = "crypto_trades"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False)
    position_id = Column(Integer, ForeignKey("crypto_positions.id"))

    # Trade details
    symbol = Column(String(20), nullable=False)
    side = Column(String(10), nullable=False)  # "buy" or "sell"
    quantity = Column(Float, nullable=False)
    price = Column(Float, nullable=False)  # Execution price
    notional_value = Column(Float)  # quantity * price

    # Fees
    fees = Column(Float, default=0.0)

    # Order info
    order_id = Column(String(100))
    order_type = Column(String(20))  # market, limit
    status = Column(Enum(CryptoOrderStatus), default=CryptoOrderStatus.PENDING)

    # P&L (for closing trades)
    pnl = Column(Float)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    executed_at = Column(DateTime(timezone=True))

    agent = relationship("Agent")
    position = relationship("CryptoPosition")


class CryptoQuoteCache(Base):
    """Cache for crypto quotes to reduce API calls"""
    __tablename__ = "crypto_quote_cache"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(20), nullable=False, unique=True, index=True)

    # Quote data
    bid_price = Column(Float)
    ask_price = Column(Float)
    mark_price = Column(Float)
    high_price = Column(Float)
    low_price = Column(Float)
    open_price = Column(Float)
    volume = Column(Float)

    # Timestamps
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
