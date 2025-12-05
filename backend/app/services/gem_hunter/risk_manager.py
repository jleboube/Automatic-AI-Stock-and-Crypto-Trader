"""
Risk Manager for Gem Hunter

Implements Kelly Criterion position sizing and capital management.
"""

import structlog
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime, date

logger = structlog.get_logger()


@dataclass
class PositionSize:
    """Calculated position size"""
    symbol: str
    shares: int
    dollar_amount: float
    position_pct: float  # % of allocated capital
    kelly_fraction: float
    reasoning: str


@dataclass
class RiskStatus:
    """Current risk status for the agent"""
    allocated_capital: float
    deployed_capital: float
    available_capital: float
    deployed_pct: float
    daily_pnl: float
    daily_pnl_pct: float
    is_daily_limit_hit: bool
    open_positions: int
    max_positions: int
    can_open_new: bool


class RiskManager:
    """
    Manages risk and position sizing for the Gem Hunter agent.

    Key responsibilities:
    - Kelly Criterion position sizing
    - Capital allocation tracking
    - Daily loss limit enforcement
    - Position count limits
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize risk manager with configuration.

        Config options:
        - allocated_capital: Total capital for this agent
        - max_positions: Maximum concurrent positions
        - max_position_pct: Maximum % of capital in single position
        - kelly_multiplier: Fraction of Kelly to use (e.g., 0.5 for half-Kelly)
        - daily_loss_limit_pct: Daily loss limit as % of capital
        - stop_loss_pct: Default stop loss %
        - take_profit_pct: Default take profit %
        """
        self.config = config
        self.allocated_capital = config.get("allocated_capital", 10000)
        self.max_positions = config.get("max_positions", 5)
        self.max_position_pct = config.get("max_position_pct", 0.25)
        self.kelly_multiplier = config.get("kelly_multiplier", 0.5)
        self.daily_loss_limit_pct = config.get("daily_loss_limit_pct", 0.05)
        self.stop_loss_pct = config.get("stop_loss_pct", 0.08)
        self.take_profit_pct = config.get("take_profit_pct", 0.20)

        # Track performance for Kelly calculations
        self._trade_history: List[Dict] = []
        self._daily_pnl: Dict[date, float] = {}

    def kelly_fraction(
        self,
        win_rate: float = None,
        avg_win: float = None,
        avg_loss: float = None
    ) -> float:
        """
        Calculate the Kelly Criterion fraction.

        Kelly formula: f* = (bp - q) / b
        where:
        - b = odds received on the bet (avg_win / avg_loss)
        - p = probability of winning (win_rate)
        - q = probability of losing (1 - win_rate)

        Returns the Kelly fraction (0 to 1), capped at max_position_pct.
        """
        # Use historical data if not provided
        if win_rate is None or avg_win is None or avg_loss is None:
            stats = self._calculate_historical_stats()
            win_rate = stats.get("win_rate", 0.5)
            avg_win = stats.get("avg_win", self.take_profit_pct)
            avg_loss = stats.get("avg_loss", self.stop_loss_pct)

        # Prevent division by zero
        if avg_loss <= 0:
            avg_loss = self.stop_loss_pct

        # Calculate Kelly
        b = avg_win / avg_loss
        p = win_rate
        q = 1 - p

        kelly = (b * p - q) / b

        # Apply Kelly multiplier (e.g., half-Kelly for more conservative sizing)
        kelly *= self.kelly_multiplier

        # Ensure reasonable bounds
        kelly = max(0, min(kelly, self.max_position_pct))

        logger.debug(
            "Kelly calculation",
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            raw_kelly=kelly / self.kelly_multiplier,
            adjusted_kelly=kelly
        )

        return kelly

    def _calculate_historical_stats(self) -> Dict[str, float]:
        """Calculate win rate and average win/loss from trade history"""
        if not self._trade_history:
            # Default to conservative estimates
            return {
                "win_rate": 0.50,
                "avg_win": self.take_profit_pct,
                "avg_loss": self.stop_loss_pct,
                "total_trades": 0
            }

        wins = [t for t in self._trade_history if t.get("pnl", 0) > 0]
        losses = [t for t in self._trade_history if t.get("pnl", 0) <= 0]

        win_rate = len(wins) / len(self._trade_history) if self._trade_history else 0.5

        avg_win = (
            sum(t["pnl_pct"] for t in wins) / len(wins)
            if wins else self.take_profit_pct
        )

        avg_loss = (
            abs(sum(t["pnl_pct"] for t in losses) / len(losses))
            if losses else self.stop_loss_pct
        )

        return {
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "total_trades": len(self._trade_history)
        }

    def record_trade(
        self,
        symbol: str,
        entry_price: float,
        exit_price: float,
        pnl: float,
        trade_date: date = None
    ):
        """Record a completed trade for Kelly calculation updates"""
        if trade_date is None:
            trade_date = date.today()

        pnl_pct = (exit_price - entry_price) / entry_price if entry_price > 0 else 0

        self._trade_history.append({
            "symbol": symbol,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "pnl": pnl,
            "pnl_pct": pnl_pct,
            "date": trade_date
        })

        # Update daily P&L
        if trade_date not in self._daily_pnl:
            self._daily_pnl[trade_date] = 0
        self._daily_pnl[trade_date] += pnl

        logger.info("Trade recorded", symbol=symbol, pnl=pnl, pnl_pct=pnl_pct)

    def calculate_position_size(
        self,
        symbol: str,
        entry_price: float,
        deployed_capital: float = 0,
        open_positions: int = 0
    ) -> PositionSize:
        """
        Calculate the optimal position size for a trade.

        Args:
            symbol: Stock symbol
            entry_price: Expected entry price
            deployed_capital: Currently deployed capital
            open_positions: Number of open positions

        Returns:
            PositionSize with shares and dollar amount
        """
        available = self.allocated_capital - deployed_capital

        # Check if we can open a new position
        if open_positions >= self.max_positions:
            return PositionSize(
                symbol=symbol,
                shares=0,
                dollar_amount=0,
                position_pct=0,
                kelly_fraction=0,
                reasoning="Maximum positions reached"
            )

        if available <= 0:
            return PositionSize(
                symbol=symbol,
                shares=0,
                dollar_amount=0,
                position_pct=0,
                kelly_fraction=0,
                reasoning="No available capital"
            )

        # Calculate Kelly fraction
        kelly = self.kelly_fraction()

        # Position size based on Kelly
        kelly_amount = self.allocated_capital * kelly

        # Cap at max position size
        max_amount = self.allocated_capital * self.max_position_pct
        position_amount = min(kelly_amount, max_amount, available)

        # Calculate shares (round down)
        shares = int(position_amount / entry_price)
        actual_amount = shares * entry_price

        # Calculate actual position percentage
        position_pct = actual_amount / self.allocated_capital if self.allocated_capital > 0 else 0

        reasoning = (
            f"Kelly: {kelly:.1%} → ${kelly_amount:.0f}, "
            f"Max: {self.max_position_pct:.0%} → ${max_amount:.0f}, "
            f"Available: ${available:.0f} → Final: ${actual_amount:.0f} ({shares} shares)"
        )

        return PositionSize(
            symbol=symbol,
            shares=shares,
            dollar_amount=actual_amount,
            position_pct=position_pct,
            kelly_fraction=kelly,
            reasoning=reasoning
        )

    def check_daily_limit(self, current_daily_pnl: float) -> bool:
        """
        Check if daily loss limit has been hit.

        Returns True if limit is hit (trading should stop).
        """
        daily_limit = self.allocated_capital * self.daily_loss_limit_pct
        limit_hit = current_daily_pnl <= -daily_limit

        if limit_hit:
            logger.warning(
                "Daily loss limit hit!",
                daily_pnl=current_daily_pnl,
                limit=-daily_limit
            )

        return limit_hit

    def get_risk_status(
        self,
        deployed_capital: float,
        open_positions: int,
        daily_pnl: float
    ) -> RiskStatus:
        """Get current risk status for the agent"""
        available = self.allocated_capital - deployed_capital
        deployed_pct = deployed_capital / self.allocated_capital if self.allocated_capital > 0 else 0
        daily_pnl_pct = daily_pnl / self.allocated_capital if self.allocated_capital > 0 else 0

        is_limit_hit = self.check_daily_limit(daily_pnl)
        can_open = (
            open_positions < self.max_positions and
            available > 0 and
            not is_limit_hit
        )

        return RiskStatus(
            allocated_capital=self.allocated_capital,
            deployed_capital=deployed_capital,
            available_capital=available,
            deployed_pct=deployed_pct,
            daily_pnl=daily_pnl,
            daily_pnl_pct=daily_pnl_pct,
            is_daily_limit_hit=is_limit_hit,
            open_positions=open_positions,
            max_positions=self.max_positions,
            can_open_new=can_open
        )

    def calculate_stop_loss(self, entry_price: float, atr: float = None) -> float:
        """
        Calculate stop loss price.

        If ATR provided, uses ATR-based stop. Otherwise uses fixed percentage.
        """
        if atr:
            # 2x ATR stop
            return entry_price - (2 * atr)
        else:
            return entry_price * (1 - self.stop_loss_pct)

    def calculate_take_profit(self, entry_price: float, stop_loss: float = None) -> float:
        """
        Calculate take profit price.

        Uses risk/reward ratio of at least 2:1 if stop is provided.
        """
        if stop_loss:
            risk = entry_price - stop_loss
            # 2.5:1 reward to risk
            return entry_price + (risk * 2.5)
        else:
            return entry_price * (1 + self.take_profit_pct)

    def should_exit(
        self,
        current_price: float,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        days_held: int = 0,
        max_hold_days: int = 30
    ) -> tuple:
        """
        Determine if a position should be exited.

        Returns (should_exit: bool, reason: str)
        """
        if current_price <= stop_loss:
            return True, "stop_loss"

        if current_price >= take_profit:
            return True, "take_profit"

        if days_held >= max_hold_days:
            return True, "max_hold_days"

        return False, None
