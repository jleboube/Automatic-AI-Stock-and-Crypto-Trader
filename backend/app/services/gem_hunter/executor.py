"""
Trade Executor for Gem Hunter

Handles order placement and management through Interactive Brokers.
"""

import structlog
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from .analyzer import GemAnalysis
from .risk_manager import PositionSize

logger = structlog.get_logger()


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderStatus(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    FILLED = "filled"
    PARTIAL = "partial"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    ERROR = "error"


@dataclass
class OrderRequest:
    """Request to place an order"""
    symbol: str
    action: str  # "BUY" or "SELL"
    quantity: int
    order_type: OrderType
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    time_in_force: str = "DAY"  # DAY, GTC, IOC

    # For options
    is_option: bool = False
    option_type: Optional[str] = None  # "CALL" or "PUT"
    strike: Optional[float] = None
    expiry: Optional[str] = None  # YYYYMMDD format


@dataclass
class OrderResult:
    """Result from order submission"""
    order_id: Optional[str]
    status: OrderStatus
    filled_quantity: int
    filled_price: float
    message: str
    timestamp: datetime


@dataclass
class Position:
    """Current position information"""
    symbol: str
    quantity: int
    avg_cost: float
    market_value: float
    unrealized_pnl: float
    realized_pnl: float


class TradeExecutor:
    """
    Executes trades through Interactive Brokers.

    Responsibilities:
    - Place entry orders based on analysis
    - Place stop-loss and take-profit orders
    - Monitor and manage open positions
    - Handle order status updates
    """

    def __init__(self, ib_client, config: Dict[str, Any]):
        """
        Initialize executor with IB client.

        Args:
            ib_client: Interactive Brokers client instance
            config: Configuration options
        """
        self.ib_client = ib_client
        self.config = config
        self.use_limit_orders = config.get("use_limit_orders", True)
        self.limit_offset_pct = config.get("limit_offset_pct", 0.001)  # 0.1% offset
        self.bracket_orders = config.get("bracket_orders", True)

    async def execute_entry(
        self,
        analysis: GemAnalysis,
        position_size: PositionSize,
        order_type: OrderType = OrderType.LIMIT
    ) -> OrderResult:
        """
        Execute an entry order based on analysis.

        Args:
            analysis: The gem analysis with entry criteria
            position_size: Calculated position size
            order_type: Type of order to place

        Returns:
            OrderResult with status and fill information
        """
        if position_size.shares <= 0:
            return OrderResult(
                order_id=None,
                status=OrderStatus.REJECTED,
                filled_quantity=0,
                filled_price=0,
                message=position_size.reasoning,
                timestamp=datetime.now()
            )

        # Determine limit price
        limit_price = None
        if order_type == OrderType.LIMIT:
            # Set limit slightly above current price for immediate fill likelihood
            limit_price = analysis.entry_price * (1 + self.limit_offset_pct)

        order_request = OrderRequest(
            symbol=analysis.symbol,
            action="BUY",
            quantity=position_size.shares,
            order_type=order_type,
            limit_price=limit_price,
            time_in_force="DAY"
        )

        logger.info(
            "Executing entry order",
            symbol=analysis.symbol,
            shares=position_size.shares,
            order_type=order_type.value,
            limit_price=limit_price
        )

        # Place the order through IB
        result = await self._place_order(order_request)

        # If bracket orders enabled, place stop-loss and take-profit
        if result.status == OrderStatus.FILLED and self.bracket_orders:
            await self._place_exit_orders(
                symbol=analysis.symbol,
                quantity=result.filled_quantity,
                stop_loss=analysis.stop_loss,
                take_profit=analysis.target_price
            )

        return result

    async def execute_exit(
        self,
        symbol: str,
        quantity: int,
        reason: str,
        order_type: OrderType = OrderType.MARKET
    ) -> OrderResult:
        """
        Execute an exit order.

        Args:
            symbol: Stock symbol
            quantity: Number of shares to sell
            reason: Reason for exit (stop_loss, take_profit, manual, etc.)
            order_type: Type of order

        Returns:
            OrderResult with status and fill information
        """
        order_request = OrderRequest(
            symbol=symbol,
            action="SELL",
            quantity=quantity,
            order_type=order_type,
            time_in_force="DAY"
        )

        logger.info(
            "Executing exit order",
            symbol=symbol,
            quantity=quantity,
            reason=reason,
            order_type=order_type.value
        )

        return await self._place_order(order_request)

    async def _place_order(self, order: OrderRequest) -> OrderResult:
        """
        Place an order through the IB client.

        This is the main interface to Interactive Brokers.
        """
        try:
            # Check if IB client is connected
            if not self.ib_client or not await self._is_connected():
                return OrderResult(
                    order_id=None,
                    status=OrderStatus.ERROR,
                    filled_quantity=0,
                    filled_price=0,
                    message="IB client not connected",
                    timestamp=datetime.now()
                )

            # Create the appropriate contract
            if order.is_option:
                contract = await self._create_option_contract(
                    symbol=order.symbol,
                    option_type=order.option_type,
                    strike=order.strike,
                    expiry=order.expiry
                )
            else:
                contract = await self._create_stock_contract(order.symbol)

            if not contract:
                return OrderResult(
                    order_id=None,
                    status=OrderStatus.ERROR,
                    filled_quantity=0,
                    filled_price=0,
                    message=f"Failed to create contract for {order.symbol}",
                    timestamp=datetime.now()
                )

            # Create the order object
            ib_order = await self._create_ib_order(order)

            # Place the order
            trade = await self.ib_client.place_stock_order(
                symbol=order.symbol,
                action=order.action,
                quantity=order.quantity,
                order_type=order.order_type.value,
                limit_price=order.limit_price,
                stop_price=order.stop_price
            )

            if trade:
                # Wait for fill or timeout
                fill_result = await self._wait_for_fill(trade, timeout=30)
                return fill_result
            else:
                return OrderResult(
                    order_id=None,
                    status=OrderStatus.ERROR,
                    filled_quantity=0,
                    filled_price=0,
                    message="Failed to place order",
                    timestamp=datetime.now()
                )

        except Exception as e:
            logger.error("Order placement failed", error=str(e), symbol=order.symbol)
            return OrderResult(
                order_id=None,
                status=OrderStatus.ERROR,
                filled_quantity=0,
                filled_price=0,
                message=f"Order error: {str(e)}",
                timestamp=datetime.now()
            )

    async def _place_exit_orders(
        self,
        symbol: str,
        quantity: int,
        stop_loss: float,
        take_profit: float
    ):
        """Place bracket exit orders (stop-loss and take-profit)"""
        try:
            # Place stop-loss order
            stop_order = OrderRequest(
                symbol=symbol,
                action="SELL",
                quantity=quantity,
                order_type=OrderType.STOP,
                stop_price=stop_loss,
                time_in_force="GTC"
            )

            # Place take-profit order
            profit_order = OrderRequest(
                symbol=symbol,
                action="SELL",
                quantity=quantity,
                order_type=OrderType.LIMIT,
                limit_price=take_profit,
                time_in_force="GTC"
            )

            # Note: In production, these should be OCO (one-cancels-other) orders
            # For now, we place them as separate orders
            await self._place_order(stop_order)
            await self._place_order(profit_order)

            logger.info(
                "Exit orders placed",
                symbol=symbol,
                stop_loss=stop_loss,
                take_profit=take_profit
            )

        except Exception as e:
            logger.error("Failed to place exit orders", symbol=symbol, error=str(e))

    async def _is_connected(self) -> bool:
        """Check if IB client is connected"""
        try:
            return self.ib_client.is_connected()
        except Exception:
            return False

    async def _create_stock_contract(self, symbol: str):
        """Create a stock contract for the given symbol"""
        try:
            return await self.ib_client.create_stock_contract(symbol)
        except Exception as e:
            logger.error("Failed to create stock contract", symbol=symbol, error=str(e))
            return None

    async def _create_option_contract(
        self,
        symbol: str,
        option_type: str,
        strike: float,
        expiry: str
    ):
        """Create an option contract"""
        try:
            return await self.ib_client.create_option_contract(
                symbol=symbol,
                option_type=option_type,
                strike=strike,
                expiry=expiry
            )
        except Exception as e:
            logger.error("Failed to create option contract", symbol=symbol, error=str(e))
            return None

    async def _create_ib_order(self, order: OrderRequest):
        """Create an IB order object from our order request"""
        # This will be implemented based on the IB client interface
        pass

    async def _wait_for_fill(self, trade, timeout: int = 30) -> OrderResult:
        """
        Wait for an order to be filled.

        Args:
            trade: The IB trade object
            timeout: Maximum seconds to wait

        Returns:
            OrderResult with fill information
        """
        import asyncio

        start_time = datetime.now()

        while (datetime.now() - start_time).seconds < timeout:
            # Check order status
            status = await self._get_order_status(trade)

            if status in [OrderStatus.FILLED, OrderStatus.PARTIAL]:
                fill_info = await self._get_fill_info(trade)
                return OrderResult(
                    order_id=str(trade.order.orderId) if hasattr(trade, 'order') else None,
                    status=status,
                    filled_quantity=fill_info.get("quantity", 0),
                    filled_price=fill_info.get("price", 0),
                    message="Order filled",
                    timestamp=datetime.now()
                )

            if status in [OrderStatus.CANCELLED, OrderStatus.REJECTED]:
                return OrderResult(
                    order_id=str(trade.order.orderId) if hasattr(trade, 'order') else None,
                    status=status,
                    filled_quantity=0,
                    filled_price=0,
                    message=f"Order {status.value}",
                    timestamp=datetime.now()
                )

            await asyncio.sleep(0.5)

        # Timeout - order still pending
        return OrderResult(
            order_id=str(trade.order.orderId) if hasattr(trade, 'order') else None,
            status=OrderStatus.PENDING,
            filled_quantity=0,
            filled_price=0,
            message="Order pending (timeout waiting for fill)",
            timestamp=datetime.now()
        )

    async def _get_order_status(self, trade) -> OrderStatus:
        """Get the current status of an order"""
        try:
            status = trade.orderStatus.status if hasattr(trade, 'orderStatus') else None

            status_map = {
                'Filled': OrderStatus.FILLED,
                'Submitted': OrderStatus.SUBMITTED,
                'PreSubmitted': OrderStatus.SUBMITTED,
                'Cancelled': OrderStatus.CANCELLED,
                'Inactive': OrderStatus.REJECTED,
                'PendingSubmit': OrderStatus.PENDING,
                'PendingCancel': OrderStatus.PENDING,
            }

            return status_map.get(status, OrderStatus.PENDING)
        except Exception:
            return OrderStatus.PENDING

    async def _get_fill_info(self, trade) -> Dict[str, Any]:
        """Get fill information from a trade"""
        try:
            if hasattr(trade, 'fills') and trade.fills:
                total_qty = sum(f.execution.shares for f in trade.fills)
                avg_price = sum(f.execution.shares * f.execution.price for f in trade.fills) / total_qty
                return {"quantity": int(total_qty), "price": avg_price}
            return {"quantity": 0, "price": 0}
        except Exception:
            return {"quantity": 0, "price": 0}

    async def get_position(self, symbol: str) -> Optional[Position]:
        """Get current position for a symbol"""
        try:
            positions = await self.ib_client.get_positions()
            for pos in positions:
                if pos.contract.symbol == symbol:
                    return Position(
                        symbol=symbol,
                        quantity=int(pos.position),
                        avg_cost=pos.avgCost,
                        market_value=pos.marketValue if hasattr(pos, 'marketValue') else 0,
                        unrealized_pnl=pos.unrealizedPNL if hasattr(pos, 'unrealizedPNL') else 0,
                        realized_pnl=pos.realizedPNL if hasattr(pos, 'realizedPNL') else 0
                    )
            return None
        except Exception as e:
            logger.error("Failed to get position", symbol=symbol, error=str(e))
            return None

    async def get_all_positions(self) -> List[Position]:
        """Get all current positions"""
        try:
            positions = await self.ib_client.get_positions()
            return [
                Position(
                    symbol=pos.contract.symbol,
                    quantity=int(pos.position),
                    avg_cost=pos.avgCost,
                    market_value=pos.marketValue if hasattr(pos, 'marketValue') else 0,
                    unrealized_pnl=pos.unrealizedPNL if hasattr(pos, 'unrealizedPNL') else 0,
                    realized_pnl=pos.realizedPNL if hasattr(pos, 'realizedPNL') else 0
                )
                for pos in positions
                if pos.position != 0
            ]
        except Exception as e:
            logger.error("Failed to get positions", error=str(e))
            return []

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order"""
        try:
            await self.ib_client.cancel_order(order_id)
            logger.info("Order cancelled", order_id=order_id)
            return True
        except Exception as e:
            logger.error("Failed to cancel order", order_id=order_id, error=str(e))
            return False

    async def cancel_all_orders(self, symbol: Optional[str] = None) -> int:
        """
        Cancel all open orders, optionally filtered by symbol.

        Returns the number of orders cancelled.
        """
        try:
            cancelled = await self.ib_client.cancel_all_orders(symbol)
            logger.info("Orders cancelled", count=cancelled, symbol=symbol)
            return cancelled
        except Exception as e:
            logger.error("Failed to cancel orders", symbol=symbol, error=str(e))
            return 0
