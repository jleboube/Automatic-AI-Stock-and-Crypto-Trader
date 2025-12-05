"""
Robinhood Crypto Trading API Client

Official Robinhood Crypto Trading API client using ED25519 signatures.
API Documentation: https://docs.robinhood.com/crypto/trading/

Authentication:
- Uses ED25519 cryptographic signatures via PyNaCl
- API key and private key required (generate from Robinhood developer portal)
- Private key should be base64-encoded

Rate Limits:
- 10 requests per second per account
- 1000 requests per hour per account
"""

import asyncio
import base64
import json
import time
import uuid
from decimal import Decimal
from datetime import datetime
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

import httpx
import structlog

try:
    from nacl.signing import SigningKey
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

from app.core.config import settings

logger = structlog.get_logger()


# ============================================================
# Data Classes
# ============================================================

@dataclass
class CryptoAccount:
    """Robinhood crypto account info"""
    account_id: str
    status: str
    buying_power: float
    buying_power_currency: str
    is_active: bool


@dataclass
class CryptoHolding:
    """Crypto holding/position"""
    asset_code: str  # e.g., "BTC"
    total_quantity: float
    available_quantity: float
    held_for_orders: float
    cost_basis: Optional[float]
    market_value: Optional[float]


@dataclass
class CryptoQuote:
    """Crypto price quote"""
    symbol: str
    bid_price: float
    ask_price: float
    mark_price: float
    high_price: Optional[float]
    low_price: Optional[float]
    open_price: Optional[float]
    volume: Optional[float]
    timestamp: datetime


@dataclass
class CryptoOrder:
    """Crypto order"""
    id: str
    client_order_id: str
    symbol: str
    side: str  # "buy" or "sell"
    order_type: str  # "market" or "limit"
    quantity: float
    price: Optional[float]  # For limit orders
    status: str
    filled_quantity: float
    filled_price: Optional[float]
    created_at: datetime
    updated_at: Optional[datetime]


@dataclass
class TradingPair:
    """Available crypto trading pair"""
    symbol: str
    asset_code: str
    quote_currency: str
    min_order_size: float
    max_order_size: float
    min_order_price_increment: float
    min_order_quantity_increment: float
    is_tradable: bool


# ============================================================
# Robinhood Crypto Client
# ============================================================

