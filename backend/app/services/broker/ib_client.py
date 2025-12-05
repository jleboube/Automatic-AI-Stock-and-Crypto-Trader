"""
Interactive Brokers Client Integration

Uses ib_insync for async-friendly IB API access.
Requires IB Gateway or TWS running with API enabled.
"""

import asyncio
import structlog
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from dataclasses import dataclass

try:
    from ib_insync import IB, Stock, Option, Contract, Order, LimitOrder, MarketOrder, ComboLeg
    from ib_insync import util
    IB_AVAILABLE = True
except ImportError:
    IB_AVAILABLE = False

from app.core.config import settings

logger = structlog.get_logger()


@dataclass
class OptionQuote:
    symbol: str
    expiration: str
    strike: float
    right: str  # 'C' or 'P'
    bid: float
    ask: float
    last: float
    volume: int
    open_interest: int
    implied_vol: float
    delta: float
    gamma: float
    theta: float
    vega: float


@dataclass
class Position:
    symbol: str
    contract_type: str
    quantity: int
    avg_cost: float
    market_value: float
    unrealized_pnl: float
    realized_pnl: float


@dataclass
class AccountSummary:
    account_id: str
    net_liquidation: float
    buying_power: float
    available_funds: float
    excess_liquidity: float
    maintenance_margin: float
    unrealized_pnl: float
    realized_pnl: float


