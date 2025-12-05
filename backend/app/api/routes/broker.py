from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

from app.services.broker.ib_client import get_ib_client, IBClient

router = APIRouter()


class SpreadOrderRequest(BaseModel):
    short_strike: float
    long_strike: float
    expiration: str  # YYYYMMDD
    right: str = "P"  # P for puts, C for calls
    quantity: int
    limit_price: float


class ConnectionStatus(BaseModel):
    connected: bool
    host: str
    port: int
    message: str


@router.get("/status", response_model=ConnectionStatus)
async def get_broker_status():
    """Check IB connection status"""
    client = get_ib_client()
    return ConnectionStatus(
        connected=client.is_connected,
        host=client.host,
        port=client.port,
        message="Connected to Interactive Brokers" if client.is_connected else "Not connected"
    )


@router.post("/connect")
async def connect_broker():
    """Connect to Interactive Brokers Gateway/TWS"""
    client = get_ib_client()

    if client.is_connected:
        return {"status": "already_connected"}

    success = await client.connect()
    if success:
        return {"status": "connected"}
    else:
        raise HTTPException(
            status_code=503,
            detail="Failed to connect to IB. Ensure TWS/Gateway is running with API enabled."
        )


@router.post("/disconnect")
async def disconnect_broker():
    """Disconnect from Interactive Brokers"""
    client = get_ib_client()
    await client.disconnect()
    return {"status": "disconnected"}


@router.get("/account")
async def get_account_summary():
    """Get account summary including buying power and P&L"""
    client = get_ib_client()

    if not client.is_connected:
        raise HTTPException(status_code=503, detail="Not connected to IB")

    summary = await client.get_account_summary()
    if not summary:
        raise HTTPException(status_code=500, detail="Failed to get account summary")

    return {
        "account_id": summary.account_id,
        "net_liquidation": summary.net_liquidation,
        "buying_power": summary.buying_power,
        "available_funds": summary.available_funds,
        "excess_liquidity": summary.excess_liquidity,
        "maintenance_margin": summary.maintenance_margin,
        "unrealized_pnl": summary.unrealized_pnl,
        "realized_pnl": summary.realized_pnl
    }


@router.get("/positions")
async def get_positions():
    """Get all current positions"""
    client = get_ib_client()

    if not client.is_connected:
        raise HTTPException(status_code=503, detail="Not connected to IB")

    positions = await client.get_positions()
    return [
        {
            "symbol": p.symbol,
            "contract_type": p.contract_type,
            "quantity": p.quantity,
            "avg_cost": p.avg_cost,
            "market_value": p.market_value,
            "unrealized_pnl": p.unrealized_pnl
        }
        for p in positions
    ]


@router.get("/qqq-price")
async def get_qqq_price():
    """Get current QQQ price"""
    client = get_ib_client()

    if not client.is_connected:
        raise HTTPException(status_code=503, detail="Not connected to IB")

    price = await client.get_qqq_price()
    if price is None:
        raise HTTPException(status_code=500, detail="Failed to get QQQ price")

    return {"symbol": "QQQ", "price": price}


@router.get("/option-chain")
async def get_option_chain(
    symbol: str = "QQQ",
    expiration: Optional[str] = None,
    right: Optional[str] = None
):
    """Get option chain for a symbol"""
    client = get_ib_client()

    if not client.is_connected:
        raise HTTPException(status_code=503, detail="Not connected to IB")

    options = await client.get_option_chain(
        symbol=symbol,
        expiration=expiration,
        right=right
    )

    return [
        {
            "symbol": o.symbol,
            "expiration": o.expiration,
            "strike": o.strike,
            "right": o.right,
            "bid": o.bid,
            "ask": o.ask,
            "last": o.last,
            "volume": o.volume,
            "implied_vol": o.implied_vol,
            "delta": o.delta,
            "gamma": o.gamma,
            "theta": o.theta,
            "vega": o.vega
        }
        for o in options
    ]


@router.get("/find-put-spread")
async def find_put_spread():
    """Find optimal put spread strikes based on strategy parameters"""
    client = get_ib_client()

    if not client.is_connected:
        raise HTTPException(status_code=503, detail="Not connected to IB")

    spread = await client.find_put_spread_strikes()
    if not spread:
        raise HTTPException(
            status_code=404,
            detail="No suitable spread found matching criteria"
        )

    return spread


@router.post("/place-spread")
async def place_spread_order(request: SpreadOrderRequest):
    """Place a vertical spread order"""
    client = get_ib_client()

    if not client.is_connected:
        raise HTTPException(status_code=503, detail="Not connected to IB")

    order_id = await client.place_spread_order(
        short_strike=request.short_strike,
        long_strike=request.long_strike,
        expiration=request.expiration,
        right=request.right,
        quantity=request.quantity,
        limit_price=request.limit_price
    )

    if not order_id:
        raise HTTPException(status_code=500, detail="Failed to place order")

    return {"order_id": order_id, "status": "submitted"}


@router.get("/open-orders")
async def get_open_orders():
    """Get all open orders"""
    client = get_ib_client()

    if not client.is_connected:
        raise HTTPException(status_code=503, detail="Not connected to IB")

    orders = await client.get_open_orders()
    return orders


@router.delete("/orders/{order_id}")
async def cancel_order(order_id: int):
    """Cancel an open order"""
    client = get_ib_client()

    if not client.is_connected:
        raise HTTPException(status_code=503, detail="Not connected to IB")

    success = await client.cancel_order(order_id)
    if not success:
        raise HTTPException(status_code=404, detail="Order not found or already filled")

    return {"order_id": order_id, "status": "cancelled"}
