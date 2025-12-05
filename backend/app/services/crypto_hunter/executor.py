"""
Trade Executor for Crypto Hunter

Executes crypto trades via Robinhood API.
Handles order placement, monitoring, and management.
"""

import structlog
import asyncio
import math
from decimal import Decimal, ROUND_DOWN
from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from app.services.broker.robinhood_client import RobinhoodCryptoClient, CryptoOrder, TradingPair

logger = structlog.get_logger()


class CryptoOrderStatus(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    FAILED = "failed"


@dataclass
class CryptoOrderResult:
    """Result of a crypto order execution"""
    symbol: str
    side: str  # "buy" or "sell"
    order_type: str  # "market" or "limit"
    requested_quantity: float
    filled_quantity: float
    filled_price: Optional[float]
    status: CryptoOrderStatus
    order_id: Optional[str]
    message: str
    timestamp: datetime


# Stablecoins that don't support limit orders or shouldn't be traded
EXCLUDED_SYMBOLS = {"USDC-USD", "USDT-USD", "DAI-USD", "BUSD-USD", "TUSD-USD"}


class CryptoExecutor:
    """
    Executes crypto trades via Robinhood.

    Features:
    - Market and limit order support
    - Order monitoring and status tracking
    - Automatic retry logic
    - Slippage protection via limit orders
    - Price precision handling per trading pair
    """

    # Class-level cache for trading pair info
    _trading_pairs_cache: Dict[str, TradingPair] = {}
    _cache_loaded: bool = False

    def __init__(
        self,
        robinhood_client: RobinhoodCryptoClient,
        config: Dict[str, Any]
    ):
        """
        Initialize executor.

        Config options:
        - use_limit_orders: Use limit orders instead of market (default: True)
        - limit_offset_pct: Offset for limit price from current (default: 0.002)
        - order_timeout_seconds: Timeout waiting for fill (default: 120)
        - max_slippage_pct: Maximum allowed slippage (default: 0.01)
        """
        self.client = robinhood_client
        self.config = config

        # Default to market orders for faster execution
        # Limit orders often timeout without filling in crypto markets
        self.use_limit_orders = config.get("use_limit_orders", False)
        self.limit_offset_pct = config.get("limit_offset_pct", 0.005)  # 0.5% buffer if limit orders are used
        self.order_timeout_seconds = config.get("order_timeout_seconds", 60)  # 60 second timeout
        self.max_slippage_pct = config.get("max_slippage_pct", 0.01)

    async def _ensure_trading_pairs_cached(self):
        """Ensure trading pairs are cached for precision lookups"""
        if not CryptoExecutor._cache_loaded:
            pairs = await self.client.get_trading_pairs()
            for pair in pairs:
                CryptoExecutor._trading_pairs_cache[pair.symbol] = pair
            CryptoExecutor._cache_loaded = True
            logger.debug("Cached trading pair info", count=len(pairs))

    def _get_price_precision(self, symbol: str) -> float:
        """Get the minimum price increment for a symbol"""
        pair = CryptoExecutor._trading_pairs_cache.get(symbol)
        if pair:
            return pair.min_order_price_increment
        # Default to 0.01 if not found
        return 0.01

    def _get_quantity_precision(self, symbol: str) -> float:
        """Get the minimum quantity increment for a symbol"""
        pair = CryptoExecutor._trading_pairs_cache.get(symbol)
        if pair:
            return pair.min_order_quantity_increment
        # Default to 0.00001 if not found
        return 0.00001

    def _round_to_precision(self, value: float, precision: float) -> float:
        """Round a value to the given precision using Decimal for accuracy"""
        if precision <= 0:
            return value
        # Use Decimal to avoid floating point artifacts
        d_value = Decimal(str(value))
        d_precision = Decimal(str(precision))
        # Calculate decimal places from precision for proper quantization
        decimal_places = max(0, -int(math.floor(math.log10(precision))))
        # Create quantize format string (e.g., "0.01" for precision 0.01)
        quantize_str = f"0.{'0' * decimal_places}" if decimal_places > 0 else "1"
        # Round down to avoid exceeding available funds
        result = d_value.quantize(Decimal(quantize_str), rounding=ROUND_DOWN)
        return float(result)

    def _is_excluded_symbol(self, symbol: str) -> bool:
        """Check if symbol is excluded from trading (stablecoins, etc.)"""
        return symbol in EXCLUDED_SYMBOLS

    async def execute_entry(
        self,
        symbol: str,
        quantity: float,
        current_price: float,
        limit_price: Optional[float] = None
    ) -> CryptoOrderResult:
        """
        Execute a buy order to enter a position.

        Args:
            symbol: Trading pair symbol (e.g., "BTC-USD")
            quantity: Amount to buy
            current_price: Current market price (for limit calculation)
            limit_price: Optional explicit limit price

        Returns:
            CryptoOrderResult with execution details
        """
        logger.info(
            "Executing crypto entry",
            symbol=symbol,
            quantity=quantity,
            current_price=current_price
        )

        try:
            # Check if symbol is excluded (stablecoins, etc.)
            if self._is_excluded_symbol(symbol):
                return CryptoOrderResult(
                    symbol=symbol,
                    side="buy",
                    order_type="limit",
                    requested_quantity=quantity,
                    filled_quantity=0,
                    filled_price=None,
                    status=CryptoOrderStatus.REJECTED,
                    order_id=None,
                    message=f"Symbol {symbol} is excluded from trading (stablecoin)",
                    timestamp=datetime.now()
                )

            # Ensure trading pairs are cached for precision lookups
            await self._ensure_trading_pairs_cached()

            # Check if client is configured
            if not self.client.is_configured:
                return CryptoOrderResult(
                    symbol=symbol,
                    side="buy",
                    order_type="limit" if self.use_limit_orders else "market",
                    requested_quantity=quantity,
                    filled_quantity=0,
                    filled_price=None,
                    status=CryptoOrderStatus.FAILED,
                    order_id=None,
                    message="Robinhood client not configured",
                    timestamp=datetime.now()
                )

            # Get precision for this symbol
            price_precision = self._get_price_precision(symbol)
            quantity_precision = self._get_quantity_precision(symbol)

            # Round quantity to proper precision
            rounded_quantity = self._round_to_precision(quantity, quantity_precision)
            if rounded_quantity <= 0:
                return CryptoOrderResult(
                    symbol=symbol,
                    side="buy",
                    order_type="limit" if self.use_limit_orders else "market",
                    requested_quantity=quantity,
                    filled_quantity=0,
                    filled_price=None,
                    status=CryptoOrderStatus.REJECTED,
                    order_id=None,
                    message=f"Quantity {quantity} rounds to zero with precision {quantity_precision}",
                    timestamp=datetime.now()
                )

            # Calculate limit price if using limit orders
            if self.use_limit_orders:
                if limit_price is None:
                    # Add small buffer above current price for buy orders
                    limit_price = current_price * (1 + self.limit_offset_pct)
                # Round limit price to proper precision
                limit_price = self._round_to_precision(limit_price, price_precision)
                order_type = "limit"
            else:
                order_type = "market"
                limit_price = None

            logger.debug(
                "Placing order with precision",
                symbol=symbol,
                original_quantity=quantity,
                rounded_quantity=rounded_quantity,
                limit_price=limit_price,
                price_precision=price_precision,
                quantity_precision=quantity_precision
            )

            # Place the order
            order = await self.client.place_order(
                symbol=symbol,
                side="buy",
                order_type=order_type,
                quantity=rounded_quantity,
                limit_price=limit_price
            )

            if not order:
                return CryptoOrderResult(
                    symbol=symbol,
                    side="buy",
                    order_type=order_type,
                    requested_quantity=quantity,
                    filled_quantity=0,
                    filled_price=None,
                    status=CryptoOrderStatus.FAILED,
                    order_id=None,
                    message="Failed to place order",
                    timestamp=datetime.now()
                )

            # Wait for fill (with timeout)
            filled_order = await self._wait_for_fill(order.id)

            if filled_order and filled_order.status == "filled":
                return CryptoOrderResult(
                    symbol=symbol,
                    side="buy",
                    order_type=order_type,
                    requested_quantity=quantity,
                    filled_quantity=filled_order.filled_quantity,
                    filled_price=filled_order.filled_price,
                    status=CryptoOrderStatus.FILLED,
                    order_id=filled_order.id,
                    message="Order filled successfully",
                    timestamp=datetime.now()
                )
            elif filled_order and filled_order.filled_quantity > 0:
                return CryptoOrderResult(
                    symbol=symbol,
                    side="buy",
                    order_type=order_type,
                    requested_quantity=quantity,
                    filled_quantity=filled_order.filled_quantity,
                    filled_price=filled_order.filled_price,
                    status=CryptoOrderStatus.PARTIALLY_FILLED,
                    order_id=filled_order.id,
                    message=f"Partial fill: {filled_order.filled_quantity}/{quantity}",
                    timestamp=datetime.now()
                )
            else:
                # Cancel unfilled order
                if order.id:
                    await self.client.cancel_order(order.id)

                return CryptoOrderResult(
                    symbol=symbol,
                    side="buy",
                    order_type=order_type,
                    requested_quantity=quantity,
                    filled_quantity=0,
                    filled_price=None,
                    status=CryptoOrderStatus.CANCELLED,
                    order_id=order.id,
                    message="Order timed out, cancelled",
                    timestamp=datetime.now()
                )

        except Exception as e:
            logger.error("Crypto entry execution failed", symbol=symbol, error=str(e))
            return CryptoOrderResult(
                symbol=symbol,
                side="buy",
                order_type="unknown",
                requested_quantity=quantity,
                filled_quantity=0,
                filled_price=None,
                status=CryptoOrderStatus.FAILED,
                order_id=None,
                message=f"Execution error: {str(e)}",
                timestamp=datetime.now()
            )

    async def execute_exit(
        self,
        symbol: str,
        quantity: float,
        current_price: Optional[float] = None,
        reason: str = "manual"
    ) -> CryptoOrderResult:
        """
        Execute a sell order to exit a position.

        Args:
            symbol: Trading pair symbol
            quantity: Amount to sell
            current_price: Current market price (optional)
            reason: Reason for exit (stop_loss, take_profit, manual, etc.)

        Returns:
            CryptoOrderResult with execution details
        """
        logger.info(
            "Executing crypto exit",
            symbol=symbol,
            quantity=quantity,
            reason=reason
        )

        try:
            # Ensure trading pairs are cached for precision lookups
            await self._ensure_trading_pairs_cached()

            if not self.client.is_configured:
                return CryptoOrderResult(
                    symbol=symbol,
                    side="sell",
                    order_type="market",
                    requested_quantity=quantity,
                    filled_quantity=0,
                    filled_price=None,
                    status=CryptoOrderStatus.FAILED,
                    order_id=None,
                    message="Robinhood client not configured",
                    timestamp=datetime.now()
                )

            # Get precision for this symbol
            price_precision = self._get_price_precision(symbol)
            quantity_precision = self._get_quantity_precision(symbol)

            # Round quantity to proper precision
            rounded_quantity = self._round_to_precision(quantity, quantity_precision)
            if rounded_quantity <= 0:
                return CryptoOrderResult(
                    symbol=symbol,
                    side="sell",
                    order_type="market",
                    requested_quantity=quantity,
                    filled_quantity=0,
                    filled_price=None,
                    status=CryptoOrderStatus.REJECTED,
                    order_id=None,
                    message=f"Quantity {quantity} rounds to zero with precision {quantity_precision}",
                    timestamp=datetime.now()
                )

            # For exits, prefer market orders for speed
            # Especially for stop losses
            if reason == "stop_loss":
                order_type = "market"
                limit_price = None
            elif self.use_limit_orders and current_price:
                order_type = "limit"
                # Small buffer below current price for sell orders
                limit_price = current_price * (1 - self.limit_offset_pct)
                # Round limit price to proper precision
                limit_price = self._round_to_precision(limit_price, price_precision)
            else:
                order_type = "market"
                limit_price = None

            logger.debug(
                "Placing exit order with precision",
                symbol=symbol,
                original_quantity=quantity,
                rounded_quantity=rounded_quantity,
                limit_price=limit_price,
                reason=reason
            )

            # Place the order
            order = await self.client.place_order(
                symbol=symbol,
                side="sell",
                order_type=order_type,
                quantity=rounded_quantity,
                limit_price=limit_price
            )

            if not order:
                return CryptoOrderResult(
                    symbol=symbol,
                    side="sell",
                    order_type=order_type,
                    requested_quantity=quantity,
                    filled_quantity=0,
                    filled_price=None,
                    status=CryptoOrderStatus.FAILED,
                    order_id=None,
                    message="Failed to place exit order",
                    timestamp=datetime.now()
                )

            # Wait for fill
            filled_order = await self._wait_for_fill(order.id)

            if filled_order and filled_order.status == "filled":
                return CryptoOrderResult(
                    symbol=symbol,
                    side="sell",
                    order_type=order_type,
                    requested_quantity=quantity,
                    filled_quantity=filled_order.filled_quantity,
                    filled_price=filled_order.filled_price,
                    status=CryptoOrderStatus.FILLED,
                    order_id=filled_order.id,
                    message=f"Exit order filled ({reason})",
                    timestamp=datetime.now()
                )
            else:
                # For exits, try market order if limit times out
                if order_type == "limit" and order.id:
                    await self.client.cancel_order(order.id)

                    # Retry with market order (use rounded quantity)
                    market_order = await self.client.place_order(
                        symbol=symbol,
                        side="sell",
                        order_type="market",
                        quantity=rounded_quantity
                    )

                    if market_order:
                        filled = await self._wait_for_fill(market_order.id)
                        if filled and filled.status == "filled":
                            return CryptoOrderResult(
                                symbol=symbol,
                                side="sell",
                                order_type="market",
                                requested_quantity=quantity,
                                filled_quantity=filled.filled_quantity,
                                filled_price=filled.filled_price,
                                status=CryptoOrderStatus.FILLED,
                                order_id=filled.id,
                                message=f"Exit filled at market ({reason})",
                                timestamp=datetime.now()
                            )

                return CryptoOrderResult(
                    symbol=symbol,
                    side="sell",
                    order_type=order_type,
                    requested_quantity=quantity,
                    filled_quantity=filled_order.filled_quantity if filled_order else 0,
                    filled_price=filled_order.filled_price if filled_order else None,
                    status=CryptoOrderStatus.PARTIALLY_FILLED if filled_order and filled_order.filled_quantity > 0 else CryptoOrderStatus.FAILED,
                    order_id=order.id,
                    message="Exit order not fully filled",
                    timestamp=datetime.now()
                )

        except Exception as e:
            logger.error("Crypto exit execution failed", symbol=symbol, error=str(e))
            return CryptoOrderResult(
                symbol=symbol,
                side="sell",
                order_type="unknown",
                requested_quantity=quantity,
                filled_quantity=0,
                filled_price=None,
                status=CryptoOrderStatus.FAILED,
                order_id=None,
                message=f"Exit error: {str(e)}",
                timestamp=datetime.now()
            )

    async def _wait_for_fill(
        self,
        order_id: str,
        timeout_seconds: Optional[int] = None
    ) -> Optional[CryptoOrder]:
        """
        Wait for an order to fill.

        Args:
            order_id: Order ID to monitor
            timeout_seconds: Timeout in seconds (default from config)

        Returns:
            Updated CryptoOrder or None if timeout
        """
        timeout = timeout_seconds or self.order_timeout_seconds
        interval = 2  # Check every 2 seconds
        elapsed = 0

        while elapsed < timeout:
            try:
                order = await self.client.get_order(order_id)

                if order:
                    if order.status in ["filled", "canceled", "failed", "rejected"]:
                        return order

                    if order.filled_quantity > 0:
                        # Partial fill - continue waiting
                        logger.debug(
                            "Partial fill",
                            order_id=order_id,
                            filled=order.filled_quantity,
                            total=order.quantity
                        )

                await asyncio.sleep(interval)
                elapsed += interval

            except Exception as e:
                logger.warning("Error checking order status", order_id=order_id, error=str(e))
                await asyncio.sleep(interval)
                elapsed += interval

        # Timeout - get final status
        try:
            return await self.client.get_order(order_id)
        except:
            return None

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order"""
        try:
            return await self.client.cancel_order(order_id)
        except Exception as e:
            logger.error("Failed to cancel order", order_id=order_id, error=str(e))
            return False

    async def get_order_status(self, order_id: str) -> Optional[CryptoOrder]:
        """Get current status of an order"""
        try:
            return await self.client.get_order(order_id)
        except Exception as e:
            logger.error("Failed to get order status", order_id=order_id, error=str(e))
            return None
