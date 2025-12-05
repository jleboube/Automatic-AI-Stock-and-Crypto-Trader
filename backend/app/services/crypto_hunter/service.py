"""
Crypto Hunter Service

Main orchestrator for the Crypto Hunter autonomous trading agent.
Coordinates trend analysis, fundamental analysis, risk management, and execution.
"""

import structlog
import asyncio
import httpx
from typing import Dict, Any, Optional, List
from datetime import datetime, date, timedelta
from dataclasses import dataclass, asdict

from sqlalchemy.orm import Session
from sqlalchemy import and_

from .trend_analyzer import TrendAnalyzer, TrendAnalysis, TrendDirection
from .fundamental_analyzer import FundamentalAnalyzer, FundamentalAnalysis
from .risk_manager import CryptoRiskManager, CryptoRiskStatus, CryptoPositionSize
from .executor import CryptoExecutor, CryptoOrderResult, CryptoOrderStatus

from app.services.broker.robinhood_client import RobinhoodCryptoClient
from app.services.activity_service import (
    log_cycle_start, log_cycle_end,
    log_trade_signal, log_order, log_position, log_error, log_info
)
from app.models.agent import Agent, AgentStatus
from app.models.crypto import (
    CryptoPosition, CryptoPositionStatus,
    CryptoWatchlist, CryptoWatchlistStatus,
    CryptoTrade, CryptoOrderStatus as DbOrderStatus
)

logger = structlog.get_logger()


@dataclass
class CryptoAnalysis:
    """Combined analysis result for a crypto asset"""
    symbol: str
    current_price: float
    trend_analysis: TrendAnalysis
    fundamental_analysis: FundamentalAnalysis

    # Composite scores
    trend_score: float
    fundamental_score: float
    momentum_score: float
    composite_score: float

    # Trade setup
    entry_price: float
    target_price: float
    stop_loss: float
    risk_reward_ratio: float

    # Entry criteria
    entry_trigger: str  # immediate, breakout, pullback, volume_surge
    reasoning: str


@dataclass
class CryptoHunterState:
    """Current state of the Crypto Hunter agent"""
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
    last_scan: Optional[datetime]
    last_trade: Optional[datetime]
    is_trading_enabled: bool
    risk_status: Optional[CryptoRiskStatus]


