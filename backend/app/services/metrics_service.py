from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timedelta
from typing import List, Dict, Any

from app.models.agent import Agent, AgentRun, Trade, AgentStatus
from app.models.metrics import AgentMetric, SystemMetric
from app.services.agent_service import AgentService


class MetricsService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.agent_service = AgentService(db)

    async def record_agent_metric(self, agent_id: int, metric_name: str, value: float):
        metric = AgentMetric(
            agent_id=agent_id,
            metric_name=metric_name,
            metric_value=value
        )
        self.db.add(metric)
        await self.db.commit()

    async def record_system_metric(self, metric_name: str, value: float, metadata: str = None):
        metric = SystemMetric(
            metric_name=metric_name,
            metric_value=value,
            metric_metadata=metadata
        )
        self.db.add(metric)
        await self.db.commit()

    async def get_agent_metrics(self, agent_id: int, hours: int = 24) -> List[AgentMetric]:
        since = datetime.utcnow() - timedelta(hours=hours)
        result = await self.db.execute(
            select(AgentMetric)
            .where(AgentMetric.agent_id == agent_id, AgentMetric.recorded_at > since)
            .order_by(AgentMetric.recorded_at.desc())
        )
        return result.scalars().all()

    async def get_system_metrics(self, metric_name: str = None, hours: int = 24) -> List[SystemMetric]:
        since = datetime.utcnow() - timedelta(hours=hours)
        query = select(SystemMetric).where(SystemMetric.recorded_at > since)
        if metric_name:
            query = query.where(SystemMetric.metric_name == metric_name)
        result = await self.db.execute(query.order_by(SystemMetric.recorded_at.desc()))
        return result.scalars().all()

    async def get_dashboard_data(self) -> Dict[str, Any]:
        """Get all data needed for the dashboard"""
        agents = await self.agent_service.get_all_agents()
        current_regime = await self.agent_service.get_current_regime()
        trade_stats = await self.agent_service.get_trade_stats()
        recent_trades = await self.agent_service.get_all_trades(limit=10)

        agent_summaries = []
        for agent in agents:
            runs = await self.agent_service.get_agent_runs(agent.id, limit=100)
            successful = sum(1 for r in runs if r.status == AgentStatus.IDLE)
            failed = sum(1 for r in runs if r.status == AgentStatus.ERROR)

            # Get trades for this agent
            trades_result = await self.db.execute(
                select(Trade).where(Trade.agent_id == agent.id)
            )
            agent_trades = trades_result.scalars().all()
            open_trades = sum(1 for t in agent_trades if t.status == "open")
            total_pnl = sum(t.pnl or 0 for t in agent_trades if t.pnl)

            agent_summaries.append({
                "agent_id": agent.id,
                "agent_name": agent.name,
                "agent_type": agent.agent_type,
                "status": agent.status.value,
                "total_runs": len(runs),
                "successful_runs": successful,
                "failed_runs": failed,
                "total_trades": len(agent_trades),
                "open_trades": open_trades,
                "total_pnl": total_pnl
            })

        return {
            "current_regime": current_regime.regime_type.value if current_regime else None,
            "regime_started_at": current_regime.started_at if current_regime else None,
            "qqq_price": current_regime.qqq_price_at_start if current_regime else None,
            "vix": None,  # TODO: Get from market data
            "account_value": None,  # TODO: Get from broker
            "buying_power": None,
            "deployed_capital_pct": None,
            "month_pnl": None,
            "ytd_pnl": None,
            "drawdown_pct": None,
            "agents": agent_summaries,
            "trade_summary": trade_stats,
            "recent_trades": [
                {
                    "id": t.id,
                    "agent_id": t.agent_id,
                    "trade_type": t.trade_type,
                    "symbol": t.symbol,
                    "contracts": t.contracts,
                    "status": t.status,
                    "pnl": t.pnl,
                    "opened_at": t.opened_at.isoformat() if t.opened_at else None
                }
                for t in recent_trades
            ],
            "recent_alerts": []  # TODO: Implement alerts
        }

    async def get_pnl_chart_data(self, days: int = 30) -> List[Dict[str, Any]]:
        """Get P&L data for chart visualization"""
        since = datetime.utcnow() - timedelta(days=days)
        result = await self.db.execute(
            select(Trade)
            .where(Trade.closed_at > since, Trade.status == "closed")
            .order_by(Trade.closed_at)
        )
        trades = result.scalars().all()

        cumulative_pnl = 0
        data = []
        for trade in trades:
            cumulative_pnl += trade.pnl or 0
            data.append({
                "date": trade.closed_at.isoformat(),
                "pnl": trade.pnl or 0,
                "cumulative_pnl": cumulative_pnl
            })

        return data

    async def get_trade_history_by_type(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get trade history grouped by type"""
        result = await self.db.execute(select(Trade).order_by(Trade.opened_at.desc()))
        trades = result.scalars().all()

        grouped = {}
        for trade in trades:
            if trade.trade_type not in grouped:
                grouped[trade.trade_type] = []
            grouped[trade.trade_type].append({
                "id": trade.id,
                "symbol": trade.symbol,
                "contracts": trade.contracts,
                "short_strike": trade.short_strike,
                "long_strike": trade.long_strike,
                "premium": trade.premium_received or trade.premium_paid,
                "pnl": trade.pnl,
                "status": trade.status,
                "opened_at": trade.opened_at.isoformat() if trade.opened_at else None,
                "closed_at": trade.closed_at.isoformat() if trade.closed_at else None
            })

        return grouped
