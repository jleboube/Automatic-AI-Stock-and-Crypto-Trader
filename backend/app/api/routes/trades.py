from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.core.database import get_db
from app.schemas.agent import TradeCreate, TradeResponse
from app.services.agent_service import AgentService

router = APIRouter()


@router.get("/", response_model=List[TradeResponse])
async def get_trades(limit: int = 100, db: AsyncSession = Depends(get_db)):
    """Get all trades"""
    service = AgentService(db)
    trades = await service.get_all_trades(limit=limit)
    return trades


@router.get("/open", response_model=List[TradeResponse])
async def get_open_trades(db: AsyncSession = Depends(get_db)):
    """Get all open trades"""
    service = AgentService(db)
    trades = await service.get_open_trades()
    return trades


@router.post("/", response_model=TradeResponse)
async def create_trade(trade_data: TradeCreate, db: AsyncSession = Depends(get_db)):
    """Create a new trade"""
    service = AgentService(db)
    trade = await service.create_trade(trade_data)
    return trade


@router.post("/{trade_id}/close")
async def close_trade(trade_id: int, pnl: float, db: AsyncSession = Depends(get_db)):
    """Close a trade"""
    service = AgentService(db)
    trade = await service.close_trade(trade_id, pnl)
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    return {"status": "closed", "trade_id": trade_id, "pnl": pnl}


@router.get("/stats")
async def get_trade_stats(db: AsyncSession = Depends(get_db)):
    """Get trade statistics"""
    service = AgentService(db)
    stats = await service.get_trade_stats()
    return stats
