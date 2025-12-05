from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from sqlalchemy.orm import selectinload
from typing import List, Optional
from datetime import datetime

from app.models.agent import Agent, AgentRun, Trade, Regime, AgentStatus, RegimeType
from app.schemas.agent import AgentCreate, AgentUpdate, TradeCreate


class AgentService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_all_agents(self) -> List[Agent]:
        result = await self.db.execute(select(Agent).order_by(Agent.id))
        return result.scalars().all()

    async def get_agent(self, agent_id: int) -> Optional[Agent]:
        result = await self.db.execute(select(Agent).where(Agent.id == agent_id))
        return result.scalar_one_or_none()

    async def get_agent_by_name(self, name: str) -> Optional[Agent]:
        result = await self.db.execute(select(Agent).where(Agent.name == name))
        return result.scalar_one_or_none()

    async def get_agent_by_type(self, agent_type: str) -> Optional[Agent]:
        result = await self.db.execute(select(Agent).where(Agent.agent_type == agent_type))
        return result.scalar_one_or_none()

    async def create_agent(self, agent_data: AgentCreate) -> Agent:
        agent = Agent(**agent_data.model_dump())
        self.db.add(agent)
        await self.db.commit()
        await self.db.refresh(agent)
        return agent

    async def update_agent(self, agent_id: int, agent_data: AgentUpdate) -> Optional[Agent]:
        agent = await self.get_agent(agent_id)
        if not agent:
            return None

        update_data = agent_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(agent, key, value)

        await self.db.commit()
        await self.db.refresh(agent)
        return agent

    async def update_agent_status(self, agent_id: int, status: AgentStatus) -> Optional[Agent]:
        agent = await self.get_agent(agent_id)
        if not agent:
            return None

        agent.status = status
        await self.db.commit()
        await self.db.refresh(agent)
        return agent

    async def start_agent_run(self, agent_id: int) -> AgentRun:
        run = AgentRun(agent_id=agent_id, status=AgentStatus.RUNNING)
        self.db.add(run)

        # Update the agent's last_run_at timestamp
        agent = await self.get_agent(agent_id)
        if agent:
            agent.last_run_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(run)
        return run

    async def end_agent_run(
        self,
        run_id: int,
        status: AgentStatus,
        result: dict = None,
        error_message: str = None
    ) -> Optional[AgentRun]:
        result_query = await self.db.execute(select(AgentRun).where(AgentRun.id == run_id))
        run = result_query.scalar_one_or_none()
        if not run:
            return None

        run.ended_at = datetime.utcnow()
        run.status = status
        run.result = result
        run.error_message = error_message

        await self.db.commit()
        await self.db.refresh(run)
        return run

    async def get_agent_runs(self, agent_id: int, limit: int = 50) -> List[AgentRun]:
        result = await self.db.execute(
            select(AgentRun)
            .where(AgentRun.agent_id == agent_id)
            .order_by(AgentRun.started_at.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def create_trade(self, trade_data: TradeCreate) -> Trade:
        trade = Trade(**trade_data.model_dump())
        self.db.add(trade)
        await self.db.commit()
        await self.db.refresh(trade)
        return trade

    async def get_open_trades(self) -> List[Trade]:
        result = await self.db.execute(
            select(Trade).where(Trade.status == "open").order_by(Trade.opened_at.desc())
        )
        return result.scalars().all()

    async def get_all_trades(self, limit: int = 100) -> List[Trade]:
        result = await self.db.execute(
            select(Trade).order_by(Trade.opened_at.desc()).limit(limit)
        )
        return result.scalars().all()

    async def close_trade(self, trade_id: int, pnl: float) -> Optional[Trade]:
        result = await self.db.execute(select(Trade).where(Trade.id == trade_id))
        trade = result.scalar_one_or_none()
        if not trade:
            return None

        trade.status = "closed"
        trade.closed_at = datetime.utcnow()
        trade.pnl = pnl

        await self.db.commit()
        await self.db.refresh(trade)
        return trade

    async def get_current_regime(self) -> Optional[Regime]:
        result = await self.db.execute(
            select(Regime).where(Regime.is_active == True).order_by(Regime.started_at.desc())
        )
        return result.scalar_one_or_none()

    async def set_regime(self, regime_type: RegimeType, qqq_price: float, recovery_strike: float = None) -> Regime:
        # End current regime
        current = await self.get_current_regime()
        if current:
            current.is_active = False
            current.ended_at = datetime.utcnow()

        # Start new regime
        new_regime = Regime(
            regime_type=regime_type,
            qqq_price_at_start=qqq_price,
            recovery_strike=recovery_strike,
            is_active=True
        )
        self.db.add(new_regime)
        await self.db.commit()
        await self.db.refresh(new_regime)
        return new_regime

    async def get_trade_stats(self) -> dict:
        total_result = await self.db.execute(select(func.count(Trade.id)))
        total = total_result.scalar()

        open_result = await self.db.execute(
            select(func.count(Trade.id)).where(Trade.status == "open")
        )
        open_count = open_result.scalar()

        closed_result = await self.db.execute(
            select(func.count(Trade.id)).where(Trade.status == "closed")
        )
        closed_count = closed_result.scalar()

        pnl_result = await self.db.execute(
            select(func.sum(Trade.pnl)).where(Trade.status == "closed")
        )
        total_pnl = pnl_result.scalar() or 0

        winning_result = await self.db.execute(
            select(func.count(Trade.id)).where(Trade.status == "closed", Trade.pnl > 0)
        )
        winning = winning_result.scalar()

        win_rate = (winning / closed_count * 100) if closed_count > 0 else 0

        premium_result = await self.db.execute(
            select(func.avg(Trade.premium_received)).where(Trade.premium_received.isnot(None))
        )
        avg_premium = premium_result.scalar() or 0

        return {
            "total_trades": total,
            "open_trades": open_count,
            "closed_trades": closed_count,
            "total_pnl": total_pnl,
            "win_rate": win_rate,
            "avg_premium": avg_premium
        }
