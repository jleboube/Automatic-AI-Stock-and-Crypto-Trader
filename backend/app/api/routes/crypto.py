"""
Crypto API Routes

Endpoints for the Crypto section and Crypto Hunter agent.
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import List, Optional
from pydantic import BaseModel

from app.core.database import SyncSessionLocal
from app.models.agent import Agent
from app.models.crypto import CryptoPosition, CryptoWatchlist, CryptoPositionStatus, CryptoWatchlistStatus
from app.services.crypto_hunter import CryptoHunterService
from app.services.broker.robinhood_client import get_robinhood_client
from app.services.scheduler import (
    start_agent_scheduler, stop_agent_scheduler, get_scheduler_status
)

router = APIRouter()


# ============================================================
# Pydantic Models
# ============================================================

class CryptoStatusResponse(BaseModel):
    connected: bool
    configured: bool
    account_id: Optional[str]
    message: str


class CryptoAccountResponse(BaseModel):
    account_id: str
    status: str
    buying_power: float
    buying_power_currency: str
    is_active: bool


class CryptoHoldingResponse(BaseModel):
    asset_code: str
    total_quantity: float
    available_quantity: float
    held_for_orders: float
    cost_basis: Optional[float]
    market_value: Optional[float]


class CryptoHunterStateResponse(BaseModel):
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


class CryptoWatchlistEntry(BaseModel):
    id: int
    symbol: str
    composite_score: float
    trend_score: Optional[float]
    fundamental_score: Optional[float]
    momentum_score: Optional[float]
    entry_price: float
    target_price: float
    stop_loss: float
    entry_trigger: str
    created_at: Optional[str]


class CryptoPositionResponse(BaseModel):
    id: int
    symbol: str
    side: str
    quantity: float
    entry_price: float
    current_price: Optional[float]
    stop_loss: Optional[float]
    take_profit: Optional[float]
    unrealized_pnl: Optional[float]
    allocated_amount: float
    created_at: Optional[str]


class CryptoTradeHistoryEntry(BaseModel):
    id: int
    symbol: str
    side: str
    quantity: float
    entry_price: float
    exit_price: Optional[float]
    realized_pnl: Optional[float]
    status: str
    entry_reason: Optional[str]
    exit_reason: Optional[str]
    created_at: Optional[str]
    closed_at: Optional[str]


class CryptoQuoteResponse(BaseModel):
    symbol: str
    bid_price: float
    ask_price: float
    mark_price: float
    high_price: Optional[float]
    low_price: Optional[float]
    open_price: Optional[float]
    volume: Optional[float]


class ScanResponse(BaseModel):
    timestamp: str
    pairs_scanned: int
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

def _ensure_crypto_hunter_agent(session) -> Agent:
    """Get or create the crypto_hunter agent"""
    from app.models.agent import AgentStatus

    agent = session.query(Agent).filter(Agent.name == "crypto_hunter").first()

    if not agent:
        # Create the crypto_hunter agent with default config
        agent = Agent(
            name="crypto_hunter",
            agent_type="crypto_hunter",
            description="Autonomous crypto trading agent that learns trends, compares fundamentals, and executes trades via Robinhood 24/7",
            status=AgentStatus.IDLE,
            is_active=True,
            config={
                "allocated_capital": 5000,
                "max_positions": 5,
                "max_position_pct": 0.20,
                "daily_loss_limit_pct": 0.05,
                "stop_loss_pct": 0.08,
                "take_profit_pct": 0.15,
                "trailing_stop_pct": 0.05,
                "min_composite_score": 65,
                "auto_trade": False,
                "scan_interval_minutes": 15,
                "max_hold_days": 30,
                "technical_weight": 0.4,
                "fundamental_weight": 0.3,
                "momentum_weight": 0.3,
                "trading_enabled": False
            }
        )
        session.add(agent)
        session.commit()
        session.refresh(agent)

    return agent


def get_crypto_hunter_service_sync() -> tuple:
    """
    Get or create the Crypto Hunter service instance with sync session.
    Returns tuple of (service, session) - caller must close session when done.
    """
    sync_session = SyncSessionLocal()

    # Get or create the Crypto Hunter agent
    agent = _ensure_crypto_hunter_agent(sync_session)

    # Get Robinhood client
    robinhood_client = get_robinhood_client()

    # Parse config
    config = agent.config or {}

    # Return service instance and session
    service = CryptoHunterService(
        agent_id=agent.id,
        db=sync_session,
        robinhood_client=robinhood_client,
        config=config
    )
    return service, sync_session


# ============================================================
# Connection & Account Routes
# ============================================================

@router.get("/status", response_model=CryptoStatusResponse)
async def get_status():
    """Get Robinhood connection status"""
    client = get_robinhood_client()

    if not client.is_configured:
        return CryptoStatusResponse(
            connected=False,
            configured=False,
            account_id=None,
            message="Robinhood API not configured. Add ROBINHOOD_API_KEY and ROBINHOOD_PRIVATE_KEY to .env"
        )

    try:
        account = await client.get_account()
        if account:
            return CryptoStatusResponse(
                connected=True,
                configured=True,
                account_id=account.account_id,
                message="Connected to Robinhood Crypto API"
            )
        else:
            return CryptoStatusResponse(
                connected=False,
                configured=True,
                account_id=None,
                message="Could not retrieve account information"
            )
    except Exception as e:
        return CryptoStatusResponse(
            connected=False,
            configured=True,
            account_id=None,
            message=f"Connection error: {str(e)}"
        )


@router.get("/account", response_model=CryptoAccountResponse)
async def get_account():
    """Get Robinhood crypto account info"""
    client = get_robinhood_client()

    if not client.is_configured:
        raise HTTPException(status_code=503, detail="Robinhood API not configured")

    account = await client.get_account()
    if not account:
        raise HTTPException(status_code=503, detail="Could not retrieve account")

    return CryptoAccountResponse(
        account_id=account.account_id,
        status=account.status,
        buying_power=account.buying_power,
        buying_power_currency=account.buying_power_currency,
        is_active=account.is_active
    )


@router.get("/holdings", response_model=List[CryptoHoldingResponse])
async def get_holdings():
    """Get all crypto holdings"""
    client = get_robinhood_client()

    if not client.is_configured:
        raise HTTPException(status_code=503, detail="Robinhood API not configured")

    holdings = await client.get_holdings()

    return [
        CryptoHoldingResponse(
            asset_code=h.asset_code,
            total_quantity=h.total_quantity,
            available_quantity=h.available_quantity,
            held_for_orders=h.held_for_orders,
            cost_basis=h.cost_basis,
            market_value=h.market_value
        )
        for h in holdings
    ]


# ============================================================
# Crypto Hunter Agent Routes
# ============================================================

@router.get("/hunter/state", response_model=CryptoHunterStateResponse)
async def get_hunter_state():
    """Get current state of the Crypto Hunter agent"""
    service, session = get_crypto_hunter_service_sync()
    try:
        state = await service.get_state()

        return CryptoHunterStateResponse(
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


@router.get("/hunter/watchlist", response_model=List[CryptoWatchlistEntry])
async def get_watchlist():
    """Get current crypto watchlist"""
    service, session = get_crypto_hunter_service_sync()
    try:
        watchlist = await service.get_watchlist()
        return watchlist
    finally:
        session.close()


@router.get("/hunter/positions", response_model=List[CryptoPositionResponse])
async def get_positions():
    """Get current open crypto positions"""
    service, session = get_crypto_hunter_service_sync()
    try:
        positions = await service.get_positions()
        return positions
    finally:
        session.close()


@router.get("/hunter/history", response_model=List[CryptoTradeHistoryEntry])
async def get_trade_history(limit: int = 50):
    """Get crypto trade history"""
    service, session = get_crypto_hunter_service_sync()
    try:
        history = await service.get_trade_history(limit=limit)
        return history
    finally:
        session.close()


@router.post("/hunter/scan", response_model=ScanResponse)
async def trigger_scan(background_tasks: BackgroundTasks):
    """Trigger a manual market scan"""
    service, session = get_crypto_hunter_service_sync()
    try:
        result = await service.manual_scan()
        return result
    finally:
        session.close()


@router.post("/hunter/watchlist/add", response_model=ActionResponse)
async def add_to_watchlist(request: AddSymbolRequest):
    """Manually add a symbol to the watchlist"""
    service, session = get_crypto_hunter_service_sync()
    try:
        result = await service.add_to_watchlist(request.symbol.upper())
        return ActionResponse(
            success=result.get("success", False),
            message=result.get("message", "")
        )
    finally:
        session.close()


@router.post("/hunter/watchlist/{symbol}/remove", response_model=ActionResponse)
async def remove_from_watchlist(symbol: str):
    """Remove a symbol from the watchlist"""
    service, session = get_crypto_hunter_service_sync()
    try:
        result = await service.remove_from_watchlist(symbol.upper())
        return ActionResponse(
            success=result.get("success", False),
            message=result.get("message", "")
        )
    finally:
        session.close()


@router.post("/hunter/positions/{position_id}/close", response_model=ActionResponse)
async def close_position(position_id: int):
    """Manually close a position"""
    service, session = get_crypto_hunter_service_sync()
    try:
        result = await service.close_position(position_id)
        return ActionResponse(
            success=result.get("success", False),
            message=result.get("message", "")
        )
    finally:
        session.close()


@router.get("/hunter/config")
async def get_config():
    """Get current Crypto Hunter configuration"""
    sync_session = SyncSessionLocal()
    try:
        agent = _ensure_crypto_hunter_agent(sync_session)
        return agent.config or {}
    finally:
        sync_session.close()


@router.patch("/hunter/config")
async def update_config(config: dict):
    """Update Crypto Hunter configuration"""
    from sqlalchemy.orm.attributes import flag_modified

    sync_session = SyncSessionLocal()
    try:
        agent = _ensure_crypto_hunter_agent(sync_session)

        # Merge with existing config - create a new dict to ensure SQLAlchemy detects the change
        existing = dict(agent.config or {})
        existing.update(config)
        agent.config = existing

        # Explicitly mark the JSON column as modified
        flag_modified(agent, "config")

        sync_session.commit()
        sync_session.refresh(agent)

        return agent.config
    finally:
        sync_session.close()


# ============================================================
# Market Data Routes
# ============================================================

@router.get("/quotes", response_model=List[CryptoQuoteResponse])
async def get_all_quotes():
    """Get quotes for all tradable crypto pairs"""
    client = get_robinhood_client()

    if not client.is_configured:
        raise HTTPException(status_code=503, detail="Robinhood API not configured")

    # Get tradable pairs
    pairs = await client.get_trading_pairs()
    tradable_symbols = [p.symbol for p in pairs if p.is_tradable]

    # Get quotes in batches
    all_quotes = []
    batch_size = 10

    for i in range(0, len(tradable_symbols), batch_size):
        batch = tradable_symbols[i:i + batch_size]
        quotes = await client.get_quotes(batch)
        all_quotes.extend(quotes)

    return [
        CryptoQuoteResponse(
            symbol=q.symbol,
            bid_price=q.bid_price,
            ask_price=q.ask_price,
            mark_price=q.mark_price,
            high_price=q.high_price,
            low_price=q.low_price,
            open_price=q.open_price,
            volume=q.volume
        )
        for q in all_quotes
    ]


@router.get("/quotes/{symbol}", response_model=CryptoQuoteResponse)
async def get_quote(symbol: str):
    """Get quote for a single crypto pair"""
    client = get_robinhood_client()

    if not client.is_configured:
        raise HTTPException(status_code=503, detail="Robinhood API not configured")

    # Format symbol if needed
    if not symbol.endswith("-USD"):
        symbol = f"{symbol.upper()}-USD"

    quote = await client.get_quote(symbol)
    if not quote:
        raise HTTPException(status_code=404, detail=f"Quote not found for {symbol}")

    return CryptoQuoteResponse(
        symbol=quote.symbol,
        bid_price=quote.bid_price,
        ask_price=quote.ask_price,
        mark_price=quote.mark_price,
        high_price=quote.high_price,
        low_price=quote.low_price,
        open_price=quote.open_price,
        volume=quote.volume
    )


@router.get("/pairs")
async def get_trading_pairs():
    """Get all available trading pairs"""
    client = get_robinhood_client()

    if not client.is_configured:
        raise HTTPException(status_code=503, detail="Robinhood API not configured")

    pairs = await client.get_trading_pairs()

    return [
        {
            "symbol": p.symbol,
            "asset_code": p.asset_code,
            "quote_currency": p.quote_currency,
            "min_order_size": p.min_order_size,
            "max_order_size": p.max_order_size,
            "min_order_price_increment": p.min_order_price_increment,
            "min_order_quantity_increment": p.min_order_quantity_increment,
            "is_tradable": p.is_tradable
        }
        for p in pairs
    ]


# ============================================================
# Order Routes
# ============================================================

@router.get("/orders")
async def get_orders(status: Optional[str] = None, limit: int = 50):
    """Get order history"""
    client = get_robinhood_client()

    if not client.is_configured:
        raise HTTPException(status_code=503, detail="Robinhood API not configured")

    orders = await client.get_orders(status=status, limit=limit)

    return [
        {
            "id": o.id,
            "client_order_id": o.client_order_id,
            "symbol": o.symbol,
            "side": o.side,
            "order_type": o.order_type,
            "quantity": o.quantity,
            "price": o.price,
            "status": o.status,
            "filled_quantity": o.filled_quantity,
            "filled_price": o.filled_price,
            "created_at": o.created_at.isoformat() if o.created_at else None,
            "updated_at": o.updated_at.isoformat() if o.updated_at else None
        }
        for o in orders
    ]


@router.delete("/orders/{order_id}", response_model=ActionResponse)
async def cancel_order(order_id: str):
    """Cancel an open order"""
    client = get_robinhood_client()

    if not client.is_configured:
        raise HTTPException(status_code=503, detail="Robinhood API not configured")

    success = await client.cancel_order(order_id)

    return ActionResponse(
        success=success,
        message="Order cancelled" if success else "Failed to cancel order"
    )


# ============================================================
# Agent Control Routes
# ============================================================

@router.get("/agents")
async def get_crypto_agents():
    """Get all crypto-related agents"""
    sync_session = SyncSessionLocal()
    try:
        agents = sync_session.query(Agent).filter(
            Agent.agent_type.in_(["crypto_hunter", "crypto_orchestrator"])
        ).all()

        return [
            {
                "id": a.id,
                "name": a.name,
                "agent_type": a.agent_type,
                "description": a.description,
                "status": a.status.value if a.status else "unknown",
                "is_active": a.is_active,
                "config": a.config,
                "last_run_at": a.last_run_at.isoformat() if a.last_run_at else None,
                "created_at": a.created_at.isoformat() if a.created_at else None
            }
            for a in agents
        ]
    finally:
        sync_session.close()


@router.post("/agents/{agent_id}/start", response_model=ActionResponse)
async def start_agent(agent_id: int):
    """Start a crypto agent"""
    sync_session = SyncSessionLocal()
    try:
        from app.models.agent import AgentStatus

        agent = sync_session.query(Agent).filter(Agent.id == agent_id).first()

        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")

        if not agent.is_active:
            raise HTTPException(status_code=400, detail="Agent is disabled")

        agent.status = AgentStatus.RUNNING
        sync_session.commit()

        return ActionResponse(success=True, message=f"Agent {agent.name} started")
    finally:
        sync_session.close()


@router.post("/agents/{agent_id}/stop", response_model=ActionResponse)
async def stop_agent(agent_id: int):
    """Stop a crypto agent"""
    sync_session = SyncSessionLocal()
    try:
        from app.models.agent import AgentStatus

        agent = sync_session.query(Agent).filter(Agent.id == agent_id).first()

        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")

        agent.status = AgentStatus.IDLE
        sync_session.commit()

        return ActionResponse(success=True, message=f"Agent {agent.name} stopped")
    finally:
        sync_session.close()


@router.post("/agents/{agent_id}/pause", response_model=ActionResponse)
async def pause_agent(agent_id: int):
    """Pause a crypto agent"""
    sync_session = SyncSessionLocal()
    try:
        from app.models.agent import AgentStatus

        agent = sync_session.query(Agent).filter(Agent.id == agent_id).first()

        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")

        agent.status = AgentStatus.PAUSED
        sync_session.commit()

        return ActionResponse(success=True, message=f"Agent {agent.name} paused")
    finally:
        sync_session.close()


@router.patch("/agents/{agent_id}")
async def update_agent(agent_id: int, data: dict):
    """Update a crypto agent's configuration"""
    from sqlalchemy.orm.attributes import flag_modified

    sync_session = SyncSessionLocal()
    try:
        agent = sync_session.query(Agent).filter(Agent.id == agent_id).first()

        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")

        # Update allowed fields
        if "name" in data:
            agent.name = data["name"]
        if "description" in data:
            agent.description = data["description"]
        if "is_active" in data:
            agent.is_active = data["is_active"]
        if "config" in data:
            # Merge with existing config - create new dict to ensure change detection
            existing_config = dict(agent.config or {})
            existing_config.update(data["config"])
            agent.config = existing_config
            flag_modified(agent, "config")

        sync_session.commit()
        sync_session.refresh(agent)

        return {
            "id": agent.id,
            "name": agent.name,
            "agent_type": agent.agent_type,
            "status": agent.status.value if hasattr(agent.status, 'value') else str(agent.status),
            "is_active": agent.is_active,
            "config": agent.config or {}
        }
    finally:
        sync_session.close()