class IBClient:
    """
    Interactive Brokers API client for options trading.

    Requires:
    - IB Gateway or TWS running
    - API connections enabled (Edit > Global Configuration > API > Settings)
    - Socket port configured (default: 7497 for TWS paper, 7496 for live)
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 7497,  # 7497 = TWS paper, 7496 = TWS live, 4001 = Gateway paper, 4002 = Gateway live
        client_id: int = 1,
        readonly: bool = False
    ):
        if not IB_AVAILABLE:
            raise ImportError("ib_insync is not installed. Run: pip install ib_insync")

        self.host = host
        self.port = port
        self.client_id = client_id
        self.readonly = readonly
        self.ib: Optional[IB] = None
        self._connected = False

    async def connect(self) -> bool:
        """Connect to IB Gateway/TWS"""
        try:
            self.ib = IB()
            await self.ib.connectAsync(
                host=self.host,
                port=self.port,
                clientId=self.client_id,
                readonly=self.readonly
            )
            self._connected = True

            # Request delayed market data (type 3) if live data subscription not available
            # Type 1 = Live, Type 2 = Frozen, Type 3 = Delayed, Type 4 = Delayed-Frozen
            self.ib.reqMarketDataType(3)
            logger.info("Connected to Interactive Brokers (using delayed market data)", host=self.host, port=self.port)
            return True
        except Exception as e:
            logger.error("Failed to connect to IB", error=str(e))
            self._connected = False
            return False

    async def disconnect(self):
        """Disconnect from IB"""
        if self.ib and self._connected:
            self.ib.disconnect()
            self._connected = False
            logger.info("Disconnected from Interactive Brokers")

    @property
    def is_connected(self) -> bool:
        return self._connected and self.ib and self.ib.isConnected()

    async def get_account_summary(self) -> Optional[AccountSummary]:
        """Get account summary including buying power and P&L"""
        if not self.is_connected:
            return None

        try:
            account_values = self.ib.accountSummary()

            values = {}
            for av in account_values:
                values[av.tag] = float(av.value) if av.value else 0.0

            return AccountSummary(
                account_id=settings.BROKER_ACCOUNT_ID or "default",
                net_liquidation=values.get("NetLiquidation", 0),
                buying_power=values.get("BuyingPower", 0),
                available_funds=values.get("AvailableFunds", 0),
                excess_liquidity=values.get("ExcessLiquidity", 0),
                maintenance_margin=values.get("MaintMarginReq", 0),
                unrealized_pnl=values.get("UnrealizedPnL", 0),
                realized_pnl=values.get("RealizedPnL", 0)
            )
        except Exception as e:
            logger.error("Failed to get account summary", error=str(e))
            return None

    async def get_positions(self) -> List[Position]:
        """Get all current positions"""
        if not self.is_connected:
            return []

        try:
            positions = self.ib.positions()
            result = []

            for pos in positions:
                contract = pos.contract
                result.append(Position(
                    symbol=contract.symbol,
                    contract_type=contract.secType,
                    quantity=int(pos.position),
                    avg_cost=pos.avgCost,
                    market_value=0,  # Need to request market data
                    unrealized_pnl=0,
                    realized_pnl=0
                ))

            return result
        except Exception as e:
            logger.error("Failed to get positions", error=str(e))
            return []

    async def get_qqq_price(self) -> Optional[float]:
        """Get current QQQ price"""
        if not self.is_connected:
            return None

        try:
            contract = Stock("QQQ", "SMART", "USD")

            # Use qualifyContractsAsync for async compatibility
            await self.ib.qualifyContractsAsync(contract)

            # Request market data
            ticker = self.ib.reqMktData(contract, "", False, False)

            # Wait for data with timeout (5 seconds for delayed data)
            price = None
            for _ in range(50):  # 5 second timeout (50 * 0.1s)
                await asyncio.sleep(0.1)
                # Try marketPrice first (uses last, then close, then bid/ask midpoint)
                mp = ticker.marketPrice()
                if mp and mp > 0 and not (mp != mp):  # Check for NaN
                    price = mp
                    break
                # Also check if we have bid/ask
                if ticker.bid and ticker.ask and ticker.bid > 0 and ticker.ask > 0:
                    price = (ticker.bid + ticker.ask) / 2
                    break
                # Check last price
                if ticker.last and ticker.last > 0:
                    price = ticker.last
                    break
                # Check close price (for delayed/frozen data)
                if ticker.close and ticker.close > 0:
                    price = ticker.close
                    break

            self.ib.cancelMktData(contract)

            if price and price > 0:
                logger.info("Got QQQ price from IB", price=price)
                return price
            else:
                logger.warning("Could not get valid QQQ price from IB", ticker_data={
                    "bid": ticker.bid,
                    "ask": ticker.ask,
                    "last": ticker.last,
                    "close": ticker.close
                })
                return None
        except Exception as e:
            logger.error("Failed to get QQQ price", error=str(e))
            return None

    async def get_option_chain(
        self,
        symbol: str = "QQQ",
        expiration: str = None,  # Format: YYYYMMDD
        strikes: List[float] = None,
        right: str = None  # 'C' or 'P'
    ) -> List[OptionQuote]:
        """
        Get option chain for a symbol.

        Args:
            symbol: Underlying symbol (default: QQQ)
            expiration: Expiration date in YYYYMMDD format
            strikes: List of strike prices to filter
            right: 'C' for calls, 'P' for puts
        """
        if not self.is_connected:
            return []

        try:
            underlying = Stock(symbol, "SMART", "USD")
            await self.ib.qualifyContractsAsync(underlying)

            # Get option chain parameters
            chains = await self.ib.reqSecDefOptParamsAsync(
                underlying.symbol,
                "",
                underlying.secType,
                underlying.conId
            )

            if not chains:
                return []

            # Use SMART exchange
            chain = next((c for c in chains if c.exchange == "SMART"), chains[0])

            # Build option contracts
            options = []
            expirations = [expiration] if expiration else list(chain.expirations)[:4]  # Next 4 expirations
            target_strikes = strikes if strikes else list(chain.strikes)
            rights = [right] if right else ["P", "C"]

            for exp in expirations:
                for strike in target_strikes:
                    for r in rights:
                        opt = Option(symbol, exp, strike, r, "SMART")
                        options.append(opt)

            # Qualify contracts (limit to avoid overload)
            qualified = await self.ib.qualifyContractsAsync(*options[:50])

            # Request market data
            quotes = []
            for opt in qualified:
                ticker = self.ib.reqMktData(opt, "100,101,104,106", False, False)
                await asyncio.sleep(0.2)  # Wait for data

                quotes.append(OptionQuote(
                    symbol=opt.symbol,
                    expiration=opt.lastTradeDateOrContractMonth,
                    strike=opt.strike,
                    right=opt.right,
                    bid=ticker.bid or 0,
                    ask=ticker.ask or 0,
                    last=ticker.last or 0,
                    volume=ticker.volume or 0,
                    open_interest=0,
                    implied_vol=ticker.modelGreeks.impliedVol if ticker.modelGreeks else 0,
                    delta=ticker.modelGreeks.delta if ticker.modelGreeks else 0,
                    gamma=ticker.modelGreeks.gamma if ticker.modelGreeks else 0,
                    theta=ticker.modelGreeks.theta if ticker.modelGreeks else 0,
                    vega=ticker.modelGreeks.vega if ticker.modelGreeks else 0
                ))

                self.ib.cancelMktData(opt)

            return quotes
        except Exception as e:
            logger.error("Failed to get option chain", error=str(e))
            return []

    async def find_put_spread_strikes(
        self,
        target_credit_min: float = 0.55,
        target_credit_max: float = 0.70,
        spread_width: int = 25,
        max_delta: float = 0.12
    ) -> Optional[Dict[str, Any]]:
        """
        Find optimal put spread strikes based on target credit and delta.

        Returns strikes for the weekly 25-wide put credit spread.
        """
        if not self.is_connected:
            return None

        try:
            qqq_price = await self.get_qqq_price()
            if not qqq_price:
                return None

            # Get Friday expiration (next weekly)
            today = datetime.now()
            days_until_friday = (4 - today.weekday()) % 7
            if days_until_friday == 0 and today.hour >= 16:
                days_until_friday = 7
            expiration_date = today + timedelta(days=days_until_friday)
            expiration = expiration_date.strftime("%Y%m%d")

            # Generate strike range (below current price)
            strikes = [round(qqq_price - i, 0) for i in range(5, 50, 1)]

            # Get put options
            puts = await self.get_option_chain(
                symbol="QQQ",
                expiration=expiration,
                strikes=strikes,
                right="P"
            )

            # Find short put with target credit and delta
            for put in sorted(puts, key=lambda x: x.strike, reverse=True):
                mid_price = (put.bid + put.ask) / 2
                if (target_credit_min <= mid_price <= target_credit_max and
                    abs(put.delta) <= max_delta):

                    short_strike = put.strike
                    long_strike = short_strike - spread_width

                    # Find long put
                    long_put = next(
                        (p for p in puts if p.strike == long_strike),
                        None
                    )

                    if long_put:
                        long_mid = (long_put.bid + long_put.ask) / 2
                        net_credit = mid_price - long_mid
                        max_risk = (spread_width - net_credit) * 100

                        return {
                            "short_strike": short_strike,
                            "long_strike": long_strike,
                            "short_premium": mid_price,
                            "long_premium": long_mid,
                            "net_credit": net_credit,
                            "max_risk": max_risk,
                            "short_delta": put.delta,
                            "expiration": expiration,
                            "qqq_price": qqq_price
                        }

            return None
        except Exception as e:
            logger.error("Failed to find put spread strikes", error=str(e))
            return None

    async def place_spread_order(
        self,
        short_strike: float,
        long_strike: float,
        expiration: str,
        right: str,  # 'P' for puts, 'C' for calls
        quantity: int,
        limit_price: float
    ) -> Optional[str]:
        """
        Place a vertical spread order.

        Returns order ID if successful.
        """
        if not self.is_connected or self.readonly:
            logger.warning("Cannot place order: not connected or readonly mode")
            return None

        try:
            # Create option contracts
            short_opt = Option("QQQ", expiration, short_strike, right, "SMART")
            long_opt = Option("QQQ", expiration, long_strike, right, "SMART")

            await self.ib.qualifyContractsAsync(short_opt, long_opt)

            # Create combo contract for spread
            combo = Contract()
            combo.symbol = "QQQ"
            combo.secType = "BAG"
            combo.currency = "USD"
            combo.exchange = "SMART"

            leg1 = ComboLeg()
            leg1.conId = short_opt.conId
            leg1.ratio = 1
            leg1.action = "SELL"
            leg1.exchange = "SMART"

            leg2 = ComboLeg()
            leg2.conId = long_opt.conId
            leg2.ratio = 1
            leg2.action = "BUY"
            leg2.exchange = "SMART"

            combo.comboLegs = [leg1, leg2]

            # Create limit order
            order = LimitOrder(
                action="BUY",  # BUY to open credit spread
                totalQuantity=quantity,
                lmtPrice=limit_price
            )

            # Place order
            trade = self.ib.placeOrder(combo, order)

            logger.info(
                "Placed spread order",
                short_strike=short_strike,
                long_strike=long_strike,
                quantity=quantity,
                limit_price=limit_price,
                order_id=trade.order.orderId
            )

            return str(trade.order.orderId)
        except Exception as e:
            logger.error("Failed to place spread order", error=str(e))
            return None

    async def close_position(self, contract: Contract, quantity: int) -> Optional[str]:
        """Close a position at market"""
        if not self.is_connected or self.readonly:
            return None

        try:
            order = MarketOrder(
                action="SELL" if quantity > 0 else "BUY",
                totalQuantity=abs(quantity)
            )
            trade = self.ib.placeOrder(contract, order)
            return str(trade.order.orderId)
        except Exception as e:
            logger.error("Failed to close position", error=str(e))
            return None

    async def get_open_orders(self) -> List[Dict[str, Any]]:
        """Get all open orders"""
        if not self.is_connected:
            return []

        try:
            orders = self.ib.openOrders()
            return [
                {
                    "order_id": o.orderId,
                    "symbol": o.contract.symbol if hasattr(o, 'contract') else "",
                    "action": o.action,
                    "quantity": o.totalQuantity,
                    "order_type": o.orderType,
                    "limit_price": o.lmtPrice if hasattr(o, 'lmtPrice') else None,
                    "status": o.status if hasattr(o, 'status') else "unknown"
                }
                for o in orders
            ]
        except Exception as e:
            logger.error("Failed to get open orders", error=str(e))
            return []

    async def cancel_order(self, order_id: int) -> bool:
        """Cancel an open order"""
        if not self.is_connected:
            return False

        try:
            orders = self.ib.openOrders()
            order = next((o for o in orders if o.orderId == order_id), None)
            if order:
                self.ib.cancelOrder(order)
                return True
            return False
        except Exception as e:
            logger.error("Failed to cancel order", error=str(e))
            return False

    # ============================================================
    # Stock Trading Methods (for Gem Hunter agent)
    # ============================================================

    async def get_stock_price(self, symbol: str) -> Optional[float]:
        """Get current stock price"""
        if not self.is_connected:
            return None

        try:
            contract = Stock(symbol, "SMART", "USD")
            await self.ib.qualifyContractsAsync(contract)

            ticker = self.ib.reqMktData(contract, "", False, False)

            # Wait for data with timeout
            price = None
            for _ in range(50):  # 5 second timeout
                await asyncio.sleep(0.1)
                mp = ticker.marketPrice()
                if mp and mp > 0 and not (mp != mp):  # Check for NaN
                    price = mp
                    break
                if ticker.bid and ticker.ask and ticker.bid > 0 and ticker.ask > 0:
                    price = (ticker.bid + ticker.ask) / 2
                    break
                if ticker.last and ticker.last > 0:
                    price = ticker.last
                    break
                if ticker.close and ticker.close > 0:
                    price = ticker.close
                    break

            self.ib.cancelMktData(contract)

            if price and price > 0:
                logger.debug("Got stock price", symbol=symbol, price=price)
                return price
            return None
        except Exception as e:
            logger.error("Failed to get stock price", symbol=symbol, error=str(e))
            return None

    async def create_stock_contract(self, symbol: str) -> Optional[Contract]:
        """Create and qualify a stock contract"""
        if not self.is_connected:
            return None

        try:
            contract = Stock(symbol, "SMART", "USD")
            qualified = await self.ib.qualifyContractsAsync(contract)
            return qualified[0] if qualified else None
        except Exception as e:
            logger.error("Failed to create stock contract", symbol=symbol, error=str(e))
            return None

    async def create_option_contract(
        self,
        symbol: str,
        option_type: str,  # "CALL" or "PUT"
        strike: float,
        expiry: str  # YYYYMMDD format
    ) -> Optional[Contract]:
        """Create and qualify an option contract"""
        if not self.is_connected:
            return None

        try:
            right = "C" if option_type.upper() == "CALL" else "P"
            contract = Option(symbol, expiry, strike, right, "SMART")
            qualified = await self.ib.qualifyContractsAsync(contract)
            return qualified[0] if qualified else None
        except Exception as e:
            logger.error("Failed to create option contract", symbol=symbol, error=str(e))
            return None

    async def place_stock_order(
        self,
        symbol: str,
        action: str,  # "BUY" or "SELL"
        quantity: int,
        order_type: str = "limit",  # "market", "limit", "stop", "stop_limit"
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
        time_in_force: str = "DAY"  # "DAY", "GTC", "IOC"
    ) -> Optional[Any]:
        """
        Place a stock order.

        Returns the Trade object if successful.
        """
        if not self.is_connected or self.readonly:
            logger.warning("Cannot place order: not connected or readonly mode")
            return None

        try:
            contract = await self.create_stock_contract(symbol)
            if not contract:
                logger.error("Failed to create contract for stock order", symbol=symbol)
                return None

            # Create the appropriate order type
            if order_type.lower() == "market":
                order = MarketOrder(action=action, totalQuantity=quantity)
            elif order_type.lower() == "limit":
                if limit_price is None:
                    logger.error("Limit price required for limit order")
                    return None
                order = LimitOrder(action=action, totalQuantity=quantity, lmtPrice=limit_price)
            elif order_type.lower() == "stop":
                if stop_price is None:
                    logger.error("Stop price required for stop order")
                    return None
                order = Order()
                order.action = action
                order.totalQuantity = quantity
                order.orderType = "STP"
                order.auxPrice = stop_price
            elif order_type.lower() == "stop_limit":
                if stop_price is None or limit_price is None:
                    logger.error("Stop and limit prices required for stop-limit order")
                    return None
                order = Order()
                order.action = action
                order.totalQuantity = quantity
                order.orderType = "STP LMT"
                order.auxPrice = stop_price
                order.lmtPrice = limit_price
            else:
                logger.error("Unknown order type", order_type=order_type)
                return None

            # Set time in force
            order.tif = time_in_force

            # Place the order
            trade = self.ib.placeOrder(contract, order)

            logger.info(
                "Placed stock order",
                symbol=symbol,
                action=action,
                quantity=quantity,
                order_type=order_type,
                limit_price=limit_price,
                stop_price=stop_price,
                order_id=trade.order.orderId
            )

            return trade
        except Exception as e:
            logger.error("Failed to place stock order", symbol=symbol, error=str(e))
            return None

    async def place_bracket_order(
        self,
        symbol: str,
        action: str,  # "BUY" or "SELL"
        quantity: int,
        entry_price: float,
        stop_loss_price: float,
        take_profit_price: float
    ) -> Optional[List[Any]]:
        """
        Place a bracket order (entry + stop loss + take profit).

        Returns list of Trade objects if successful.
        """
        if not self.is_connected or self.readonly:
            return None

        try:
            contract = await self.create_stock_contract(symbol)
            if not contract:
                return None

            # Create bracket order using IB's bracket order functionality
            parent = LimitOrder(
                action=action,
                totalQuantity=quantity,
                lmtPrice=entry_price,
                transmit=False  # Don't transmit until children are attached
            )

            exit_action = "SELL" if action == "BUY" else "BUY"

            # Take profit order
            take_profit = LimitOrder(
                action=exit_action,
                totalQuantity=quantity,
                lmtPrice=take_profit_price,
                parentId=0,  # Will be set after parent is placed
                transmit=False
            )

            # Stop loss order
            stop_loss = Order()
            stop_loss.action = exit_action
            stop_loss.totalQuantity = quantity
            stop_loss.orderType = "STP"
            stop_loss.auxPrice = stop_loss_price
            stop_loss.parentId = 0
            stop_loss.transmit = True  # Transmit all orders

            # Place orders
            parent_trade = self.ib.placeOrder(contract, parent)
            parent_id = parent_trade.order.orderId

            take_profit.parentId = parent_id
            stop_loss.parentId = parent_id

            tp_trade = self.ib.placeOrder(contract, take_profit)
            sl_trade = self.ib.placeOrder(contract, stop_loss)

            logger.info(
                "Placed bracket order",
                symbol=symbol,
                action=action,
                quantity=quantity,
                entry_price=entry_price,
                stop_loss=stop_loss_price,
                take_profit=take_profit_price
            )

            return [parent_trade, tp_trade, sl_trade]
        except Exception as e:
            logger.error("Failed to place bracket order", symbol=symbol, error=str(e))
            return None

    async def cancel_all_orders(self, symbol: Optional[str] = None) -> int:
        """
        Cancel all open orders, optionally filtered by symbol.

        Returns the number of orders cancelled.
        """
        if not self.is_connected:
            return 0

        try:
            orders = self.ib.openOrders()
            cancelled = 0

            for order in orders:
                if symbol is None or (hasattr(order, 'contract') and order.contract.symbol == symbol):
                    self.ib.cancelOrder(order)
                    cancelled += 1

            return cancelled
        except Exception as e:
            logger.error("Failed to cancel orders", error=str(e))
            return 0


# Singleton instance for app-wide use
_ib_client: Optional[IBClient] = None


def get_ib_client() -> IBClient:
    """Get or create the IB client singleton"""
    global _ib_client
    if _ib_client is None:
        _ib_client = IBClient(
            host=settings.IB_HOST,
            port=settings.IB_PORT,
            client_id=settings.IB_CLIENT_ID,
            readonly=settings.IB_READONLY
        )
    return _ib_client
