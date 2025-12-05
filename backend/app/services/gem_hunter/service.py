"""
Gem Hunter Service

Main orchestrator for the Gem Hunter autonomous trading agent.
Coordinates screening, analysis, risk management, and execution.
"""

import structlog
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime, date, timedelta
from dataclasses import dataclass, asdict

from sqlalchemy.orm import Session
from sqlalchemy import and_

from .screener import GemScreener, ScreenerResult
from .analyzer import GemAnalyzer, GemAnalysis
from .risk_manager import RiskManager, RiskStatus, PositionSize
from .executor import TradeExecutor, OrderResult, OrderStatus

from app.core.market_hours import MarketHours, MarketSession
from app.services.activity_service import (
    log_cycle_start, log_cycle_end, log_market_closed,
    log_trade_signal, log_order, log_position, log_error, log_info
)
from app.models.agent import (
    Agent, AgentStatus, GemPosition, GemPositionStatus,
    GemWatchlist, GemWatchlistStatus
)

logger = structlog.get_logger()


@dataclass
class GemHunterState:
    """Current state of the Gem Hunter agent"""
    agent_id: int
    status: str
    allocated_capital: float
    deployed_capital: float
    available_capital: float
    daily_pnl: float
    total_pnl: float
    open_positions: int
    max_positions: int
    watchlist_count: int
    last_scan: Optional[datetime]
    last_trade: Optional[datetime]
    is_trading_enabled: bool
    risk_status: Optional[RiskStatus]