class CryptoHunterService:
    """
    Autonomous crypto trading agent that scans markets for opportunities
    using trend and fundamental analysis.

    Key differences from Gem Hunter (stocks):
    - 24/7 operation (no market hours check)
    - Uses Robinhood Crypto API instead of IB
    - Wider stops due to crypto volatility
    - Fractional position sizing
    - More frequent scans

    Workflow:
    1. Fetch all available crypto pairs from Robinhood
    2. Get quotes and calculate technical indicators
    3. Analyze trends and fundamentals
    4. Add top candidates to watchlist
    5. Execute trades for qualifying opportunities
    6. Manage open positions (stop-loss, take-profit)
    """

    # Class-level cache for historical prices (persists across instances)
    _class_historical_cache: Dict[str, tuple] = {}
    _class_coingecko_last_request: Optional[datetime] = None

    def __init__(
        self,
        agent_id: int,
        db: Session,
        robinhood_client: RobinhoodCryptoClient,
        config: Dict[str, Any]
    ):
        """
        Initialize the Crypto Hunter service.

        Args:
            agent_id: Database ID of this agent
            db: SQLAlchemy database session
            robinhood_client: Robinhood Crypto API client
            config: Agent configuration
        """
        self.agent_id = agent_id
        self.db = db
        self.client = robinhood_client
        self.config = config

        # Initialize components
        self.trend_analyzer = TrendAnalyzer(config)
        self.fundamental_analyzer = FundamentalAnalyzer(config)
        self.risk_manager = CryptoRiskManager(config)
        self.executor = CryptoExecutor(robinhood_client, config)

        # Configuration
        self.min_score = config.get("min_composite_score", 65)
        self.entry_score_threshold = config.get("entry_score_threshold", 75)
        self.max_watchlist = config.get("max_watchlist", 20)
        self.auto_trade = config.get("auto_trade", True)
        self.scan_interval_minutes = config.get("scan_interval_minutes", 15)

        # Scoring weights
        self.trend_weight = config.get("trend_weight", 0.50)
        self.fundamental_weight = config.get("fundamental_weight", 0.30)
        self.momentum_weight = config.get("momentum_weight", 0.20)

        # Coin filtering
        self.coins = config.get("coins", [])  # Empty = all available
        self.exclude_coins = config.get("exclude_coins", [])

        # State tracking
        self._daily_pnl: Dict[date, float] = {}
        self._last_scan: Optional[datetime] = None
        self._price_cache: Dict[str, List[float]] = {}  # symbol -> recent price history
        self._historical_cache_ttl = timedelta(hours=1)  # Cache historical data for 1 hour
        self._coingecko_rate_limit = 0.5  # seconds between requests (2 per second max)

    async def run_cycle(self) -> Dict[str, Any]:
        """
        Run a complete trading cycle.

        Unlike stocks, crypto trades 24/7, so no market hours check needed.
        Returns summary of actions taken.
        """
        logger.info("Starting Crypto Hunter cycle", agent_id=self.agent_id)

        summary = {
            "timestamp": datetime.now().isoformat(),
            "pairs_scanned": 0,
            "analyzed": 0,
            "added_to_watchlist": 0,
            "trades_executed": 0,
            "positions_closed": 0,
            "errors": []
        }

        try:
            # Log cycle start
            log_cycle_start(self.db, self.agent_id, {
                "market": "crypto",
                "mode": "24/7"
            })

            # 1. Check risk status first
            risk_status = await self._get_risk_status()

            if risk_status.is_daily_limit_hit:
                logger.warning("Daily loss limit hit, skipping cycle")
                summary["errors"].append("Daily loss limit reached")
                return summary

            # 2. Manage existing positions (check stops/targets)
            closed = await self._manage_positions()
            summary["positions_closed"] = closed

            # 3. Fetch available trading pairs
            pairs = await self._get_trading_pairs()
            summary["pairs_scanned"] = len(pairs)

            if not pairs:
                logger.warning("No trading pairs available")
                summary["errors"].append("No trading pairs available")
                return summary

            # 4. Analyze each pair
            analyses = await self._analyze_pairs(pairs)
            summary["analyzed"] = len(analyses)

            # 5. Update watchlist with top candidates
            added = await self._update_watchlist(analyses)
            summary["added_to_watchlist"] = added

            # 6. Execute trades for qualifying opportunities
            if self.auto_trade and risk_status.can_open_new:
                trades = await self._execute_trades(risk_status)
                summary["trades_executed"] = trades

            # Update last scan time
            self._last_scan = datetime.now()
            await self._update_agent_last_run()

            # Log cycle completion
            log_cycle_end(self.db, self.agent_id, {
                "pairs_scanned": summary["pairs_scanned"],
                "analyzed": summary["analyzed"],
                "added_to_watchlist": summary["added_to_watchlist"],
                "trades_executed": summary["trades_executed"],
                "positions_closed": summary["positions_closed"]
            })

            logger.info("Crypto Hunter cycle complete", **summary)

        except Exception as e:
            logger.error("Crypto Hunter cycle error", error=str(e))
            log_error(self.db, self.agent_id, str(e))
            summary["errors"].append(str(e))

        return summary

    async def _get_trading_pairs(self) -> List[str]:
        """Get list of tradable crypto pairs"""
        try:
            pairs = await self.client.get_trading_pairs()

            # Filter to tradable pairs
            tradable = [p.symbol for p in pairs if p.is_tradable]

            # Apply coin filters
            if self.coins:
                # Only include specified coins
                allowed = [f"{c.upper()}-USD" for c in self.coins]
                tradable = [p for p in tradable if p in allowed]

            if self.exclude_coins:
                # Exclude specified coins
                excluded = [f"{c.upper()}-USD" for c in self.exclude_coins]
                tradable = [p for p in tradable if p not in excluded]

            logger.info("Found tradable pairs", count=len(tradable))
            return tradable

        except Exception as e:
            logger.error("Failed to get trading pairs", error=str(e))
            return []

    async def _fetch_historical_prices(self, symbol: str, days: int = 7) -> Optional[List[float]]:
        """
        Fetch historical prices using multiple data sources with fallback.

        Primary: CryptoCompare (no strict rate limits, no API key required)
        Fallback: CoinGecko (has rate limits but wider coverage)

        Args:
            symbol: Trading pair symbol (e.g., "BTC-USD")
            days: Number of days of history to fetch

        Returns:
            List of prices (oldest to newest) or None if all sources fail
        """
        # Check class-level cache first - historical data doesn't change frequently
        if symbol in CryptoHunterService._class_historical_cache:
            cached_prices, fetch_time = CryptoHunterService._class_historical_cache[symbol]
            if datetime.now() - fetch_time < self._historical_cache_ttl:
                return cached_prices

        # Extract coin code from symbol (e.g., "BTC-USD" -> "BTC")
        coin_code = symbol.split("-")[0].upper()

        # Try CryptoCompare first (better rate limits)
        prices = await self._fetch_from_cryptocompare(coin_code, days)

        # Fall back to CoinGecko if CryptoCompare fails
        if not prices:
            prices = await self._fetch_from_coingecko(coin_code, days)

        if prices and len(prices) >= 20:
            # Cache the result at class level
            CryptoHunterService._class_historical_cache[symbol] = (prices, datetime.now())
            logger.debug(
                "Fetched historical prices",
                symbol=symbol,
                points=len(prices)
            )
            return prices

        return None

    async def _fetch_from_cryptocompare(self, coin_code: str, days: int) -> Optional[List[float]]:
        """
        Fetch historical prices from CryptoCompare API.
        No API key required for basic usage, no strict rate limits.

        Args:
            coin_code: Coin symbol (e.g., "BTC")
            days: Number of days of history

        Returns:
            List of prices or None if fetch fails
        """
        try:
            # Calculate hours needed (CryptoCompare uses hourly data)
            hours = min(days * 24, 168)  # Max 7 days of hourly data

            async with httpx.AsyncClient(timeout=15.0) as client:
                url = "https://min-api.cryptocompare.com/data/v2/histohour"
                params = {
                    "fsym": coin_code,
                    "tsym": "USD",
                    "limit": hours
                }

                response = await client.get(url, params=params)
                response.raise_for_status()

                data = response.json()

                if data.get("Response") != "Success":
                    logger.debug(
                        "CryptoCompare API error",
                        coin=coin_code,
                        message=data.get("Message", "Unknown error")
                    )
                    return None

                price_data = data.get("Data", {}).get("Data", [])
                if not price_data:
                    return None

                # Extract close prices
                prices = [p["close"] for p in price_data if p.get("close", 0) > 0]

                # Resample to ~50 data points for consistent analysis
                if len(prices) > 50:
                    step = len(prices) // 50
                    prices = prices[::step][:50]

                if len(prices) >= 20:
                    logger.debug(
                        "CryptoCompare fetch successful",
                        coin=coin_code,
                        points=len(prices)
                    )
                    return prices

                return None

        except Exception as e:
            logger.debug("CryptoCompare fetch failed", coin=coin_code, error=str(e))
            return None

    async def _fetch_from_coingecko(self, coin_code: str, days: int) -> Optional[List[float]]:
        """
        Fetch historical prices from CoinGecko API (fallback).
        Has rate limits on free tier, so used as backup.

        Args:
            coin_code: Coin symbol (e.g., "BTC")
            days: Number of days of history

        Returns:
            List of prices or None if fetch fails
        """
        # Map coin code to CoinGecko ID
        coin_id_map = {
            # Major coins
            "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana",
            "DOGE": "dogecoin", "SHIB": "shiba-inu", "AVAX": "avalanche-2",
            "LINK": "chainlink", "UNI": "uniswap", "AAVE": "aave",
            "XLM": "stellar", "LTC": "litecoin", "BCH": "bitcoin-cash",
            "ETC": "ethereum-classic", "COMP": "compound-governance-token",
            "XTZ": "tezos", "MATIC": "matic-network", "ATOM": "cosmos",
            "DOT": "polkadot", "ADA": "cardano", "ALGO": "algorand",
            # DeFi & Layer 2
            "FIL": "filecoin", "NEAR": "near", "APE": "apecoin",
            "ARB": "arbitrum", "OP": "optimism", "SUI": "sui",
            "SEI": "sei-network", "TIA": "celestia", "JUP": "jupiter-exchange-solana",
            # Meme coins
            "BONK": "bonk", "WIF": "dogwifcoin", "PEPE": "pepe",
            "FLOKI": "floki", "MOODENG": "moo-deng",
            # New/emerging
            "HYPE": "hyperliquid", "AERO": "aerodrome-finance",
            "RENDER": "render-token", "INJ": "injective-protocol",
            "FET": "fetch-ai", "RNDR": "render-token", "PYTH": "pyth-network",
            # Additional coins
            "CRV": "curve-dao-token", "MKR": "maker", "SNX": "havven",
            "SUSHI": "sushi", "YFI": "yearn-finance", "1INCH": "1inch",
            "BAT": "basic-attention-token", "ENJ": "enjincoin",
            "SAND": "the-sandbox", "MANA": "decentraland", "AXS": "axie-infinity",
            "GRT": "the-graph", "LRC": "loopring", "ZRX": "0x",
            "STORJ": "storj", "UMA": "uma", "BAL": "balancer",
            "REN": "republic-protocol", "KNC": "kyber-network-crystal",
            "XRP": "ripple", "BNB": "binancecoin", "TRX": "tron",
            "TON": "the-open-network",
        }

        coin_id = coin_id_map.get(coin_code)
        if not coin_id:
            logger.debug("No CoinGecko mapping for coin", coin=coin_code)
            return None

        # Rate limiting for CoinGecko
        if CryptoHunterService._class_coingecko_last_request:
            elapsed = (datetime.now() - CryptoHunterService._class_coingecko_last_request).total_seconds()
            if elapsed < self._coingecko_rate_limit:
                await asyncio.sleep(self._coingecko_rate_limit - elapsed)

        try:
            CryptoHunterService._class_coingecko_last_request = datetime.now()

            async with httpx.AsyncClient(timeout=10.0) as client:
                url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
                params = {"vs_currency": "usd", "days": days}

                response = await client.get(url, params=params)
                response.raise_for_status()

                data = response.json()
                prices = data.get("prices", [])

                if not prices:
                    return None

                # Extract just the price values
                price_list = [p[1] for p in prices]

                # Resample to ~50 data points
                if len(price_list) > 50:
                    step = len(price_list) // 50
                    price_list = price_list[::step][:50]

                if len(price_list) >= 20:
                    logger.debug(
                        "CoinGecko fetch successful",
                        coin=coin_code,
                        points=len(price_list)
                    )
                    return price_list

                return None

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.debug("CoinGecko rate limit hit", coin=coin_code)
            else:
                logger.debug("CoinGecko API error", coin=coin_code, status=e.response.status_code)
            return None
        except Exception as e:
            logger.debug("CoinGecko fetch failed", coin=coin_code, error=str(e))
            return None

    async def _analyze_pairs(self, pairs: List[str]) -> List[CryptoAnalysis]:
        """Analyze all trading pairs"""
        analyses = []

        # Get quotes for all pairs
        quotes = await self.client.get_quotes(pairs)
        quote_map = {q.symbol: q for q in quotes}

        for symbol in pairs:
            try:
                quote = quote_map.get(symbol)
                if not quote or quote.mark_price <= 0:
                    continue

                current_price = quote.mark_price

                # Get price history - must be real data, no fake/mock data allowed
                prices = self._price_cache.get(symbol, [])
                if not prices or len(prices) < 20:
                    # Fetch historical prices from CoinGecko
                    historical = await self._fetch_historical_prices(symbol, days=7)
                    if historical and len(historical) >= 20:
                        # Use real historical data, append current price
                        prices = historical[-49:] + [current_price]
                        self._price_cache[symbol] = prices
                    else:
                        # No real historical data available - skip this asset
                        logger.debug(
                            "Skipping asset - no historical data available",
                            symbol=symbol
                        )
                        continue
                else:
                    # Add current live price to existing price history
                    prices = prices[-49:] + [current_price]
                    self._price_cache[symbol] = prices

                # Trend analysis
                trend = self.trend_analyzer.analyze(
                    symbol=symbol,
                    prices=prices,
                    current_price=current_price
                )

                # Fundamental analysis with actual high/low from price history
                price_high = max(prices) if prices else current_price
                price_low = min(prices) if prices else current_price

                # Calculate price changes from historical data
                price_changes = {}
                if len(prices) >= 2:
                    price_changes["24h"] = ((prices[-1] - prices[-2]) / prices[-2]) * 100 if prices[-2] > 0 else 0
                if len(prices) >= 7:
                    price_changes["7d"] = ((prices[-1] - prices[-7]) / prices[-7]) * 100 if prices[-7] > 0 else 0

                fundamental = self.fundamental_analyzer.analyze(
                    symbol=symbol,
                    current_price=current_price,
                    volume_24h=None,  # Would get from market data
                    avg_volume=None,
                    high_52w=price_high,  # Use actual high from history
                    low_52w=price_low,    # Use actual low from history
                    market_cap_rank=None,
                    price_changes=price_changes,
                    asset_prices=prices
                )

                # Calculate composite score
                trend_score = trend.score
                fundamental_score = fundamental.score
                momentum_score = self._calculate_momentum_score(prices)

                composite_score = (
                    trend_score * self.trend_weight +
                    fundamental_score * self.fundamental_weight +
                    momentum_score * self.momentum_weight
                )

                # Only include if meets minimum score
                if composite_score < self.min_score:
                    continue

                # Calculate trade setup
                stop_loss = self.risk_manager.calculate_stop_loss(current_price)
                target_price = self.risk_manager.calculate_take_profit(current_price, stop_loss)
                risk = current_price - stop_loss
                reward = target_price - current_price
                risk_reward = reward / risk if risk > 0 else 0

                # Determine entry trigger
                entry_trigger = self._determine_entry_trigger(trend, fundamental)

                # Generate reasoning
                reasoning = self._generate_reasoning(trend, fundamental, composite_score)

                analyses.append(CryptoAnalysis(
                    symbol=symbol,
                    current_price=current_price,
                    trend_analysis=trend,
                    fundamental_analysis=fundamental,
                    trend_score=trend_score,
                    fundamental_score=fundamental_score,
                    momentum_score=momentum_score,
                    composite_score=composite_score,
                    entry_price=current_price,
                    target_price=target_price,
                    stop_loss=stop_loss,
                    risk_reward_ratio=risk_reward,
                    entry_trigger=entry_trigger,
                    reasoning=reasoning
                ))

            except Exception as e:
                logger.warning("Failed to analyze pair", symbol=symbol, error=str(e))
                continue

        # Sort by composite score
        analyses.sort(key=lambda x: x.composite_score, reverse=True)

        logger.info(
            "Crypto analysis complete",
            total_pairs=len(pairs),
            analyzed=len(analyses)
        )

        return analyses

    def _calculate_momentum_score(self, prices: List[float]) -> float:
        """Calculate momentum score from price history"""
        if len(prices) < 10:
            return 50.0

        # Recent price change (last 10 periods)
        recent_change = (prices[-1] - prices[-10]) / prices[-10] if prices[-10] != 0 else 0

        # Convert to score (0-100)
        # +10% change = 100, -10% change = 0
        score = 50 + (recent_change * 500)
        return max(0, min(100, score))

    def _determine_entry_trigger(
        self,
        trend: TrendAnalysis,
        fundamental: FundamentalAnalysis
    ) -> str:
        """Determine the entry trigger type"""
        # Strong bullish trend = immediate
        if trend.direction == TrendDirection.BULLISH and trend.strength > 70:
            return "immediate"

        # Near support with bullish signals
        if trend.rsi and trend.rsi < 35:
            return "pullback"

        # High volume = volume surge
        if fundamental.volume_ratio and fundamental.volume_ratio > 2:
            return "volume_surge"

        # Near resistance = breakout
        if trend.resistance_levels and trend.current_price:
            nearest_resistance = min(
                (r for r in trend.resistance_levels if r > trend.current_price),
                default=None
            )
            if nearest_resistance and (nearest_resistance - trend.current_price) / trend.current_price < 0.03:
                return "breakout"

        return "immediate"

    def _generate_reasoning(
        self,
        trend: TrendAnalysis,
        fundamental: FundamentalAnalysis,
        composite_score: float
    ) -> str:
        """Generate human-readable reasoning for the trade"""
        parts = []

        # Trend summary
        parts.append(trend.summary)

        # Fundamental summary
        if fundamental.summary:
            parts.append(fundamental.summary)

        # Composite score
        parts.append(f"Composite score: {composite_score:.0f}/100")

        return " | ".join(parts)

    async def _update_watchlist(self, analyses: List[CryptoAnalysis]) -> int:
        """Update the watchlist with new candidates"""
        added = 0

        for analysis in analyses[:self.max_watchlist]:
            # Check if already in watchlist
            existing = self.db.query(CryptoWatchlist).filter(
                and_(
                    CryptoWatchlist.agent_id == self.agent_id,
                    CryptoWatchlist.symbol == analysis.symbol,
                    CryptoWatchlist.status == CryptoWatchlistStatus.WATCHING
                )
            ).first()

            if existing:
                # Update existing entry
                existing.composite_score = analysis.composite_score
                existing.trend_score = analysis.trend_score
                existing.fundamental_score = analysis.fundamental_score
                existing.momentum_score = analysis.momentum_score
                existing.entry_price = analysis.entry_price
                existing.target_price = analysis.target_price
                existing.stop_loss = analysis.stop_loss
                existing.entry_trigger = analysis.entry_trigger
                existing.analysis_json = {"reasoning": analysis.reasoning}
                existing.updated_at = datetime.utcnow()
            else:
                # Add new entry
                watchlist_entry = CryptoWatchlist(
                    agent_id=self.agent_id,
                    symbol=analysis.symbol,
                    composite_score=analysis.composite_score,
                    trend_score=analysis.trend_score,
                    fundamental_score=analysis.fundamental_score,
                    momentum_score=analysis.momentum_score,
                    entry_price=analysis.entry_price,
                    target_price=analysis.target_price,
                    stop_loss=analysis.stop_loss,
                    entry_trigger=analysis.entry_trigger,
                    analysis_json={"reasoning": analysis.reasoning},
                    status=CryptoWatchlistStatus.WATCHING
                )
                self.db.add(watchlist_entry)
                added += 1

        self.db.commit()

        # Expire old watchlist entries
        await self._expire_old_watchlist_entries()

        logger.info("Crypto watchlist updated", added=added)
        return added

    async def _expire_old_watchlist_entries(self, hours: int = 48):
        """Remove watchlist entries older than specified hours"""
        cutoff = datetime.utcnow() - timedelta(hours=hours)

        old_entries = self.db.query(CryptoWatchlist).filter(
            and_(
                CryptoWatchlist.agent_id == self.agent_id,
                CryptoWatchlist.status == CryptoWatchlistStatus.WATCHING,
                CryptoWatchlist.created_at < cutoff
            )
        ).all()

        for entry in old_entries:
            entry.status = CryptoWatchlistStatus.EXPIRED
            entry.updated_at = datetime.utcnow()

        if old_entries:
            self.db.commit()
            logger.info("Expired old crypto watchlist entries", count=len(old_entries))

    async def _execute_trades(self, risk_status: CryptoRiskStatus) -> int:
        """Execute trades for qualifying watchlist entries"""
        executed = 0

        # Get top watchlist entries above entry threshold
        watchlist = self.db.query(CryptoWatchlist).filter(
            and_(
                CryptoWatchlist.agent_id == self.agent_id,
                CryptoWatchlist.status == CryptoWatchlistStatus.WATCHING,
                CryptoWatchlist.composite_score >= self.entry_score_threshold
            )
        ).order_by(CryptoWatchlist.composite_score.desc()).limit(5).all()

        for entry in watchlist:
            if not risk_status.can_open_new:
                break

            # Get current quote
            quote = await self.client.get_quote(entry.symbol)
            if not quote:
                continue

            current_price = quote.mark_price

            # Calculate position size
            position_size = self.risk_manager.calculate_position_size(
                symbol=entry.symbol,
                entry_price=current_price,
                stop_loss=entry.stop_loss,
                deployed_capital=risk_status.deployed_capital,
                open_positions=risk_status.open_positions
            )

            if position_size.quantity > 0:
                # Execute the trade
                result = await self.executor.execute_entry(
                    symbol=entry.symbol,
                    quantity=position_size.quantity,
                    current_price=current_price
                )

                if result.status == CryptoOrderStatus.FILLED:
                    # Create position record
                    await self._create_position(entry, result, position_size)

                    # Update watchlist status
                    entry.status = CryptoWatchlistStatus.ENTERED
                    entry.updated_at = datetime.utcnow()

                    # Log the trade
                    log_trade_signal(
                        self.db, self.agent_id,
                        entry.symbol, "buy",
                        {"quantity": result.filled_quantity, "price": result.filled_price}
                    )

                    executed += 1

                    # Update risk status
                    risk_status = await self._get_risk_status()

                    logger.info(
                        "Crypto trade executed",
                        symbol=entry.symbol,
                        quantity=result.filled_quantity,
                        price=result.filled_price
                    )

        if executed > 0:
            self.db.commit()

        return executed

    async def _create_position(
        self,
        entry: CryptoWatchlist,
        result: CryptoOrderResult,
        position_size: CryptoPositionSize
    ):
        """Create a position record from a filled order"""
        position = CryptoPosition(
            agent_id=self.agent_id,
            symbol=entry.symbol,
            side="long",
            entry_price=result.filled_price,
            quantity=result.filled_quantity,
            allocated_amount=result.filled_price * result.filled_quantity,
            stop_loss=entry.stop_loss,
            take_profit=entry.target_price,
            status=CryptoPositionStatus.OPEN,
            entry_reason=f"Composite score: {entry.composite_score:.0f}",
            entry_order_id=result.order_id,
            created_at=datetime.utcnow()
        )
        self.db.add(position)

        # Create trade record
        trade = CryptoTrade(
            agent_id=self.agent_id,
            symbol=entry.symbol,
            side="buy",
            quantity=result.filled_quantity,
            price=result.filled_price,
            notional_value=result.filled_price * result.filled_quantity,
            order_id=result.order_id,
            order_type=result.order_type,
            status=DbOrderStatus.FILLED,
            executed_at=datetime.utcnow()
        )
        self.db.add(trade)

    async def _manage_positions(self) -> int:
        """Check and manage open positions"""
        closed = 0

        positions = self.db.query(CryptoPosition).filter(
            and_(
                CryptoPosition.agent_id == self.agent_id,
                CryptoPosition.status == CryptoPositionStatus.OPEN
            )
        ).all()

        for position in positions:
            try:
                # Get current quote
                quote = await self.client.get_quote(position.symbol)
                if not quote:
                    continue

                current_price = quote.mark_price
                position.current_price = current_price

                # Calculate hours held
                hours_held = (datetime.utcnow() - position.created_at).total_seconds() / 3600

                # Check exit conditions
                should_exit, reason = self.risk_manager.should_exit(
                    current_price=current_price,
                    entry_price=position.entry_price,
                    stop_loss=position.stop_loss,
                    take_profit=position.take_profit,
                    hours_held=hours_held
                )

                if should_exit:
                    # Execute exit
                    result = await self.executor.execute_exit(
                        symbol=position.symbol,
                        quantity=position.quantity,
                        current_price=current_price,
                        reason=reason
                    )

                    if result.status == CryptoOrderStatus.FILLED:
                        # Update position
                        position.exit_price = result.filled_price
                        position.exit_reason = reason
                        position.closed_at = datetime.utcnow()
                        position.exit_order_id = result.order_id

                        # Calculate P&L
                        pnl = (result.filled_price - position.entry_price) * position.quantity
                        position.realized_pnl = pnl

                        # Set status based on reason
                        if reason == "stop_loss":
                            position.status = CryptoPositionStatus.STOPPED_OUT
                        elif reason == "take_profit":
                            position.status = CryptoPositionStatus.TARGET_HIT
                        else:
                            position.status = CryptoPositionStatus.CLOSED

                        # Record trade for Kelly updates
                        self.risk_manager.record_trade(
                            symbol=position.symbol,
                            entry_price=position.entry_price,
                            exit_price=result.filled_price,
                            pnl=pnl
                        )

                        # Create trade record
                        trade = CryptoTrade(
                            agent_id=self.agent_id,
                            position_id=position.id,
                            symbol=position.symbol,
                            side="sell",
                            quantity=result.filled_quantity,
                            price=result.filled_price,
                            notional_value=result.filled_price * result.filled_quantity,
                            order_id=result.order_id,
                            order_type=result.order_type,
                            status=DbOrderStatus.FILLED,
                            pnl=pnl,
                            executed_at=datetime.utcnow()
                        )
                        self.db.add(trade)

                        # Update daily P&L
                        today = date.today()
                        self._daily_pnl[today] = self._daily_pnl.get(today, 0) + pnl

                        closed += 1

                        logger.info(
                            "Crypto position closed",
                            symbol=position.symbol,
                            reason=reason,
                            pnl=pnl
                        )
                else:
                    # Update unrealized P&L
                    position.unrealized_pnl = (current_price - position.entry_price) * position.quantity

            except Exception as e:
                logger.error(
                    "Error managing crypto position",
                    symbol=position.symbol,
                    error=str(e)
                )

        if closed > 0:
            self.db.commit()

        return closed

    async def _get_risk_status(self) -> CryptoRiskStatus:
        """Get current risk status from database positions"""
        positions = self.db.query(CryptoPosition).filter(
            and_(
                CryptoPosition.agent_id == self.agent_id,
                CryptoPosition.status == CryptoPositionStatus.OPEN
            )
        ).all()

        deployed_capital = sum(p.allocated_amount for p in positions)
        daily_pnl = self._get_daily_pnl()

        return self.risk_manager.get_risk_status(
            deployed_capital=deployed_capital,
            open_positions=len(positions),
            daily_pnl=daily_pnl
        )

    def _get_daily_pnl(self) -> float:
        """Get today's realized + unrealized P&L"""
        today = date.today()
        return self._daily_pnl.get(today, 0)

    async def _update_agent_last_run(self):
        """Update the agent's last run timestamp"""
        agent = self.db.query(Agent).filter(Agent.id == self.agent_id).first()
        if agent:
            agent.last_run_at = datetime.utcnow()
            self.db.commit()

    # ============================================================
    # Public API Methods
    # ============================================================

    async def get_state(self) -> CryptoHunterState:
        """Get current state of the Crypto Hunter agent"""
        risk_status = await self._get_risk_status()

        agent = self.db.query(Agent).filter(Agent.id == self.agent_id).first()

        watchlist_count = self.db.query(CryptoWatchlist).filter(
            and_(
                CryptoWatchlist.agent_id == self.agent_id,
                CryptoWatchlist.status == CryptoWatchlistStatus.WATCHING
            )
        ).count()

        total_pnl = sum(self._daily_pnl.values())

        last_position = self.db.query(CryptoPosition).filter(
            CryptoPosition.agent_id == self.agent_id
        ).order_by(CryptoPosition.created_at.desc()).first()

        return CryptoHunterState(
            agent_id=self.agent_id,
            status=agent.status.value if agent else "unknown",
            allocated_capital=self.risk_manager.allocated_capital,
            deployed_capital=risk_status.deployed_capital,
            available_capital=risk_status.available_capital,
            daily_pnl=risk_status.daily_pnl,
            total_pnl=total_pnl,
            open_positions=risk_status.open_positions,
            max_positions=risk_status.max_positions,
            watchlist_count=watchlist_count,
            last_scan=self._last_scan,
            last_trade=last_position.created_at if last_position else None,
            is_trading_enabled=self.auto_trade and not risk_status.is_daily_limit_hit,
            risk_status=risk_status
        )

    async def get_watchlist(self) -> List[Dict[str, Any]]:
        """Get current watchlist entries"""
        entries = self.db.query(CryptoWatchlist).filter(
            and_(
                CryptoWatchlist.agent_id == self.agent_id,
                CryptoWatchlist.status == CryptoWatchlistStatus.WATCHING
            )
        ).order_by(CryptoWatchlist.composite_score.desc()).all()

        return [
            {
                "id": e.id,
                "symbol": e.symbol,
                "composite_score": e.composite_score,
                "trend_score": e.trend_score,
                "fundamental_score": e.fundamental_score,
                "momentum_score": e.momentum_score,
                "entry_price": e.entry_price,
                "target_price": e.target_price,
                "stop_loss": e.stop_loss,
                "entry_trigger": e.entry_trigger,
                "created_at": e.created_at.isoformat() if e.created_at else None
            }
            for e in entries
        ]

    async def get_positions(self) -> List[Dict[str, Any]]:
        """Get current open positions"""
        positions = self.db.query(CryptoPosition).filter(
            and_(
                CryptoPosition.agent_id == self.agent_id,
                CryptoPosition.status == CryptoPositionStatus.OPEN
            )
        ).all()

        result = []
        for p in positions:
            # Get current price
            quote = await self.client.get_quote(p.symbol)
            current_price = quote.mark_price if quote else p.current_price

            unrealized_pnl = None
            if current_price:
                unrealized_pnl = (current_price - p.entry_price) * p.quantity

            result.append({
                "id": p.id,
                "symbol": p.symbol,
                "side": p.side,
                "quantity": p.quantity,
                "entry_price": p.entry_price,
                "current_price": current_price,
                "stop_loss": p.stop_loss,
                "take_profit": p.take_profit,
                "unrealized_pnl": unrealized_pnl,
                "allocated_amount": p.allocated_amount,
                "created_at": p.created_at.isoformat() if p.created_at else None
            })

        return result

    async def get_trade_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent trade history"""
        positions = self.db.query(CryptoPosition).filter(
            and_(
                CryptoPosition.agent_id == self.agent_id,
                CryptoPosition.status != CryptoPositionStatus.OPEN
            )
        ).order_by(CryptoPosition.closed_at.desc()).limit(limit).all()

        return [
            {
                "id": p.id,
                "symbol": p.symbol,
                "side": p.side,
                "quantity": p.quantity,
                "entry_price": p.entry_price,
                "exit_price": p.exit_price,
                "realized_pnl": p.realized_pnl,
                "status": p.status.value if p.status else None,
                "entry_reason": p.entry_reason,
                "exit_reason": p.exit_reason,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "closed_at": p.closed_at.isoformat() if p.closed_at else None
            }
            for p in positions
        ]

    async def manual_scan(self) -> Dict[str, Any]:
        """Trigger a manual market scan"""
        return await self.run_cycle()

    async def add_to_watchlist(self, symbol: str) -> Dict[str, Any]:
        """Manually add a symbol to the watchlist"""
        # Format symbol if needed
        if not symbol.endswith("-USD"):
            symbol = f"{symbol.upper()}-USD"

        # Get quote
        quote = await self.client.get_quote(symbol)
        if not quote:
            return {"success": False, "message": f"Could not get quote for {symbol}"}

        current_price = quote.mark_price

        # Create analysis
        stop_loss = self.risk_manager.calculate_stop_loss(current_price)
        target_price = self.risk_manager.calculate_take_profit(current_price, stop_loss)

        # Add to watchlist
        entry = CryptoWatchlist(
            agent_id=self.agent_id,
            symbol=symbol,
            composite_score=60,  # Default score for manual add
            trend_score=50,
            fundamental_score=50,
            momentum_score=50,
            entry_price=current_price,
            target_price=target_price,
            stop_loss=stop_loss,
            entry_trigger="manual",
            analysis_json={"reasoning": "Manually added"},
            status=CryptoWatchlistStatus.WATCHING
        )
        self.db.add(entry)
        self.db.commit()

        return {
            "success": True,
            "message": f"Added {symbol} to watchlist",
            "entry": {
                "symbol": symbol,
                "entry_price": current_price,
                "target_price": target_price,
                "stop_loss": stop_loss
            }
        }

    async def remove_from_watchlist(self, symbol: str) -> Dict[str, Any]:
        """Remove a symbol from the watchlist"""
        entry = self.db.query(CryptoWatchlist).filter(
            and_(
                CryptoWatchlist.agent_id == self.agent_id,
                CryptoWatchlist.symbol == symbol,
                CryptoWatchlist.status == CryptoWatchlistStatus.WATCHING
            )
        ).first()

        if entry:
            entry.status = CryptoWatchlistStatus.REMOVED
            entry.updated_at = datetime.utcnow()
            self.db.commit()
            return {"success": True, "message": f"Removed {symbol} from watchlist"}

        return {"success": False, "message": f"{symbol} not found in watchlist"}

    async def close_position(self, position_id: int) -> Dict[str, Any]:
        """Manually close a position"""
        position = self.db.query(CryptoPosition).filter(
            and_(
                CryptoPosition.id == position_id,
                CryptoPosition.agent_id == self.agent_id,
                CryptoPosition.status == CryptoPositionStatus.OPEN
            )
        ).first()

        if not position:
            return {"success": False, "message": "Position not found"}

        # Get current price
        quote = await self.client.get_quote(position.symbol)
        current_price = quote.mark_price if quote else None

        result = await self.executor.execute_exit(
            symbol=position.symbol,
            quantity=position.quantity,
            current_price=current_price,
            reason="manual"
        )

        if result.status == CryptoOrderStatus.FILLED:
            position.exit_price = result.filled_price
            position.exit_reason = "manual"
            position.closed_at = datetime.utcnow()
            position.realized_pnl = (result.filled_price - position.entry_price) * position.quantity
            position.status = CryptoPositionStatus.CLOSED
            position.exit_order_id = result.order_id
            self.db.commit()

            return {
                "success": True,
                "message": f"Closed position in {position.symbol}",
                "pnl": position.realized_pnl
            }

        return {"success": False, "message": f"Failed to close: {result.message}"}
