"""
Trend Analyzer for Crypto Hunter

Analyzes crypto price trends using technical indicators.
Works with price data fetched from the Robinhood API.
"""

import structlog
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

logger = structlog.get_logger()


class TrendDirection(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


@dataclass
class TrendSignal:
    """Individual trend signal from an indicator"""
    indicator: str
    signal: str  # bullish, bearish, neutral
    value: float
    description: str


@dataclass
class TrendAnalysis:
    """Complete trend analysis for a crypto asset"""
    symbol: str
    direction: TrendDirection
    strength: float  # 0-100
    score: float  # 0-100 trend score
    current_price: float

    # Key price levels
    support_levels: List[float]
    resistance_levels: List[float]

    # Moving averages
    ema_9: Optional[float]
    ema_21: Optional[float]
    ema_50: Optional[float]
    ema_200: Optional[float]

    # Indicators
    rsi: Optional[float]
    macd_value: Optional[float]
    macd_signal: Optional[float]
    macd_histogram: Optional[float]

    # Bollinger Bands
    bb_upper: Optional[float]
    bb_middle: Optional[float]
    bb_lower: Optional[float]

    # Signals
    signals: List[TrendSignal]

    # Summary
    summary: str
    timestamp: datetime


class TrendAnalyzer:
    """
    Analyzes crypto price trends using technical indicators.

    Indicators used:
    - Moving Averages (EMA 9, 21, 50, 200)
    - RSI (14-period)
    - MACD (12, 26, 9)
    - Bollinger Bands (20, 2)
    - Support/Resistance levels
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize trend analyzer.

        Config options:
        - rsi_oversold: RSI level considered oversold (default: 30)
        - rsi_overbought: RSI level considered overbought (default: 70)
        - trend_weight: Weight of trend in composite score (default: 0.50)
        """
        self.config = config
        self.rsi_oversold = config.get("rsi_oversold", 30)
        self.rsi_overbought = config.get("rsi_overbought", 70)

    def analyze(
        self,
        symbol: str,
        prices: List[float],
        volumes: Optional[List[float]] = None,
        current_price: Optional[float] = None
    ) -> TrendAnalysis:
        """
        Analyze price trend for a crypto asset.

        Args:
            symbol: Trading pair symbol (e.g., "BTC-USD")
            prices: Historical prices (oldest to newest)
            volumes: Historical volumes (optional)
            current_price: Current price (defaults to last price)

        Returns:
            TrendAnalysis with complete trend information
        """
        if not prices or len(prices) < 21:
            return self._empty_analysis(symbol, current_price or 0)

        current = current_price or prices[-1]
        signals = []

        # Calculate EMAs
        ema_9 = self._calculate_ema(prices, 9)
        ema_21 = self._calculate_ema(prices, 21)
        ema_50 = self._calculate_ema(prices, 50) if len(prices) >= 50 else None
        ema_200 = self._calculate_ema(prices, 200) if len(prices) >= 200 else None

        # EMA signals
        if ema_9 and ema_21:
            if ema_9 > ema_21:
                signals.append(TrendSignal(
                    indicator="EMA Cross",
                    signal="bullish",
                    value=ema_9 - ema_21,
                    description="EMA 9 above EMA 21"
                ))
            else:
                signals.append(TrendSignal(
                    indicator="EMA Cross",
                    signal="bearish",
                    value=ema_9 - ema_21,
                    description="EMA 9 below EMA 21"
                ))

        # Price vs EMAs
        if ema_50:
            if current > ema_50:
                signals.append(TrendSignal(
                    indicator="Price vs EMA50",
                    signal="bullish",
                    value=(current - ema_50) / ema_50 * 100,
                    description="Price above EMA 50"
                ))
            else:
                signals.append(TrendSignal(
                    indicator="Price vs EMA50",
                    signal="bearish",
                    value=(current - ema_50) / ema_50 * 100,
                    description="Price below EMA 50"
                ))

        # Calculate RSI
        rsi = self._calculate_rsi(prices, 14)
        if rsi:
            if rsi < self.rsi_oversold:
                signals.append(TrendSignal(
                    indicator="RSI",
                    signal="bullish",
                    value=rsi,
                    description=f"RSI oversold at {rsi:.1f}"
                ))
            elif rsi > self.rsi_overbought:
                signals.append(TrendSignal(
                    indicator="RSI",
                    signal="bearish",
                    value=rsi,
                    description=f"RSI overbought at {rsi:.1f}"
                ))
            else:
                signals.append(TrendSignal(
                    indicator="RSI",
                    signal="neutral",
                    value=rsi,
                    description=f"RSI neutral at {rsi:.1f}"
                ))

        # Calculate MACD
        macd_value, macd_signal, macd_hist = self._calculate_macd(prices)
        if macd_value is not None and macd_signal is not None:
            if macd_value > macd_signal:
                signals.append(TrendSignal(
                    indicator="MACD",
                    signal="bullish",
                    value=macd_hist or 0,
                    description="MACD above signal line"
                ))
            else:
                signals.append(TrendSignal(
                    indicator="MACD",
                    signal="bearish",
                    value=macd_hist or 0,
                    description="MACD below signal line"
                ))

        # Calculate Bollinger Bands
        bb_upper, bb_middle, bb_lower = self._calculate_bollinger_bands(prices, 20, 2)
        if bb_lower and bb_upper:
            bb_position = (current - bb_lower) / (bb_upper - bb_lower) if bb_upper != bb_lower else 0.5
            if bb_position < 0.2:
                signals.append(TrendSignal(
                    indicator="Bollinger Bands",
                    signal="bullish",
                    value=bb_position,
                    description="Price near lower Bollinger Band"
                ))
            elif bb_position > 0.8:
                signals.append(TrendSignal(
                    indicator="Bollinger Bands",
                    signal="bearish",
                    value=bb_position,
                    description="Price near upper Bollinger Band"
                ))

        # Calculate support/resistance
        support_levels = self._find_support_levels(prices)
        resistance_levels = self._find_resistance_levels(prices)

        # Determine overall direction and strength
        direction, strength = self._determine_trend(signals)

        # Calculate trend score (0-100)
        score = self._calculate_score(signals, direction, strength)

        # Generate summary
        summary = self._generate_summary(direction, strength, signals)

        return TrendAnalysis(
            symbol=symbol,
            direction=direction,
            strength=strength,
            score=score,
            current_price=current,
            support_levels=support_levels,
            resistance_levels=resistance_levels,
            ema_9=ema_9,
            ema_21=ema_21,
            ema_50=ema_50,
            ema_200=ema_200,
            rsi=rsi,
            macd_value=macd_value,
            macd_signal=macd_signal,
            macd_histogram=macd_hist,
            bb_upper=bb_upper,
            bb_middle=bb_middle,
            bb_lower=bb_lower,
            signals=signals,
            summary=summary,
            timestamp=datetime.now()
        )

    def _empty_analysis(self, symbol: str, price: float) -> TrendAnalysis:
        """Return empty analysis when insufficient data"""
        return TrendAnalysis(
            symbol=symbol,
            direction=TrendDirection.NEUTRAL,
            strength=0,
            score=50,
            current_price=price,
            support_levels=[],
            resistance_levels=[],
            ema_9=None,
            ema_21=None,
            ema_50=None,
            ema_200=None,
            rsi=None,
            macd_value=None,
            macd_signal=None,
            macd_histogram=None,
            bb_upper=None,
            bb_middle=None,
            bb_lower=None,
            signals=[],
            summary="Insufficient data for trend analysis",
            timestamp=datetime.now()
        )

    def _calculate_ema(self, prices: List[float], period: int) -> Optional[float]:
        """Calculate Exponential Moving Average"""
        if len(prices) < period:
            return None

        multiplier = 2 / (period + 1)
        ema = sum(prices[:period]) / period  # Start with SMA

        for price in prices[period:]:
            ema = (price * multiplier) + (ema * (1 - multiplier))

        return ema

    def _calculate_rsi(self, prices: List[float], period: int = 14) -> Optional[float]:
        """Calculate Relative Strength Index"""
        if len(prices) < period + 1:
            return None

        deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]

        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]

        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period

        if avg_loss == 0:
            return 100

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return rsi

    def _calculate_macd(
        self,
        prices: List[float],
        fast: int = 12,
        slow: int = 26,
        signal: int = 9
    ) -> tuple:
        """Calculate MACD (value, signal, histogram)"""
        if len(prices) < slow + signal:
            return None, None, None

        ema_fast = self._calculate_ema(prices, fast)
        ema_slow = self._calculate_ema(prices, slow)

        if ema_fast is None or ema_slow is None:
            return None, None, None

        macd_line = ema_fast - ema_slow

        # For signal line, we'd need historical MACD values
        # Simplified: estimate from recent prices
        signal_line = macd_line * 0.9  # Approximation
        histogram = macd_line - signal_line

        return macd_line, signal_line, histogram

    def _calculate_bollinger_bands(
        self,
        prices: List[float],
        period: int = 20,
        std_dev: int = 2
    ) -> tuple:
        """Calculate Bollinger Bands (upper, middle, lower)"""
        if len(prices) < period:
            return None, None, None

        recent = prices[-period:]
        middle = sum(recent) / period

        variance = sum((p - middle) ** 2 for p in recent) / period
        std = variance ** 0.5

        upper = middle + (std * std_dev)
        lower = middle - (std * std_dev)

        return upper, middle, lower

    def _find_support_levels(self, prices: List[float], num_levels: int = 3) -> List[float]:
        """Find support levels from price history"""
        if len(prices) < 10:
            return []

        # Find local minima
        minima = []
        for i in range(1, len(prices) - 1):
            if prices[i] < prices[i-1] and prices[i] < prices[i+1]:
                minima.append(prices[i])

        # Cluster and return top levels
        if not minima:
            return [min(prices)]

        minima.sort()
        return minima[:num_levels]

    def _find_resistance_levels(self, prices: List[float], num_levels: int = 3) -> List[float]:
        """Find resistance levels from price history"""
        if len(prices) < 10:
            return []

        # Find local maxima
        maxima = []
        for i in range(1, len(prices) - 1):
            if prices[i] > prices[i-1] and prices[i] > prices[i+1]:
                maxima.append(prices[i])

        # Cluster and return top levels
        if not maxima:
            return [max(prices)]

        maxima.sort(reverse=True)
        return maxima[:num_levels]

    def _determine_trend(self, signals: List[TrendSignal]) -> tuple:
        """Determine overall trend direction and strength"""
        if not signals:
            return TrendDirection.NEUTRAL, 0

        bullish_count = sum(1 for s in signals if s.signal == "bullish")
        bearish_count = sum(1 for s in signals if s.signal == "bearish")
        total = len(signals)

        if bullish_count > bearish_count:
            direction = TrendDirection.BULLISH
            strength = (bullish_count / total) * 100
        elif bearish_count > bullish_count:
            direction = TrendDirection.BEARISH
            strength = (bearish_count / total) * 100
        else:
            direction = TrendDirection.NEUTRAL
            strength = 50

        return direction, strength

    def _calculate_score(
        self,
        signals: List[TrendSignal],
        direction: TrendDirection,
        strength: float
    ) -> float:
        """Calculate trend score (0-100)"""
        if not signals:
            return 50

        # Base score from signal consensus
        bullish_count = sum(1 for s in signals if s.signal == "bullish")
        total = len(signals)

        # Score based on bullish ratio (50 = neutral, 100 = all bullish)
        base_score = 50 + (bullish_count / total - 0.5) * 100

        # Adjust by strength
        score = base_score * (0.5 + strength / 200)

        return max(0, min(100, score))

    def _generate_summary(
        self,
        direction: TrendDirection,
        strength: float,
        signals: List[TrendSignal]
    ) -> str:
        """Generate human-readable trend summary"""
        strength_desc = "weak" if strength < 40 else "moderate" if strength < 70 else "strong"

        bullish = [s for s in signals if s.signal == "bullish"]
        bearish = [s for s in signals if s.signal == "bearish"]

        summary = f"{strength_desc.title()} {direction.value} trend. "

        if bullish:
            summary += f"Bullish signals: {', '.join(s.indicator for s in bullish)}. "
        if bearish:
            summary += f"Bearish signals: {', '.join(s.indicator for s in bearish)}. "

        return summary.strip()
