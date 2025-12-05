"""
Market Screener using Yahoo Finance

Screens for potential "hidden gems" based on technical, fundamental, and momentum criteria.
"""

import yfinance as yf
import pandas as pd
import structlog
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta

logger = structlog.get_logger()


@dataclass
class ScreenerResult:
    """Result from screening a single stock"""
    symbol: str
    current_price: float
    market_cap: float
    pe_ratio: Optional[float]
    revenue_growth: Optional[float]
    earnings_growth: Optional[float]
    rsi: float
    volume_ratio: float  # Current volume vs 20-day average
    distance_from_52w_high: float  # % below 52-week high
    distance_from_52w_low: float  # % above 52-week low
    sma_20: float
    sma_50: float
    sma_200: float
    avg_volume: float
    sector: Optional[str]
    industry: Optional[str]


class GemScreener:
    """
    Screens the market for potential hidden gems using Yahoo Finance data.

    Screening criteria:
    - Technical: RSI, moving averages, volume patterns
    - Fundamental: P/E, revenue growth, earnings
    - Momentum: Price relative to moving averages, volume surge
    """

    # Default universe - can be customized
    DEFAULT_UNIVERSE = [
        # Large cap tech that can still move
        "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA",
        # Growth stocks
        "CRM", "ADBE", "NOW", "SNOW", "DDOG", "NET", "CRWD",
        # Semiconductors
        "AMD", "AVGO", "MRVL", "QCOM", "MU", "LRCX", "AMAT",
        # Financials
        "JPM", "BAC", "GS", "MS", "V", "MA", "PYPL",
        # Healthcare/Biotech
        "UNH", "JNJ", "PFE", "ABBV", "MRK", "LLY", "AMGN",
        # Consumer
        "COST", "WMT", "TGT", "HD", "LOW", "NKE", "SBUX",
        # Industrial
        "CAT", "DE", "HON", "UPS", "FDX", "BA", "GE",
        # Energy
        "XOM", "CVX", "COP", "SLB", "OXY",
        # Other high-potential
        "PLTR", "COIN", "SQ", "SHOP", "ROKU", "ZM", "DOCU"
    ]

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize screener with configuration.

        Config options:
        - min_market_cap: Minimum market cap (default: $1B)
        - min_avg_volume: Minimum average daily volume (default: 500K)
        - universe: List of symbols to screen (optional)
        """
        self.config = config
        self.min_market_cap = config.get("min_market_cap", 1_000_000_000)
        self.min_avg_volume = config.get("min_avg_volume", 500_000)
        self.universe = config.get("universe", self.DEFAULT_UNIVERSE)

    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> float:
        """Calculate RSI for a price series"""
        try:
            delta = prices.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            return rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50.0
        except Exception:
            return 50.0  # Neutral default

    def _get_stock_data(self, symbol: str) -> Optional[ScreenerResult]:
        """Fetch and analyze data for a single stock"""
        try:
            ticker = yf.Ticker(symbol)

            # Get historical data (6 months for moving averages)
            hist = ticker.history(period="6mo")
            if hist.empty or len(hist) < 50:
                return None

            # Get info
            info = ticker.info

            # Current price
            current_price = hist['Close'].iloc[-1]

            # Market cap check
            market_cap = info.get('marketCap', 0)
            if market_cap < self.min_market_cap:
                return None

            # Volume check
            avg_volume = hist['Volume'].tail(20).mean()
            if avg_volume < self.min_avg_volume:
                return None

            # Calculate technical indicators
            rsi = self._calculate_rsi(hist['Close'])

            # Moving averages
            sma_20 = hist['Close'].tail(20).mean()
            sma_50 = hist['Close'].tail(50).mean()
            sma_200 = hist['Close'].tail(200).mean() if len(hist) >= 200 else hist['Close'].mean()

            # Volume ratio (today vs 20-day average)
            current_volume = hist['Volume'].iloc[-1]
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0

            # 52-week high/low
            high_52w = info.get('fiftyTwoWeekHigh', current_price)
            low_52w = info.get('fiftyTwoWeekLow', current_price)

            distance_from_high = ((high_52w - current_price) / high_52w * 100) if high_52w > 0 else 0
            distance_from_low = ((current_price - low_52w) / low_52w * 100) if low_52w > 0 else 0

            # Fundamental data
            pe_ratio = info.get('trailingPE')
            revenue_growth = info.get('revenueGrowth')
            earnings_growth = info.get('earningsGrowth')

            return ScreenerResult(
                symbol=symbol,
                current_price=current_price,
                market_cap=market_cap,
                pe_ratio=pe_ratio,
                revenue_growth=revenue_growth,
                earnings_growth=earnings_growth,
                rsi=rsi,
                volume_ratio=volume_ratio,
                distance_from_52w_high=distance_from_high,
                distance_from_52w_low=distance_from_low,
                sma_20=sma_20,
                sma_50=sma_50,
                sma_200=sma_200,
                avg_volume=avg_volume,
                sector=info.get('sector'),
                industry=info.get('industry')
            )

        except Exception as e:
            logger.warning("Failed to get stock data", symbol=symbol, error=str(e))
            return None

    def screen_market(self) -> List[ScreenerResult]:
        """
        Screen the market universe and return all stocks that pass initial filters.
        """
        results = []

        logger.info("Starting market screen", universe_size=len(self.universe))

        for symbol in self.universe:
            result = self._get_stock_data(symbol)
            if result:
                results.append(result)

        logger.info("Market screen complete", candidates=len(results))
        return results

    def find_oversold_gems(self, results: List[ScreenerResult] = None) -> List[ScreenerResult]:
        """
        Find oversold stocks with potential for reversal.

        Criteria:
        - RSI < 35 (oversold)
        - Price above 200-day MA (still in long-term uptrend)
        - Volume surge (volume_ratio > 1.5)
        """
        if results is None:
            results = self.screen_market()

        oversold = [
            r for r in results
            if r.rsi < 35
            and r.current_price > r.sma_200
            and r.volume_ratio > 1.5
        ]

        logger.info("Found oversold gems", count=len(oversold))
        return sorted(oversold, key=lambda x: x.rsi)

    def find_breakout_candidates(self, results: List[ScreenerResult] = None) -> List[ScreenerResult]:
        """
        Find stocks poised for breakout.

        Criteria:
        - Price within 5% of 52-week high
        - RSI between 50-70 (not overbought)
        - Volume surge (volume_ratio > 2.0)
        - Above all major moving averages
        """
        if results is None:
            results = self.screen_market()

        breakouts = [
            r for r in results
            if r.distance_from_52w_high < 5  # Within 5% of high
            and 50 < r.rsi < 70
            and r.volume_ratio > 2.0
            and r.current_price > r.sma_20
            and r.current_price > r.sma_50
        ]

        logger.info("Found breakout candidates", count=len(breakouts))
        return sorted(breakouts, key=lambda x: -x.volume_ratio)

    def find_value_plays(self, results: List[ScreenerResult] = None) -> List[ScreenerResult]:
        """
        Find undervalued stocks with growth potential.

        Criteria:
        - P/E < 20 (or None for growth stocks)
        - Revenue growth > 10%
        - Down >15% from 52-week high
        - RSI < 50
        """
        if results is None:
            results = self.screen_market()

        value_plays = [
            r for r in results
            if (r.pe_ratio is None or r.pe_ratio < 20)
            and (r.revenue_growth is not None and r.revenue_growth > 0.10)
            and r.distance_from_52w_high > 15
            and r.rsi < 50
        ]

        logger.info("Found value plays", count=len(value_plays))
        return sorted(value_plays, key=lambda x: x.distance_from_52w_high, reverse=True)

    def find_momentum_plays(self, results: List[ScreenerResult] = None) -> List[ScreenerResult]:
        """
        Find stocks with strong momentum.

        Criteria:
        - Price above 20, 50, and 200-day MA
        - RSI between 55-75
        - Recent volume surge
        - Up from 52-week low > 20%
        """
        if results is None:
            results = self.screen_market()

        momentum = [
            r for r in results
            if r.current_price > r.sma_20
            and r.current_price > r.sma_50
            and r.current_price > r.sma_200
            and 55 < r.rsi < 75
            and r.volume_ratio > 1.5
            and r.distance_from_52w_low > 20
        ]

        logger.info("Found momentum plays", count=len(momentum))
        return sorted(momentum, key=lambda x: -x.distance_from_52w_low)