# ============================================================
# Scheduler Control Routes
# ============================================================

@router.get("/scheduler/status")
async def get_scheduler_info():
    """Get current scheduler status and running jobs"""
    return get_scheduler_status()


@router.post("/scheduler/start", response_model=ActionResponse)
async def start_scheduler_for_crypto():
    """Start the automated crypto trading scheduler"""
    sync_session = SyncSessionLocal()
    try:
        from app.models.agent import AgentStatus

        agent = _ensure_crypto_hunter_agent(sync_session)
        config = agent.config or {}

        # Set agent to RUNNING status
        agent.status = AgentStatus.RUNNING
        sync_session.commit()

        # Start the scheduler with config
        interval = config.get("scan_interval_minutes", 15)
        start_agent_scheduler("crypto_hunter", config)

        return ActionResponse(
            success=True,
            message=f"Crypto hunter scheduler started (interval: {interval} minutes)"
        )
    finally:
        sync_session.close()


@router.post("/scheduler/stop", response_model=ActionResponse)
async def stop_scheduler_for_crypto():
    """Stop the automated crypto trading scheduler"""
    sync_session = SyncSessionLocal()
    try:
        from app.models.agent import AgentStatus

        agent = _ensure_crypto_hunter_agent(sync_session)

        # Set agent to IDLE status
        agent.status = AgentStatus.IDLE
        sync_session.commit()

        # Stop the scheduler
        stopped = stop_agent_scheduler("crypto_hunter")

        return ActionResponse(
            success=True,
            message="Crypto hunter scheduler stopped" if stopped else "Scheduler was not running"
        )
    finally:
        sync_session.close()
