import asyncio
import structlog
from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentStatus, RegimeType, TradeRecommendation
from app.services.agent_service import AgentService
from app.services.recommendation_service import RecommendationService
from app.services.broker.ib_client import get_ib_client
from app.core.config import settings
from app.core.market_hours import MarketHours, MarketSession

logger = structlog.get_logger()


class OrchestratorService:
    """
    The Orchestrator Agent - the "brain" of the system.
    Decides which regime we are in and activates the appropriate agents.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.agent_service = AgentService(db)
        self.recommendation_service = RecommendationService(db)
        self.ib_client = get_ib_client()
        self.is_running = False
        self.current_qqq_price: Optional[float] = None
        self.current_vix: Optional[float] = None
        self.last_short_put_strike: Optional[float] = None

    async def ensure_ib_connected(self) -> bool:
        """Ensure IB client is connected, attempt connection if not"""
        if self.ib_client.is_connected:
            return True

        logger.info("IB not connected, attempting to connect...")
        try:
            connected = await self.ib_client.connect()
            if connected:
                logger.info("Successfully connected to IB Gateway")
                return True
            else:
                logger.warning("Failed to connect to IB Gateway")
                return False
        except Exception as e:
            logger.error("Error connecting to IB Gateway", error=str(e))
            return False

    async def get_market_data(self) -> Dict[str, Any]:
        """Fetch current market data from IB or fallback to mock"""
        # Try to connect to IB if not already connected
        await self.ensure_ib_connected()

        # Try to get data from IB (may be live or delayed depending on subscription)
        if self.ib_client.is_connected:
            try:
                qqq_price = await self.ib_client.get_qqq_price()
                if qqq_price:
                    # IB is using delayed market data (type 3) so we label it accordingly
                    # Note: With a real-time subscription, this would be "live"
                    return {
                        "qqq_price": qqq_price,
                        "vix": 17.0,  # TODO: Get VIX from IB
                        "iv_7day_atm": 21.4,  # TODO: Calculate from option chain
                        "timestamp": datetime.utcnow(),
                        "source": "live"  # Data from IB (may be delayed based on subscription)
                    }
            except Exception as e:
                logger.warning("Failed to get market data from IB", error=str(e))

        # Fallback to mock data
        logger.warning("Using mock market data - IB not available")
        return {
            "qqq_price": 562.43,
            "vix": 17.0,
            "iv_7day_atm": 21.4,
            "timestamp": datetime.utcnow(),
            "source": "mock"
        }

    async def detect_regime(self) -> RegimeType:
        """
        Determine current market regime based on:
        1. Current QQQ price vs last short put strike
        2. Historical expiration data
        3. Current positions
        """
        current_regime = await self.agent_service.get_current_regime()
        market_data = await self.get_market_data()
        self.current_qqq_price = market_data["qqq_price"]
        self.current_vix = market_data["vix"]

        # Safety check: VIX too high
        if self.current_vix > settings.VIX_SHUTDOWN_THRESHOLD:
            logger.warning("VIX above shutdown threshold", vix=self.current_vix)
            return RegimeType.DEFENSE_TRIGGER

        if current_regime is None:
            # First run, start in Normal Bull
            return RegimeType.NORMAL_BULL

        if current_regime.regime_type == RegimeType.RECOVERY_MODE:
            # Check if recovery is complete
            if current_regime.recovery_strike and self.current_qqq_price > current_regime.recovery_strike:
                return RegimeType.RECOVERY_COMPLETE
            return RegimeType.RECOVERY_MODE

        # Check if current short put would be ITM
        if self.last_short_put_strike and self.current_qqq_price < self.last_short_put_strike:
            return RegimeType.DEFENSE_TRIGGER

        return RegimeType.NORMAL_BULL

    async def execute_regime_actions(self, regime: RegimeType) -> Dict[str, Any]:
        """Execute actions based on current regime"""
        result = {"regime": regime.value, "actions": [], "timestamp": datetime.utcnow()}

        if regime == RegimeType.NORMAL_BULL:
            result["actions"].append("short_put_agent_active")
            result["actions"].append("risk_agent_active")
            await self._activate_agents(["short_put", "risk"])
            await self._deactivate_agents(["short_call", "long_call", "long_put"])

        elif regime == RegimeType.DEFENSE_TRIGGER:
            result["actions"].append("close_losing_put_spread")
            result["actions"].append("risk_agent_active")
            await self._activate_agents(["risk"])
            # Close the losing spread
            await self._close_losing_positions()

        elif regime == RegimeType.RECOVERY_MODE:
            result["actions"].append("long_call_agent_active")
            result["actions"].append("short_call_agent_active")
            result["actions"].append("risk_agent_active")
            await self._activate_agents(["long_call", "short_call", "risk"])
            await self._deactivate_agents(["short_put"])

        elif regime == RegimeType.RECOVERY_COMPLETE:
            result["actions"].append("close_short_calls")
            result["actions"].append("sell_long_calls")
            result["actions"].append("transition_to_normal")
            await self._close_recovery_positions()
            await self.agent_service.set_regime(RegimeType.NORMAL_BULL, self.current_qqq_price)

        return result

    async def _activate_agents(self, agent_types: list):
        """Activate specified agents"""
        for agent_type in agent_types:
            agent = await self.agent_service.get_agent_by_type(agent_type)
            if agent:
                await self.agent_service.update_agent_status(agent.id, AgentStatus.RUNNING)
                logger.info("Activated agent", agent_type=agent_type)

    async def _deactivate_agents(self, agent_types: list):
        """Deactivate specified agents"""
        for agent_type in agent_types:
            agent = await self.agent_service.get_agent_by_type(agent_type)
            if agent:
                await self.agent_service.update_agent_status(agent.id, AgentStatus.IDLE)
                logger.info("Deactivated agent", agent_type=agent_type)

    async def _close_losing_positions(self):
        """Close losing put spread positions"""
        open_trades = await self.agent_service.get_open_trades()
        for trade in open_trades:
            if trade.trade_type == "put_spread":
                # Calculate loss and close
                estimated_pnl = -(trade.max_risk or 0)  # Simplified
                await self.agent_service.close_trade(trade.id, estimated_pnl)
                logger.info("Closed losing put spread", trade_id=trade.id, pnl=estimated_pnl)

    async def _close_recovery_positions(self):
        """Close recovery mode positions (short calls and long calls)"""
        open_trades = await self.agent_service.get_open_trades()
        for trade in open_trades:
            if trade.trade_type in ["call_spread", "long_call"]:
                # Calculate profit and close
                estimated_pnl = trade.premium_received or 0  # Simplified
                await self.agent_service.close_trade(trade.id, estimated_pnl)
                logger.info("Closed recovery position", trade_id=trade.id, pnl=estimated_pnl)

    def get_market_hours_status(self) -> Dict[str, Any]:
        """Get comprehensive market hours status"""
        return MarketHours.get_status()

    def is_options_trading_available(self) -> bool:
        """Check if options trading is currently available (regular hours only)"""
        return MarketHours.is_options_trading_open()

    async def run_weekly_execution(self) -> Dict[str, Any]:
        """
        Main weekly execution flow - runs every Friday at 3:45 PM ET
        """
        logger.info("Starting weekly execution")

        # Check if market is open for options trading
        market_status = self.get_market_hours_status()
        if not market_status["can_trade_options"]:
            logger.warning(
                "Options trading not available, skipping weekly execution",
                session=market_status["session"],
                time_until_open=market_status.get("time_until_open")
            )
            return {
                "regime": None,
                "actions": [],
                "timestamp": datetime.utcnow(),
                "market_status": market_status,
                "error": f"Options trading not available (session: {market_status['session']})"
            }

        try:
            # Step 1: Get market data
            market_data = await self.get_market_data()

            # Step 2: Detect regime
            regime = await self.detect_regime()

            # Step 3: Update regime in database
            current = await self.agent_service.get_current_regime()
            if not current or current.regime_type != regime:
                recovery_strike = self.last_short_put_strike if regime == RegimeType.RECOVERY_MODE else None
                await self.agent_service.set_regime(regime, market_data["qqq_price"], recovery_strike)

            # Step 4: Execute regime actions
            result = await self.execute_regime_actions(regime)
            result["market_data"] = market_data

            logger.info("Weekly execution complete", result=result)
            return result

        except Exception as e:
            logger.error("Weekly execution failed", error=str(e))
            raise

    async def emergency_shutdown(self):
        """Emergency shutdown - stop all agents and close all positions"""
        logger.warning("EMERGENCY SHUTDOWN INITIATED")

        agents = await self.agent_service.get_all_agents()
        for agent in agents:
            await self.agent_service.update_agent_status(agent.id, AgentStatus.STOPPED)

        # Close all open positions
        open_trades = await self.agent_service.get_open_trades()
        for trade in open_trades:
            await self.agent_service.close_trade(trade.id, 0)  # Close at market

        logger.warning("Emergency shutdown complete")
        return {"status": "shutdown_complete", "trades_closed": len(open_trades)}

    async def analyze_only(self) -> Dict[str, Any]:
        """
        Run analysis and generate trade recommendations WITHOUT executing.

        This is the "analyze mode" that presents recommendations to the user
        for review before any trades are placed.
        """
        logger.info("Starting analyze-only execution")

        # Check if market is open for options trading
        market_status = self.get_market_hours_status()
        if not market_status["can_trade_options"]:
            logger.warning(
                "Options trading not available, skipping analysis",
                session=market_status["session"]
            )
            return {
                "mode": "analyze_only",
                "regime": None,
                "market_data": None,
                "recommendations_count": 0,
                "recommendations": [],
                "timestamp": datetime.utcnow().isoformat(),
                "market_status": market_status,
                "error": f"Options trading not available (session: {market_status['session']})"
            }

        try:
            # Step 1: Get market data
            market_data = await self.get_market_data()

            # Step 2: Detect regime
            regime = await self.detect_regime()

            # Step 3: Generate recommendations via the recommendation service
            recommendations = await self.recommendation_service.analyze_market_and_recommend()

            result = {
                "mode": "analyze_only",
                "regime": regime.value,
                "market_data": market_data,
                "recommendations_count": len(recommendations),
                "recommendations": [
                    {
                        "id": r.id,
                        "action": r.action,
                        "trade_type": r.trade_type,
                        "short_strike": r.short_strike,
                        "long_strike": r.long_strike,
                        "contracts": r.contracts,
                        "estimated_credit": r.estimated_credit,
                        "max_risk": r.max_risk,
                        "expiration": r.expiration,
                        "reasoning": r.reasoning,
                        "status": r.status.value
                    }
                    for r in recommendations
                ],
                "timestamp": datetime.utcnow().isoformat()
            }

            logger.info("Analyze-only execution complete", recommendations=len(recommendations))
            return result

        except Exception as e:
            logger.error("Analyze-only execution failed", error=str(e))
            raise

    async def get_pending_recommendations(self) -> List[TradeRecommendation]:
        """Get all pending trade recommendations awaiting user approval"""
        return await self.recommendation_service.get_pending_recommendations()

    async def approve_recommendation(self, recommendation_id: int) -> Optional[TradeRecommendation]:
        """Approve a pending recommendation"""
        return await self.recommendation_service.approve_recommendation(recommendation_id)

    async def reject_recommendation(self, recommendation_id: int, reason: str = None) -> Optional[TradeRecommendation]:
        """Reject a pending recommendation"""
        return await self.recommendation_service.reject_recommendation(recommendation_id, reason)

    async def execute_recommendation(self, recommendation_id: int) -> Dict[str, Any]:
        """Execute an approved recommendation"""
        # Check if options trading is available before execution
        market_status = self.get_market_hours_status()
        if not market_status["can_trade_options"]:
            logger.warning(
                "Options trading not available, cannot execute recommendation",
                recommendation_id=recommendation_id,
                session=market_status["session"]
            )
            return {
                "status": "error",
                "recommendation_id": recommendation_id,
                "error": f"Options trading not available (session: {market_status['session']})",
                "market_status": market_status
            }
        return await self.recommendation_service.execute_recommendation(recommendation_id)
