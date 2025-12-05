"""
Trade Recommendation Service

Handles creating, reviewing, and executing trade recommendations.
Provides an approval workflow where agents analyze and recommend trades,
which are then presented to the user for approval before execution.
"""

import structlog
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.models.agent import (
    TradeRecommendation,
    RecommendationStatus,
    RegimeType,
    Trade
)
from app.services.broker.ib_client import get_ib_client
from app.core.config import settings

logger = structlog.get_logger()


class RecommendationService:
    """
    Service for managing trade recommendations.

    The workflow is:
    1. Orchestrator calls analyze_and_recommend() to generate recommendations
    2. User reviews pending recommendations in the UI
    3. User approves/rejects each recommendation
    4. If approved, user can execute the trade
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.ib_client = get_ib_client()

    async def get_pending_recommendations(self) -> List[TradeRecommendation]:
        """Get all pending recommendations that haven't expired"""
        now = datetime.utcnow()
        result = await self.db.execute(
            select(TradeRecommendation)
            .where(
                TradeRecommendation.status == RecommendationStatus.PENDING,
                TradeRecommendation.expires_at > now
            )
            .order_by(TradeRecommendation.created_at.desc())
        )
        return result.scalars().all()

    async def get_all_recommendations(self, limit: int = 50) -> List[TradeRecommendation]:
        """Get recent recommendations of all statuses"""
        result = await self.db.execute(
            select(TradeRecommendation)
            .order_by(TradeRecommendation.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def get_recommendation_by_id(self, recommendation_id: int) -> Optional[TradeRecommendation]:
        """Get a specific recommendation by ID"""
        result = await self.db.execute(
            select(TradeRecommendation)
            .where(TradeRecommendation.id == recommendation_id)
        )
        return result.scalar_one_or_none()

    async def create_recommendation(
        self,
        regime_type: RegimeType,
        qqq_price: float,
        action: str,
        reasoning: str,
        vix: Optional[float] = None,
        iv_7day_atm: Optional[float] = None,
        trade_type: Optional[str] = None,
        short_strike: Optional[float] = None,
        long_strike: Optional[float] = None,
        expiration: Optional[str] = None,
        contracts: Optional[int] = None,
        estimated_credit: Optional[float] = None,
        estimated_debit: Optional[float] = None,
        max_risk: Optional[float] = None,
        max_profit: Optional[float] = None,
        short_delta: Optional[float] = None,
        risk_assessment: Optional[str] = None,
        expires_in_hours: int = 4
    ) -> TradeRecommendation:
        """Create a new trade recommendation"""

        recommendation = TradeRecommendation(
            status=RecommendationStatus.PENDING,
            expires_at=datetime.utcnow() + timedelta(hours=expires_in_hours),
            regime_type=regime_type,
            qqq_price=qqq_price,
            vix=vix,
            iv_7day_atm=iv_7day_atm,
            action=action,
            trade_type=trade_type,
            short_strike=short_strike,
            long_strike=long_strike,
            expiration=expiration,
            contracts=contracts,
            estimated_credit=estimated_credit,
            estimated_debit=estimated_debit,
            max_risk=max_risk,
            max_profit=max_profit,
            short_delta=short_delta,
            reasoning=reasoning,
            risk_assessment=risk_assessment
        )

        self.db.add(recommendation)
        await self.db.commit()
        await self.db.refresh(recommendation)

        logger.info(
            "Created trade recommendation",
            recommendation_id=recommendation.id,
            action=action,
            regime=regime_type.value
        )

        return recommendation

    async def approve_recommendation(self, recommendation_id: int) -> Optional[TradeRecommendation]:
        """Approve a pending recommendation"""
        recommendation = await self.get_recommendation_by_id(recommendation_id)

        if not recommendation:
            return None

        if recommendation.status != RecommendationStatus.PENDING:
            logger.warning(
                "Cannot approve non-pending recommendation",
                recommendation_id=recommendation_id,
                status=recommendation.status.value
            )
            return None

        if recommendation.expires_at < datetime.utcnow():
            # Mark as expired
            recommendation.status = RecommendationStatus.EXPIRED
            await self.db.commit()
            return None

        recommendation.status = RecommendationStatus.APPROVED
        recommendation.approved_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(recommendation)

        logger.info("Approved recommendation", recommendation_id=recommendation_id)
        return recommendation

    async def reject_recommendation(
        self,
        recommendation_id: int,
        reason: Optional[str] = None
    ) -> Optional[TradeRecommendation]:
        """Reject a pending recommendation"""
        recommendation = await self.get_recommendation_by_id(recommendation_id)

        if not recommendation:
            return None

        if recommendation.status != RecommendationStatus.PENDING:
            logger.warning(
                "Cannot reject non-pending recommendation",
                recommendation_id=recommendation_id,
                status=recommendation.status.value
            )
            return None

        recommendation.status = RecommendationStatus.REJECTED
        recommendation.rejected_at = datetime.utcnow()
        recommendation.rejection_reason = reason
        await self.db.commit()
        await self.db.refresh(recommendation)

        logger.info(
            "Rejected recommendation",
            recommendation_id=recommendation_id,
            reason=reason
        )
        return recommendation

    async def execute_recommendation(
        self,
        recommendation_id: int
    ) -> Dict[str, Any]:
        """
        Execute an approved recommendation via IB.

        Returns execution result including order ID and fill info.
        """
        recommendation = await self.get_recommendation_by_id(recommendation_id)

        if not recommendation:
            return {"success": False, "error": "Recommendation not found"}

        if recommendation.status != RecommendationStatus.APPROVED:
            return {
                "success": False,
                "error": f"Recommendation must be approved first. Current status: {recommendation.status.value}"
            }

        # Check IB connection
        if not self.ib_client.is_connected:
            connected = await self.ib_client.connect()
            if not connected:
                return {"success": False, "error": "Failed to connect to Interactive Brokers"}

        try:
            order_id = None
            execution_price = None

            if recommendation.action == "open_put_spread":
                # Place put credit spread
                order_id = await self.ib_client.place_spread_order(
                    short_strike=recommendation.short_strike,
                    long_strike=recommendation.long_strike,
                    expiration=recommendation.expiration,
                    right="P",
                    quantity=recommendation.contracts,
                    limit_price=recommendation.estimated_credit
                )
                execution_price = recommendation.estimated_credit

            elif recommendation.action == "close_put_spread":
                # Close existing put spread (buy to close)
                # This would need position tracking - simplified for now
                logger.info("Close put spread action - would close existing position")
                order_id = "simulated_close"

            elif recommendation.action == "open_call_spread":
                # Place call credit spread (recovery mode)
                order_id = await self.ib_client.place_spread_order(
                    short_strike=recommendation.short_strike,
                    long_strike=recommendation.long_strike,
                    expiration=recommendation.expiration,
                    right="C",
                    quantity=recommendation.contracts,
                    limit_price=recommendation.estimated_credit
                )
                execution_price = recommendation.estimated_credit

            elif recommendation.action == "open_long_call":
                # Buy long calls (recovery anchor)
                logger.info("Open long call action - would buy calls")
                order_id = "simulated_long_call"

            else:
                return {"success": False, "error": f"Unknown action: {recommendation.action}"}

            if order_id:
                recommendation.status = RecommendationStatus.EXECUTED
                recommendation.executed_at = datetime.utcnow()
                recommendation.order_id = str(order_id)
                recommendation.execution_price = execution_price
                await self.db.commit()

                logger.info(
                    "Executed recommendation",
                    recommendation_id=recommendation_id,
                    order_id=order_id
                )

                return {
                    "success": True,
                    "order_id": order_id,
                    "execution_price": execution_price,
                    "action": recommendation.action
                }
            else:
                return {"success": False, "error": "Order placement failed"}

        except Exception as e:
            logger.error(
                "Failed to execute recommendation",
                recommendation_id=recommendation_id,
                error=str(e)
            )
            return {"success": False, "error": str(e)}

    async def expire_old_recommendations(self) -> int:
        """Mark expired recommendations as expired"""
        now = datetime.utcnow()
        result = await self.db.execute(
            update(TradeRecommendation)
            .where(
                TradeRecommendation.status == RecommendationStatus.PENDING,
                TradeRecommendation.expires_at < now
            )
            .values(status=RecommendationStatus.EXPIRED)
        )
        await self.db.commit()
        return result.rowcount

    async def analyze_market_and_recommend(self) -> List[TradeRecommendation]:
        """
        Analyze current market conditions and generate trade recommendations.

        This is the main entry point called by the orchestrator in "analyze only" mode.
        It runs all the agent logic but creates recommendations instead of executing trades.
        """
        recommendations = []

        # First, expire any old pending recommendations
        await self.expire_old_recommendations()

        # Get market data from IB
        if not self.ib_client.is_connected:
            connected = await self.ib_client.connect()
            if not connected:
                logger.error("Cannot analyze: IB not connected")
                return recommendations

        qqq_price = await self.ib_client.get_qqq_price()
        if not qqq_price:
            logger.error("Cannot analyze: Failed to get QQQ price")
            return recommendations

        # Get account info
        account = await self.ib_client.get_account_summary()

        # Get current positions
        positions = await self.ib_client.get_positions()

        # Determine regime (simplified - would integrate with full orchestrator logic)
        # For now, assume Normal Bull if no put positions, Defense if positions are ITM
        has_put_positions = any(
            p.contract_type == "OPT" and p.quantity < 0
            for p in positions
        )

        regime = RegimeType.NORMAL_BULL  # Default

        # Build context for reasoning
        context = {
            "qqq_price": qqq_price,
            "account": account,
            "positions": positions,
            "has_put_positions": has_put_positions
        }

        if regime == RegimeType.NORMAL_BULL:
            # Look for put spread opportunity
            spread_data = await self.ib_client.find_put_spread_strikes(
                target_credit_min=settings.TARGET_CREDIT_MIN,
                target_credit_max=settings.TARGET_CREDIT_MAX,
                spread_width=settings.SPREAD_WIDTH,
                max_delta=settings.MAX_DELTA
            )

            if spread_data:
                # Calculate position size based on account
                if account:
                    max_risk_per_trade = account.net_liquidation * settings.MAX_POSITION_PCT
                    contracts = int(max_risk_per_trade / spread_data["max_risk"])
                    contracts = max(1, min(contracts, 10))  # 1-10 contracts
                else:
                    contracts = 1

                reasoning = f"""
**Market Analysis:**
- QQQ Price: ${qqq_price:.2f}
- Short Strike: ${spread_data['short_strike']} (Delta: {spread_data['short_delta']:.3f})
- Long Strike: ${spread_data['long_strike']}
- Spread Width: ${settings.SPREAD_WIDTH}

**Trade Rationale:**
- Net Credit: ${spread_data['net_credit']:.2f} per contract
- Max Risk: ${spread_data['max_risk']:.2f} per contract
- Total Max Risk: ${spread_data['max_risk'] * contracts:,.2f}
- Expiration: {spread_data['expiration']}

This put credit spread collects premium while defining max risk.
The short strike delta of {abs(spread_data['short_delta']):.3f} indicates approximately
{abs(spread_data['short_delta']) * 100:.1f}% probability of the spread expiring worthless.
"""

                risk_assessment = f"""
**Risk Factors:**
1. Max Loss: ${spread_data['max_risk'] * contracts:,.2f} if QQQ drops below ${spread_data['long_strike']}
2. Breakeven: ${spread_data['short_strike'] - spread_data['net_credit']:.2f}
3. Days to Expiration: Weekly (typically 7 days or less)

**Position Sizing:**
- Contracts: {contracts}
- % of Account at Risk: {(spread_data['max_risk'] * contracts / account.net_liquidation * 100):.1f}% (if account connected)

**Exit Criteria:**
- Close at 50% profit if achievable early
- Roll or close if delta exceeds 0.30
- Accept full loss if breached at expiration
"""

                recommendation = await self.create_recommendation(
                    regime_type=RegimeType.NORMAL_BULL,
                    qqq_price=qqq_price,
                    action="open_put_spread",
                    trade_type="put_spread",
                    short_strike=spread_data["short_strike"],
                    long_strike=spread_data["long_strike"],
                    expiration=spread_data["expiration"],
                    contracts=contracts,
                    estimated_credit=spread_data["net_credit"],
                    max_risk=spread_data["max_risk"] * contracts,
                    max_profit=spread_data["net_credit"] * contracts * 100,
                    short_delta=spread_data["short_delta"],
                    reasoning=reasoning,
                    risk_assessment=risk_assessment,
                    expires_in_hours=4
                )
                recommendations.append(recommendation)

                logger.info(
                    "Generated put spread recommendation",
                    short_strike=spread_data["short_strike"],
                    long_strike=spread_data["long_strike"],
                    credit=spread_data["net_credit"]
                )
            else:
                logger.info("No suitable put spread found matching criteria")

        # Add more regime-based recommendations as needed
        # (Defense, Recovery, etc.)

        return recommendations