class GemHunterService:
    """
    Autonomous trading agent that scans for undervalued stocks
    with breakout potential and executes trades based on analysis.

    Workflow:
    1. Screen market for candidates (oversold, breakout, value, momentum)
    2. Analyze candidates with composite scoring
    3. Add top candidates to watchlist
    4. Execute trades for qualifying opportunities
    5. Manage open positions (stop-loss, take-profit)
    6. Track performance and update Kelly parameters
    """

    def __init__(
        self,
        agent_id: int,
        db: Session,
        ib_client,
        config: Dict[str, Any]
    ):
        """
        Initialize the Gem Hunter service.

        Args:
            agent_id: Database ID of this agent
            db: SQLAlchemy database session
            ib_client: Interactive Brokers client
            config: Agent configuration
        """
        self.agent_id = agent_id
        self.db = db
        self.ib_client = ib_client
        self.config = config

        # Initialize components
        self.screener = GemScreener(config)
        self.analyzer = GemAnalyzer(config)
        self.risk_manager = RiskManager(config)
        self.executor = TradeExecutor(ib_client, config)

        # Configuration
        self.min_score = config.get("min_composite_score", 65)
        self.max_watchlist = config.get("max_watchlist", 20)
        self.auto_trade = config.get("auto_trade", True)
        self.scan_interval_minutes = config.get("scan_interval_minutes", 60)

        # State tracking
        self._daily_pnl: Dict[date, float] = {}
        self._last_scan: Optional[datetime] = None

    async def run_cycle(self) -> Dict[str, Any]:
        """
        Run a complete trading cycle.

        Returns summary of actions taken.
        """
        logger.info("Starting Gem Hunter cycle", agent_id=self.agent_id)

        summary = {
            "timestamp": datetime.now().isoformat(),
            "screened": 0,
            "analyzed": 0,
            "added_to_watchlist": 0,
            "trades_executed": 0,
            "positions_closed": 0,
            "market_status": None,
            "errors": []
        }

        try:
            # 0. Check market hours first
            market_status = MarketHours.get_status()
            summary["market_status"] = market_status

            # Skip trading during closed hours
            if not market_status["can_trade_stocks"]:
                session = market_status["session"]
                logger.info(
                    "Market closed, skipping trading cycle",
                    session=session,
                    time_until_open=market_status.get("time_until_open")
                )
                log_market_closed(
                    self.db, self.agent_id, session,
                    market_status.get("time_until_open")
                )
                summary["errors"].append(f"Market closed (session: {session})")
                return summary

            # Log cycle start
            log_cycle_start(self.db, self.agent_id, {
                "session": market_status["session"],
                "time_until_close": market_status.get("time_until_close")
            })

            logger.info(
                "Market open for trading",
                session=market_status["session"],
                time_until_close=market_status.get("time_until_close")
            )

            # 1. Check risk status first
            risk_status = await self._get_risk_status()

            if risk_status.is_daily_limit_hit:
                logger.warning("Daily loss limit hit, skipping cycle")
                summary["errors"].append("Daily loss limit reached")
                return summary

            # 2. Manage existing positions (check stops/targets)
            closed = await self._manage_positions()
            summary["positions_closed"] = closed

            # 3. Screen market for new candidates
            candidates = await self._screen_market()
            summary["screened"] = len(candidates)

            # 4. Analyze candidates
            analyses = await self._analyze_candidates(candidates)
            summary["analyzed"] = len(analyses)

            # 5. Update watchlist
            added = await self._update_watchlist(analyses)
            summary["added_to_watchlist"] = added

            # 6. Execute trades for qualifying opportunities
            if self.auto_trade and risk_status.can_open_new:
                trades = await self._execute_trades(risk_status)
                summary["trades_executed"] = trades

            # Update last scan time
            self._last_scan = datetime.now()
            await self._update_agent_last_run()

            # Log cycle completion
            log_cycle_end(self.db, self.agent_id, {
                "screened": summary["screened"],
                "analyzed": summary["analyzed"],
                "added_to_watchlist": summary["added_to_watchlist"],
                "trades_executed": summary["trades_executed"],
                "positions_closed": summary["positions_closed"]
            })

            logger.info("Gem Hunter cycle complete", **summary)

        except Exception as e:
            logger.error("Gem Hunter cycle error", error=str(e))
            log_error(self.db, self.agent_id, str(e))
            summary["errors"].append(str(e))

        return summary

    async def _get_risk_status(self) -> RiskStatus:
        """Get current risk status from database positions"""
        # Get open positions
        positions = self.db.query(GemPosition).filter(
            and_(
                GemPosition.agent_id == self.agent_id,
                GemPosition.status == GemPositionStatus.OPEN
            )
        ).all()

        # Calculate deployed capital and daily P&L
        deployed_capital = sum(p.allocated_amount for p in positions)
        daily_pnl = self._get_daily_pnl()

        return self.risk_manager.get_risk_status(
            deployed_capital=deployed_capital,
            open_positions=len(positions),
            daily_pnl=daily_pnl
        )

    def _get_daily_pnl(self) -> float:
        """Get today's realized + unrealized P&L"""
        today = date.today()
        return self._daily_pnl.get(today, 0)

    async def _screen_market(self) -> List[ScreenerResult]:
        """Screen market for gem candidates"""
        logger.info("Screening market for gems")

        # Run all screening strategies
        all_results = self.screener.screen_market()

        # Combine different screening strategies
        oversold = self.screener.find_oversold_gems(all_results)
        breakouts = self.screener.find_breakout_candidates(all_results)
        value = self.screener.find_value_plays(all_results)
        momentum = self.screener.find_momentum_plays(all_results)

        # Combine and deduplicate
        seen = set()
        combined = []

        for result in oversold + breakouts + value + momentum:
            if result.symbol not in seen:
                seen.add(result.symbol)
                combined.append(result)

        logger.info(
            "Market screening complete",
            total=len(all_results),
            oversold=len(oversold),
            breakouts=len(breakouts),
            value=len(value),
            momentum=len(momentum),
            unique_candidates=len(combined)
        )

        return combined

    async def _analyze_candidates(
        self,
        candidates: List[ScreenerResult]
    ) -> List[GemAnalysis]:
        """Analyze screened candidates"""
        analyses = self.analyzer.analyze_batch(candidates, min_score=self.min_score)

        logger.info(
            "Analysis complete",
            candidates=len(candidates),
            passed=len(analyses),
            min_score=self.min_score
        )

        return analyses

    async def _update_watchlist(self, analyses: List[GemAnalysis]) -> int:
        """Update the watchlist with new candidates"""
        added = 0

        for analysis in analyses[:self.max_watchlist]:
            # Check if already in watchlist
            existing = self.db.query(GemWatchlist).filter(
                and_(
                    GemWatchlist.agent_id == self.agent_id,
                    GemWatchlist.symbol == analysis.symbol,
                    GemWatchlist.status == GemWatchlistStatus.WATCHING
                )
            ).first()

            if existing:
                # Update existing entry
                existing.composite_score = analysis.composite_score
                existing.technical_score = analysis.technical_score
                existing.fundamental_score = analysis.fundamental_score
                existing.momentum_score = analysis.momentum_score
                existing.entry_price = analysis.entry_price
                existing.target_price = analysis.target_price
                existing.stop_loss = analysis.stop_loss
                existing.entry_trigger = analysis.entry_trigger
                existing.analysis_json = {"reasoning": analysis.reasoning}
                existing.updated_at = datetime.utcnow()
            else:
                # Add new entry
                watchlist_entry = GemWatchlist(
                    agent_id=self.agent_id,
                    symbol=analysis.symbol,
                    composite_score=analysis.composite_score,
                    technical_score=analysis.technical_score,
                    fundamental_score=analysis.fundamental_score,
                    momentum_score=analysis.momentum_score,
                    entry_price=analysis.entry_price,
                    target_price=analysis.target_price,
                    stop_loss=analysis.stop_loss,
                    entry_trigger=analysis.entry_trigger,
                    analysis_json={"reasoning": analysis.reasoning},
                    status=GemWatchlistStatus.WATCHING
                )
                self.db.add(watchlist_entry)
                added += 1

        self.db.commit()

        # Expire old watchlist entries
        await self._expire_old_watchlist_entries()

        logger.info("Watchlist updated", added=added)
        return added

    async def _expire_old_watchlist_entries(self, days: int = 7):
        """Remove watchlist entries older than specified days"""
        cutoff = datetime.utcnow() - timedelta(days=days)

        old_entries = self.db.query(GemWatchlist).filter(
            and_(
                GemWatchlist.agent_id == self.agent_id,
                GemWatchlist.status == GemWatchlistStatus.WATCHING,
                GemWatchlist.created_at < cutoff
            )
        ).all()

        for entry in old_entries:
            entry.status = GemWatchlistStatus.EXPIRED
            entry.updated_at = datetime.utcnow()

        if old_entries:
            self.db.commit()
            logger.info("Expired old watchlist entries", count=len(old_entries))

    async def _execute_trades(self, risk_status: RiskStatus) -> int:
        """Execute trades for qualifying watchlist entries"""
        executed = 0

        # Get top watchlist entries
        watchlist = self.db.query(GemWatchlist).filter(
            and_(
                GemWatchlist.agent_id == self.agent_id,
                GemWatchlist.status == GemWatchlistStatus.WATCHING
            )
        ).order_by(GemWatchlist.composite_score.desc()).limit(5).all()

        for entry in watchlist:
            if not risk_status.can_open_new:
                break

            # Check if entry trigger conditions are met
            if entry.entry_trigger == "immediate" or await self._check_entry_conditions(entry):
                # Calculate position size
                position_size = self.risk_manager.calculate_position_size(
                    symbol=entry.symbol,
                    entry_price=entry.entry_price,
                    deployed_capital=risk_status.deployed_capital,
                    open_positions=risk_status.open_positions
                )

                if position_size.shares > 0:
                    # Create analysis object for executor
                    analysis = GemAnalysis(
                        symbol=entry.symbol,
                        current_price=entry.entry_price,
                        technical_score=entry.technical_score or 0,
                        fundamental_score=entry.fundamental_score or 0,
                        momentum_score=entry.momentum_score or 0,
                        composite_score=entry.composite_score,
                        entry_price=entry.entry_price,
                        target_price=entry.target_price,
                        stop_loss=entry.stop_loss,
                        upside_potential=0,
                        downside_risk=0,
                        risk_reward_ratio=0,
                        entry_trigger=entry.entry_trigger,
                        entry_conditions={},
                        reasoning="",
                        raw_data=None
                    )

                    # Execute the trade
                    result = await self.executor.execute_entry(analysis, position_size)

                    if result.status == OrderStatus.FILLED:
                        # Create position record
                        await self._create_position(entry, result, position_size)

                        # Update watchlist status
                        entry.status = GemWatchlistStatus.ENTERED
                        entry.updated_at = datetime.utcnow()

                        executed += 1

                        # Update risk status
                        risk_status = await self._get_risk_status()

                        logger.info(
                            "Trade executed",
                            symbol=entry.symbol,
                            shares=result.filled_quantity,
                            price=result.filled_price
                        )

        if executed > 0:
            self.db.commit()

        return executed

    async def _check_entry_conditions(self, entry: GemWatchlist) -> bool:
        """Check if entry conditions are met for a watchlist entry"""
        # For now, allow immediate entry for high-scoring candidates
        if entry.composite_score >= 75:
            return True

        # Could add more sophisticated entry logic here:
        # - Check if breakout level is breached
        # - Check if pullback has occurred
        # - etc.

        return False

    async def _create_position(
        self,
        entry: GemWatchlist,
        result: OrderResult,
        position_size: PositionSize
    ):
        """Create a position record from a filled order"""
        position = GemPosition(
            agent_id=self.agent_id,
            symbol=entry.symbol,
            position_type="stock",
            entry_price=result.filled_price,
            quantity=result.filled_quantity,
            allocated_amount=result.filled_price * result.filled_quantity,
            stop_loss=entry.stop_loss,
            take_profit=entry.target_price,
            status=GemPositionStatus.OPEN,
            entry_reason=f"Composite score: {entry.composite_score:.0f}",
            created_at=datetime.utcnow()
        )
        self.db.add(position)

    async def _manage_positions(self) -> int:
        """Check and manage open positions"""
        closed = 0

        positions = self.db.query(GemPosition).filter(
            and_(
                GemPosition.agent_id == self.agent_id,
                GemPosition.status == GemPositionStatus.OPEN
            )
        ).all()

        for position in positions:
            try:
                # Get current price from IB
                current_price = await self._get_current_price(position.symbol)

                if current_price is None:
                    continue

                # Calculate days held
                days_held = (datetime.utcnow() - position.created_at).days

                # Check exit conditions
                should_exit, reason = self.risk_manager.should_exit(
                    current_price=current_price,
                    entry_price=position.entry_price,
                    stop_loss=position.stop_loss,
                    take_profit=position.take_profit,
                    days_held=days_held,
                    max_hold_days=self.config.get("max_hold_days", 30)
                )

                if should_exit:
                    # Execute exit
                    result = await self.executor.execute_exit(
                        symbol=position.symbol,
                        quantity=position.quantity,
                        reason=reason
                    )

                    if result.status == OrderStatus.FILLED:
                        # Update position
                        position.exit_price = result.filled_price
                        position.exit_reason = reason
                        position.closed_at = datetime.utcnow()

                        # Calculate P&L
                        pnl = (result.filled_price - position.entry_price) * position.quantity
                        position.realized_pnl = pnl

                        # Set status based on reason
                        if reason == "stop_loss":
                            position.status = GemPositionStatus.STOPPED_OUT
                        elif reason == "take_profit":
                            position.status = GemPositionStatus.TARGET_HIT
                        else:
                            position.status = GemPositionStatus.CLOSED

                        # Record trade for Kelly updates
                        self.risk_manager.record_trade(
                            symbol=position.symbol,
                            entry_price=position.entry_price,
                            exit_price=result.filled_price,
                            pnl=pnl
                        )

                        # Update daily P&L
                        today = date.today()
                        self._daily_pnl[today] = self._daily_pnl.get(today, 0) + pnl

                        closed += 1

                        logger.info(
                            "Position closed",
                            symbol=position.symbol,
                            reason=reason,
                            pnl=pnl
                        )

            except Exception as e:
                logger.error(
                    "Error managing position",
                    symbol=position.symbol,
                    error=str(e)
                )

        if closed > 0:
            self.db.commit()

        return closed

    async def _get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price for a symbol"""
        try:
            # Try to get from IB
            if self.ib_client and self.ib_client.is_connected():
                return await self.ib_client.get_stock_price(symbol)

            # Fallback to Yahoo Finance
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="1d")
            if not hist.empty:
                return hist['Close'].iloc[-1]

            return None
        except Exception as e:
            logger.warning("Failed to get current price", symbol=symbol, error=str(e))
            return None

    async def _update_agent_last_run(self):
        """Update the agent's last run timestamp"""
        agent = self.db.query(Agent).filter(Agent.id == self.agent_id).first()
        if agent:
            agent.last_run_at = datetime.utcnow()
            self.db.commit()

    async def get_state(self) -> GemHunterState:
        """Get current state of the Gem Hunter agent"""
        risk_status = await self._get_risk_status()

        # Get agent from DB
        agent = self.db.query(Agent).filter(Agent.id == self.agent_id).first()

        # Count watchlist entries
        watchlist_count = self.db.query(GemWatchlist).filter(
            and_(
                GemWatchlist.agent_id == self.agent_id,
                GemWatchlist.status == GemWatchlistStatus.WATCHING
            )
        ).count()

        # Calculate total P&L
        total_pnl = sum(self._daily_pnl.values())

        # Get last trade time
        last_position = self.db.query(GemPosition).filter(
            GemPosition.agent_id == self.agent_id
        ).order_by(GemPosition.created_at.desc()).first()

        return GemHunterState(
            agent_id=self.agent_id,
            status=agent.status if agent else "unknown",
            allocated_capital=self.risk_manager.allocated_capital,
            deployed_capital=risk_status.deployed_capital,
            available_capital=risk_status.available_capital,
            daily_pnl=risk_status.daily_pnl,
            total_pnl=total_pnl,
            open_positions=risk_status.open_positions,
            max_positions=risk_status.max_positions,
            watchlist_count=watchlist_count,
            last_scan=self._last_scan,
            last_trade=last_position.created_at if last_position else None,
            is_trading_enabled=self.auto_trade and not risk_status.is_daily_limit_hit,
            risk_status=risk_status
        )

    async def get_watchlist(self) -> List[Dict[str, Any]]:
        """Get current watchlist entries"""
        entries = self.db.query(GemWatchlist).filter(
            and_(
                GemWatchlist.agent_id == self.agent_id,
                GemWatchlist.status == GemWatchlistStatus.WATCHING
            )
        ).order_by(GemWatchlist.composite_score.desc()).all()

        return [
            {
                "id": e.id,
                "symbol": e.symbol,
                "composite_score": e.composite_score,
                "technical_score": e.technical_score,
                "fundamental_score": e.fundamental_score,
                "momentum_score": e.momentum_score,
                "entry_price": e.entry_price,
                "target_price": e.target_price,
                "stop_loss": e.stop_loss,
                "entry_trigger": e.entry_trigger,
                "created_at": e.created_at.isoformat() if e.created_at else None
            }
            for e in entries
        ]

    async def get_positions(self) -> List[Dict[str, Any]]:
        """Get current open positions"""
        positions = self.db.query(GemPosition).filter(
            and_(
                GemPosition.agent_id == self.agent_id,
                GemPosition.status == GemPositionStatus.OPEN
            )
        ).all()

        result = []
        for p in positions:
            current_price = await self._get_current_price(p.symbol)
            unrealized_pnl = None
            if current_price:
                unrealized_pnl = (current_price - p.entry_price) * p.quantity

            result.append({
                "id": p.id,
                "symbol": p.symbol,
                "position_type": p.position_type,
                "quantity": p.quantity,
                "entry_price": p.entry_price,
                "current_price": current_price,
                "stop_loss": p.stop_loss,
                "take_profit": p.take_profit,
                "unrealized_pnl": unrealized_pnl,
                "allocated_amount": p.allocated_amount,
                "created_at": p.created_at.isoformat() if p.created_at else None
            })

        return result

    async def get_trade_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent trade history"""
        positions = self.db.query(GemPosition).filter(
            and_(
                GemPosition.agent_id == self.agent_id,
                GemPosition.status != GemPositionStatus.OPEN
            )
        ).order_by(GemPosition.closed_at.desc()).limit(limit).all()

        return [
            {
                "id": p.id,
                "symbol": p.symbol,
                "position_type": p.position_type,
                "quantity": p.quantity,
                "entry_price": p.entry_price,
                "exit_price": p.exit_price,
                "realized_pnl": p.realized_pnl,
                "status": p.status,
                "entry_reason": p.entry_reason,
                "exit_reason": p.exit_reason,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "closed_at": p.closed_at.isoformat() if p.closed_at else None
            }
            for p in positions
        ]

    async def manual_scan(self) -> Dict[str, Any]:
        """Trigger a manual market scan"""
        return await self.run_cycle()

    async def add_to_watchlist(self, symbol: str) -> Dict[str, Any]:
        """Manually add a symbol to the watchlist"""
        # Screen the symbol
        results = self.screener.screen_market()
        result = next((r for r in results if r.symbol == symbol), None)

        if not result:
            # Try to fetch just this symbol
            result = self.screener._get_stock_data(symbol)

        if not result:
            return {"success": False, "message": f"Could not get data for {symbol}"}

        # Analyze
        analysis = self.analyzer.analyze(result)

        # Add to watchlist
        entry = GemWatchlist(
            agent_id=self.agent_id,
            symbol=analysis.symbol,
            composite_score=analysis.composite_score,
            technical_score=analysis.technical_score,
            fundamental_score=analysis.fundamental_score,
            momentum_score=analysis.momentum_score,
            entry_price=analysis.entry_price,
            target_price=analysis.target_price,
            stop_loss=analysis.stop_loss,
            entry_trigger=analysis.entry_trigger,
            analysis_json={"reasoning": analysis.reasoning},
            status=GemWatchlistStatus.WATCHING
        )
        self.db.add(entry)
        self.db.commit()

        return {
            "success": True,
            "message": f"Added {symbol} to watchlist",
            "analysis": {
                "symbol": analysis.symbol,
                "composite_score": analysis.composite_score,
                "entry_price": analysis.entry_price,
                "target_price": analysis.target_price,
                "stop_loss": analysis.stop_loss
            }
        }

    async def remove_from_watchlist(self, symbol: str) -> Dict[str, Any]:
        """Remove a symbol from the watchlist"""
        entry = self.db.query(GemWatchlist).filter(
            and_(
                GemWatchlist.agent_id == self.agent_id,
                GemWatchlist.symbol == symbol,
                GemWatchlist.status == GemWatchlistStatus.WATCHING
            )
        ).first()

        if entry:
            entry.status = GemWatchlistStatus.REMOVED
            entry.updated_at = datetime.utcnow()
            self.db.commit()
            return {"success": True, "message": f"Removed {symbol} from watchlist"}

        return {"success": False, "message": f"{symbol} not found in watchlist"}

    async def close_position(self, position_id: int) -> Dict[str, Any]:
        """Manually close a position"""
        position = self.db.query(GemPosition).filter(
            and_(
                GemPosition.id == position_id,
                GemPosition.agent_id == self.agent_id,
                GemPosition.status == GemPositionStatus.OPEN
            )
        ).first()

        if not position:
            return {"success": False, "message": "Position not found"}

        result = await self.executor.execute_exit(
            symbol=position.symbol,
            quantity=position.quantity,
            reason="manual"
        )

        if result.status == OrderStatus.FILLED:
            position.exit_price = result.filled_price
            position.exit_reason = "manual"
            position.closed_at = datetime.utcnow()
            position.realized_pnl = (result.filled_price - position.entry_price) * position.quantity
            position.status = GemPositionStatus.CLOSED
            self.db.commit()

            return {
                "success": True,
                "message": f"Closed position in {position.symbol}",
                "pnl": position.realized_pnl
            }

        return {"success": False, "message": f"Failed to close: {result.message}"}