class RobinhoodCryptoClient:
    """
    Official Robinhood Crypto Trading API client.

    Uses ED25519 signatures for authentication via PyNaCl.
    Requires ROBINHOOD_API_KEY and ROBINHOOD_PRIVATE_KEY environment variables.
    """

    BASE_URL = "https://trading.robinhood.com"

    def __init__(
        self,
        api_key: Optional[str] = None,
        private_key_base64: Optional[str] = None
    ):
        if not CRYPTO_AVAILABLE:
            raise ImportError("pynacl package is not installed. Run: pip install pynacl")

        self.api_key = api_key or settings.ROBINHOOD_API_KEY
        self._private_key_base64 = private_key_base64 or settings.ROBINHOOD_PRIVATE_KEY
        self._private_key: Optional[SigningKey] = None
        self._http_client: Optional[httpx.AsyncClient] = None
        self._account_id: Optional[str] = None

        # Load private key
        if self._private_key_base64:
            try:
                # Fix base64 padding if needed (Robinhood may provide without padding)
                key_b64 = self._private_key_base64
                padding_needed = len(key_b64) % 4
                if padding_needed:
                    key_b64 += '=' * (4 - padding_needed)

                key_bytes = base64.b64decode(key_b64)
                # Use PyNaCl SigningKey - it expects the 32-byte seed directly
                self._private_key = SigningKey(key_bytes)
                logger.info("Robinhood private key loaded successfully", key_len=len(key_bytes))
            except Exception as e:
                logger.error("Failed to load Robinhood private key", error=str(e))

    @property
    def is_configured(self) -> bool:
        """Check if client has valid credentials"""
        return bool(self.api_key and self._private_key)

    def _get_timestamp(self) -> int:
        """Get current timestamp in seconds"""
        return int(time.time())

    def _sign_message(self, message: str) -> str:
        """Sign a message with ED25519 private key using PyNaCl"""
        if not self._private_key:
            raise ValueError("Private key not loaded")

        # Use PyNaCl to sign - returns SignedMessage object
        signed = self._private_key.sign(message.encode('utf-8'))
        # Extract just the signature (first 64 bytes), not the message
        return base64.b64encode(signed.signature).decode('utf-8')

    def _create_auth_headers(
        self,
        method: str,
        path: str,
        body: Optional[str] = None
    ) -> Dict[str, str]:
        """
        Create authentication headers for API request.

        The signature message format is:
        {api_key}{timestamp}{path}{method}{body}
        """
        timestamp = self._get_timestamp()
        body_str = body or ""

        # Build message to sign - format: api_key + timestamp + path + method + body
        message = f"{self.api_key}{timestamp}{path}{method}{body_str}"

        logger.debug(
            "Creating signature",
            api_key_prefix=self.api_key[:10] if self.api_key else None,
            timestamp=timestamp,
            path=path,
            method=method,
            body_len=len(body_str),
            message_len=len(message)
        )

        signature = self._sign_message(message)

        headers = {
            "x-api-key": self.api_key,
            "x-timestamp": str(timestamp),
            "x-signature": signature,
            "Content-Type": "application/json; charset=utf-8",
        }

        return headers

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client"""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                timeout=30.0
            )
        return self._http_client

    async def _request(
        self,
        method: str,
        path: str,
        body: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Make authenticated API request"""
        if not self.is_configured:
            raise ValueError("Robinhood client not configured. Check API key and private key.")

        client = await self._get_client()
        body_str = json.dumps(body) if body else None
        headers = self._create_auth_headers(method, path, body_str)

        try:
            if method == "GET":
                response = await client.get(path, headers=headers)
            elif method == "POST":
                response = await client.post(path, headers=headers, content=body_str)
            elif method == "DELETE":
                response = await client.delete(path, headers=headers)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                "Robinhood API error",
                status=e.response.status_code,
                body=e.response.text,
                path=path
            )
            raise
        except Exception as e:
            logger.error("Robinhood request failed", error=str(e), path=path)
            raise

    async def close(self):
        """Close HTTP client"""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    # ============================================================
    # Account Methods
    # ============================================================

    async def get_account(self) -> Optional[CryptoAccount]:
        """Get crypto trading account"""
        try:
            data = await self._request("GET", "/api/v1/crypto/trading/accounts/")

            # API returns account directly or in results array depending on version
            if data.get("results"):
                account = data["results"][0]
            elif data.get("account_number"):
                account = data
            else:
                logger.warning("Unexpected account response format", data_keys=list(data.keys()) if data else None)
                return None

            self._account_id = account.get("account_number")

            return CryptoAccount(
                account_id=account.get("account_number", ""),
                status=account.get("status", ""),
                buying_power=float(account.get("buying_power", 0)),
                buying_power_currency=account.get("buying_power_currency", "USD"),
                is_active=account.get("status") == "active"
            )
        except Exception as e:
            logger.error("Failed to get Robinhood account", error=str(e))
            return None

    async def get_holdings(self) -> List[CryptoHolding]:
        """Get all crypto holdings"""
        try:
            data = await self._request("GET", "/api/v1/crypto/trading/holdings/")

            holdings = []
            for h in data.get("results", []):
                holdings.append(CryptoHolding(
                    asset_code=h.get("asset_code", ""),
                    total_quantity=float(h.get("total_quantity", 0)),
                    available_quantity=float(h.get("available_quantity", 0)),
                    held_for_orders=float(h.get("held_for_orders", 0)),
                    cost_basis=float(h.get("cost_basis")) if h.get("cost_basis") else None,
                    market_value=float(h.get("market_value")) if h.get("market_value") else None
                ))

            return holdings
        except Exception as e:
            logger.error("Failed to get crypto holdings", error=str(e))
            return []

    # ============================================================
    # Market Data Methods
    # ============================================================

    async def get_trading_pairs(self) -> List[TradingPair]:
        """Get all available trading pairs"""
        try:
            data = await self._request("GET", "/api/v1/crypto/trading/trading_pairs/")

            pairs = []
            for p in data.get("results", []):
                # API returns: status, quote_code, asset_increment, quote_increment
                pairs.append(TradingPair(
                    symbol=p.get("symbol", ""),
                    asset_code=p.get("asset_code", ""),
                    quote_currency=p.get("quote_code", "USD"),
                    min_order_size=float(p.get("min_order_size", 0)),
                    max_order_size=float(p.get("max_order_size", 0)),
                    min_order_price_increment=float(p.get("quote_increment", 0)),
                    min_order_quantity_increment=float(p.get("asset_increment", 0)),
                    is_tradable=p.get("status") == "tradable"
                ))

            return pairs
        except Exception as e:
            logger.error("Failed to get trading pairs", error=str(e))
            return []

    async def get_quote(self, symbol: str) -> Optional[CryptoQuote]:
        """
        Get quote for a single symbol.

        Args:
            symbol: Trading pair symbol (e.g., "BTC-USD")
        """
        try:
            # Use best bid/ask endpoint for most accurate pricing
            data = await self._request("GET", f"/api/v1/crypto/marketdata/best_bid_ask/?symbol={symbol}")

            if data.get("results"):
                quote_data = data["results"][0]
                # API returns: price, bid_inclusive_of_sell_spread, ask_inclusive_of_buy_spread
                price = float(quote_data.get("price", 0))
                bid = float(quote_data.get("bid_inclusive_of_sell_spread", price))
                ask = float(quote_data.get("ask_inclusive_of_buy_spread", price))
                return CryptoQuote(
                    symbol=quote_data.get("symbol", symbol),
                    bid_price=bid,
                    ask_price=ask,
                    mark_price=price if price > 0 else (bid + ask) / 2,
                    high_price=None,
                    low_price=None,
                    open_price=None,
                    volume=None,
                    timestamp=datetime.now()
                )
            return None
        except Exception as e:
            logger.error("Failed to get quote", symbol=symbol, error=str(e))
            return None

    async def get_quotes(self, symbols: List[str]) -> List[CryptoQuote]:
        """
        Get quotes for multiple symbols.

        Args:
            symbols: List of trading pair symbols (e.g., ["BTC-USD", "ETH-USD"])

        Note: API requires separate calls for each symbol, so we batch them.
        """
        quotes = []

        # Robinhood API doesn't support comma-separated symbols for batch quotes
        # We need to make individual requests (or use asyncio.gather for parallelism)
        import asyncio

        async def fetch_single(symbol: str) -> Optional[CryptoQuote]:
            return await self.get_quote(symbol)

        # Fetch quotes in parallel batches to avoid rate limiting
        batch_size = 10
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i + batch_size]
            results = await asyncio.gather(*[fetch_single(s) for s in batch], return_exceptions=True)
            for result in results:
                if isinstance(result, CryptoQuote):
                    quotes.append(result)

        return quotes

    async def get_estimated_price(
        self,
        symbol: str,
        side: str,
        quantity: float
    ) -> Optional[float]:
        """
        Get estimated execution price for an order.

        Args:
            symbol: Trading pair symbol (e.g., "BTC-USD")
            side: "buy" or "sell"
            quantity: Order quantity in asset units
        """
        try:
            body = {
                "symbol": symbol,
                "side": side,
                "quantity": str(quantity)
            }
            data = await self._request("POST", "/api/v1/crypto/trading/estimated_price/", body)

            return float(data.get("price", 0))
        except Exception as e:
            logger.error("Failed to get estimated price", symbol=symbol, error=str(e))
            return None

    # ============================================================
    # Order Methods
    # ============================================================

    async def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str = "market",
        quantity: Optional[float] = None,
        notional_amount: Optional[float] = None,
        limit_price: Optional[float] = None,
        time_in_force: str = "gtc"
    ) -> Optional[CryptoOrder]:
        """
        Place a crypto order.

        Args:
            symbol: Trading pair symbol (e.g., "BTC-USD")
            side: "buy" or "sell"
            order_type: "market" or "limit"
            quantity: Amount in asset units (e.g., 0.001 BTC)
            notional_amount: Amount in USD (for market orders, alternative to quantity)
            limit_price: Limit price (required for limit orders)
            time_in_force: "gtc" (good til cancelled) or "ioc" (immediate or cancel)

        Returns:
            CryptoOrder if successful, None otherwise

        Note:
            - For market orders, you can specify either quantity or notional_amount
            - Robinhood has order collars: 1% for buys, 5% for sells
            - Market orders timeout after 2 minutes
        """
        try:
            client_order_id = str(uuid.uuid4())

            body = {
                "client_order_id": client_order_id,
                "symbol": symbol,
                "side": side,
                "type": order_type,
                "time_in_force": time_in_force
            }

            # Helper to format floats without trailing zeros but with precision
            def format_decimal(value: float) -> str:
                """Format a float as a decimal string without floating-point artifacts"""
                # Convert to Decimal to get exact string representation
                d = Decimal(str(value))
                # Normalize to remove trailing zeros but keep precision
                normalized = d.normalize()
                # Convert to string and ensure it's a proper decimal format
                s = str(normalized)
                # If it's in scientific notation, convert back to normal
                if 'E' in s or 'e' in s:
                    # Use fixed point notation with enough precision
                    s = f"{value:.15f}".rstrip('0').rstrip('.')
                return s

            # Use the new Robinhood API format with *_order_config objects
            if order_type == "limit":
                if limit_price is None:
                    raise ValueError("Limit price required for limit orders")
                if quantity is None:
                    raise ValueError("Quantity required for limit orders")
                # Format using Decimal for exact representation
                body["limit_order_config"] = {
                    "asset_quantity": format_decimal(quantity),
                    "limit_price": format_decimal(limit_price)
                }
            else:
                # Market order
                if quantity is not None:
                    body["market_order_config"] = {
                        "asset_quantity": format_decimal(quantity)
                    }
                elif notional_amount is not None:
                    # Use quote_amount for USD-based orders
                    body["market_order_config"] = {
                        "quote_amount": f"{notional_amount:.2f}"
                    }
                else:
                    raise ValueError("Either quantity or notional_amount must be provided")

            data = await self._request("POST", "/api/v1/crypto/trading/orders/", body)

            logger.info(
                "Crypto order placed",
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=quantity,
                notional_amount=notional_amount,
                order_id=data.get("id")
            )

            # Parse quantity from order config or direct field
            order_quantity = quantity or 0
            if data.get("market_order_config"):
                order_quantity = float(data["market_order_config"].get("asset_quantity", order_quantity))
            elif data.get("limit_order_config"):
                order_quantity = float(data["limit_order_config"].get("asset_quantity", order_quantity))

            # Parse filled quantity - Robinhood uses "filled_asset_quantity" not "filled_quantity"
            filled_qty = float(data.get("filled_asset_quantity", data.get("filled_quantity", 0)))

            return CryptoOrder(
                id=data.get("id", ""),
                client_order_id=data.get("client_order_id", client_order_id),
                symbol=data.get("symbol", symbol),
                side=data.get("side", side),
                order_type=data.get("type", order_type),
                quantity=order_quantity,
                price=float(data.get("limit_price")) if data.get("limit_price") else None,
                status=data.get("state", "pending"),
                filled_quantity=filled_qty,
                filled_price=float(data.get("average_price")) if data.get("average_price") else None,
                created_at=datetime.fromisoformat(data.get("created_at", datetime.now().isoformat()).replace("Z", "+00:00")),
                updated_at=datetime.fromisoformat(data.get("updated_at").replace("Z", "+00:00")) if data.get("updated_at") else None
            )
        except Exception as e:
            logger.error(
                "Failed to place crypto order",
                symbol=symbol,
                side=side,
                error=str(e)
            )
            return None

    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an open order.

        Args:
            order_id: Order ID to cancel
        """
        try:
            await self._request("POST", f"/api/v1/crypto/trading/orders/{order_id}/cancel/")
            logger.info("Crypto order cancelled", order_id=order_id)
            return True
        except Exception as e:
            logger.error("Failed to cancel crypto order", order_id=order_id, error=str(e))
            return False

    async def get_order(self, order_id: str) -> Optional[CryptoOrder]:
        """Get order by ID"""
        try:
            data = await self._request("GET", f"/api/v1/crypto/trading/orders/{order_id}/")

            # Parse quantity from order config or direct field
            order_quantity = 0.0
            if data.get("market_order_config"):
                order_quantity = float(data["market_order_config"].get("asset_quantity", 0))
            elif data.get("limit_order_config"):
                order_quantity = float(data["limit_order_config"].get("asset_quantity", 0))

            # Parse filled quantity - Robinhood uses "filled_asset_quantity" not "filled_quantity"
            filled_qty = float(data.get("filled_asset_quantity", data.get("filled_quantity", 0)))

            return CryptoOrder(
                id=data.get("id", ""),
                client_order_id=data.get("client_order_id", ""),
                symbol=data.get("symbol", ""),
                side=data.get("side", ""),
                order_type=data.get("type", ""),
                quantity=order_quantity,
                price=float(data.get("limit_price")) if data.get("limit_price") else None,
                status=data.get("state", ""),
                filled_quantity=filled_qty,
                filled_price=float(data.get("average_price")) if data.get("average_price") else None,
                created_at=datetime.fromisoformat(data.get("created_at", datetime.now().isoformat()).replace("Z", "+00:00")),
                updated_at=datetime.fromisoformat(data.get("updated_at").replace("Z", "+00:00")) if data.get("updated_at") else None
            )
        except Exception as e:
            logger.error("Failed to get crypto order", order_id=order_id, error=str(e))
            return None

    async def get_orders(
        self,
        status: Optional[str] = None,
        limit: int = 50
    ) -> List[CryptoOrder]:
        """
        Get orders with optional status filter.

        Args:
            status: Filter by status ("open", "filled", "cancelled", etc.)
            limit: Maximum number of orders to return
        """
        try:
            path = f"/api/v1/crypto/trading/orders/?limit={limit}"
            if status:
                path += f"&state={status}"

            data = await self._request("GET", path)

            orders = []
            for o in data.get("results", []):
                # Parse quantity from order config or direct field
                order_quantity = 0.0
                if o.get("market_order_config"):
                    order_quantity = float(o["market_order_config"].get("asset_quantity", 0))
                elif o.get("limit_order_config"):
                    order_quantity = float(o["limit_order_config"].get("asset_quantity", 0))

                # Parse filled quantity - Robinhood uses "filled_asset_quantity" not "filled_quantity"
                filled_qty = float(o.get("filled_asset_quantity", o.get("filled_quantity", 0)))

                orders.append(CryptoOrder(
                    id=o.get("id", ""),
                    client_order_id=o.get("client_order_id", ""),
                    symbol=o.get("symbol", ""),
                    side=o.get("side", ""),
                    order_type=o.get("type", ""),
                    quantity=order_quantity,
                    price=float(o.get("limit_price")) if o.get("limit_price") else None,
                    status=o.get("state", ""),
                    filled_quantity=filled_qty,
                    filled_price=float(o.get("average_price")) if o.get("average_price") else None,
                    created_at=datetime.fromisoformat(o.get("created_at", datetime.now().isoformat()).replace("Z", "+00:00")),
                    updated_at=datetime.fromisoformat(o.get("updated_at").replace("Z", "+00:00")) if o.get("updated_at") else None
                ))

            return orders
        except Exception as e:
            logger.error("Failed to get crypto orders", error=str(e))
            return []

    # ============================================================
    # Helper Methods
    # ============================================================

    def format_symbol(self, asset_code: str) -> str:
        """
        Format asset code to trading pair symbol.

        Args:
            asset_code: Asset code (e.g., "BTC")

        Returns:
            Trading pair symbol (e.g., "BTC-USD")
        """
        return f"{asset_code.upper()}-USD"

    def parse_symbol(self, symbol: str) -> str:
        """
        Parse trading pair symbol to asset code.

        Args:
            symbol: Trading pair symbol (e.g., "BTC-USD")

        Returns:
            Asset code (e.g., "BTC")
        """
        return symbol.split("-")[0].upper()


# ============================================================
# Singleton Instance
# ============================================================

_robinhood_client: Optional[RobinhoodCryptoClient] = None


def get_robinhood_client() -> RobinhoodCryptoClient:
    """Get or create the Robinhood client singleton"""
    global _robinhood_client
    if _robinhood_client is None:
        _robinhood_client = RobinhoodCryptoClient()
    return _robinhood_client
