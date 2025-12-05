"""
Gem Hunter API Routes

Endpoints for the Gem Hunter autonomous trading agent.
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import List, Optional
from pydantic import BaseModel

from app.core.database import SyncSessionLocal
from app.models.agent import Agent, GemPosition, GemWatchlist, GemPositionStatus, GemWatchlistStatus
from app.services.gem_hunter import GemHunterService
from app.services.broker.ib_client import get_ib_client

router = APIRouter()


# ============================================================
# Pydantic Models
# ============================================================

class GemHunterStateResponse(BaseModel):
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
    last_scan: Optional[str]
    last_trade: Optional[str]
    is_trading_enabled: bool


class WatchlistEntry(BaseModel):
    id: int
    symbol: str
    composite_score: float
    technical_score: Optional[float]
    fundamental_score: Optional[float]
    momentum_score: Optional[float]
    entry_price: float
    target_price: float
    stop_loss: float
    entry_trigger: str
    created_at: Optional[str]


class PositionResponse(BaseModel):
    id: int
    symbol: str
    position_type: str
    quantity: int
    entry_price: float
    current_price: Optional[float]
    stop_loss: Optional[float]
    take_profit: Optional[float]
    unrealized_pnl: Optional[float]
    allocated_amount: float
    created_at: Optional[str]


class TradeHistoryEntry(BaseModel):
    id: int
    symbol: str
    position_type: str
    quantity: int
    entry_price: float
    exit_price: Optional[float]
    realized_pnl: Optional[float]
    status: str
    entry_reason: Optional[str]
    exit_reason: Optional[str]
    created_at: Optional[str]
    closed_at: Optional[str]


class ScanResponse(BaseModel):
    timestamp: str
    screened: int
    analyzed: int
    added_to_watchlist: int
    trades_executed: int
    positions_closed: int
    errors: List[str]


class AddSymbolRequest(BaseModel):
    symbol: str


class ActionResponse(BaseModel):
    success: bool
    message: str


# ============================================================
# Helper Functions
# ============================================================

def get_gem_hunter_service_sync() -> tuple[GemHunterService, any]:
    """
    Get or create the Gem Hunter service instance with sync session.
    Returns tuple of (service, session) - caller must close session when done.
    """
    sync_session = SyncSessionLocal()

    # Find the Gem Hunter agent using sync query
    agent = sync_session.query(Agent).filter(Agent.name == "gem_hunter").first()

    if not agent:
        sync_session.close()
        raise HTTPException(status_code=404, detail="Gem Hunter agent not found")

    # Get IB client
    ib_client = get_ib_client()

    # Parse config
    config = agent.config or {}

    # Return service instance and session (caller must close session)
    service = GemHunterService(
        agent_id=agent.id,
        db=sync_session,
        ib_client=ib_client,
        config=config
    )
    return service, sync_session


# ============================================================
# Routes
# ============================================================

@router.get("/state", response_model=GemHunterStateResponse)
async def get_state():
    """Get current state of the Gem Hunter agent"""
    service, session = get_gem_hunter_service_sync()
    try:
        state = await service.get_state()

        return GemHunterStateResponse(
            agent_id=state.agent_id,
            status=state.status,
            allocated_capital=state.allocated_capital,
            deployed_capital=state.deployed_capital,
            available_capital=state.available_capital,
            daily_pnl=state.daily_pnl,
            total_pnl=state.total_pnl,
            open_positions=state.open_positions,
            max_positions=state.max_positions,
            watchlist_count=state.watchlist_count,
            last_scan=state.last_scan.isoformat() if state.last_scan else None,
            last_trade=state.last_trade.isoformat() if state.last_trade else None,
            is_trading_enabled=state.is_trading_enabled
        )
    finally:
        session.close()


@router.get("/watchlist", response_model=List[WatchlistEntry])
async def get_watchlist():
    """Get current watchlist entries"""
    service, session = get_gem_hunter_service_sync()
    try:
        watchlist = await service.get_watchlist()
        return watchlist
    finally:
        session.close()


@router.get("/positions", response_model=List[PositionResponse])
async def get_positions():
    """Get current open positions"""
    service, session = get_gem_hunter_service_sync()
    try:
        positions = await service.get_positions()
        return positions
    finally:
        session.close()


@router.get("/history", response_model=List[TradeHistoryEntry])
async def get_trade_history(limit: int = 50):
    """Get trade history"""
    service, session = get_gem_hunter_service_sync()
    try:
        history = await service.get_trade_history(limit=limit)
        return history
    finally:
        session.close()


@router.post("/scan", response_model=ScanResponse)
async def trigger_scan(background_tasks: BackgroundTasks):
    """Trigger a manual market scan"""
    service, session = get_gem_hunter_service_sync()
    try:
        result = await service.manual_scan()
        return result
    finally:
        session.close()


@router.post("/watchlist/add", response_model=ActionResponse)
async def add_to_watchlist(request: AddSymbolRequest):
    """Manually add a symbol to the watchlist"""
    service, session = get_gem_hunter_service_sync()
    try:
        result = await service.add_to_watchlist(request.symbol.upper())
        return ActionResponse(
            success=result.get("success", False),
            message=result.get("message", "")
        )
    finally:
        session.close()


@router.post("/watchlist/{symbol}/remove", response_model=ActionResponse)
async def remove_from_watchlist(symbol: str):
    """Remove a symbol from the watchlist"""
    service, session = get_gem_hunter_service_sync()
    try:
        result = await service.remove_from_watchlist(symbol.upper())
        return ActionResponse(
            success=result.get("success", False),
            message=result.get("message", "")
        )
    finally:
        session.close()


@router.post("/positions/{position_id}/close", response_model=ActionResponse)
async def close_position(position_id: int):
    """Manually close a position"""
    service, session = get_gem_hunter_service_sync()
    try:
        result = await service.close_position(position_id)
        return ActionResponse(
            success=result.get("success", False),
            message=result.get("message", "")
        )
    finally:
        session.close()


@router.get("/config")
async def get_config():
    """Get current Gem Hunter configuration"""
    sync_session = SyncSessionLocal()
    try:
        agent = sync_session.query(Agent).filter(Agent.name == "gem_hunter").first()

        if not agent:
            raise HTTPException(status_code=404, detail="Gem Hunter agent not found")

        return agent.config or {}
    finally:
        sync_session.close()


@router.patch("/config")
async def update_config(config: dict):
    """Update Gem Hunter configuration"""
    sync_session = SyncSessionLocal()
    try:
        agent = sync_session.query(Agent).filter(Agent.name == "gem_hunter").first()

        if not agent:
            raise HTTPException(status_code=404, detail="Gem Hunter agent not found")

        # Merge with existing config
        existing = agent.config or {}
        existing.update(config)
        agent.config = existing

        sync_session.commit()
        sync_session.refresh(agent)

        return agent.config
    finally:
        sync_session.close()
