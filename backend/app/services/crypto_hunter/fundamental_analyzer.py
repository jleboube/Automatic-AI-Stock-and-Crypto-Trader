"""
Fundamental Analyzer for Crypto Hunter

Analyzes crypto fundamentals and market metrics.
Compares assets based on market cap, volume, and correlations.
"""

import structlog
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

logger = structlog.get_logger()


class FundamentalRating(str, Enum):
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    UNKNOWN = "unknown"


@dataclass
class FundamentalMetric:
    """Individual fundamental metric"""
    name: str
    value: float
    percentile: float  # 0-100, where 100 is best
    rating: FundamentalRating
    description: str


@dataclass
class FundamentalAnalysis:
    """Complete fundamental analysis for a crypto asset"""
    symbol: str
    score: float  # 0-100 fundamental score
    rating: FundamentalRating

    # Market metrics
    market_cap_rank: Optional[int]
    volume_24h: Optional[float]
    volume_ratio: Optional[float]  # Current volume / avg volume
    volume_percentile: float

    # Price position
    price_percentile: float  # Position in 52-week range (0-100)
    distance_from_ath: Optional[float]  # % from all-time high
    distance_from_atl: Optional[float]  # % from all-time low

    # Correlations
    btc_correlation: Optional[float]  # -1 to 1
    eth_correlation: Optional[float]  # -1 to 1

    # Momentum metrics
    price_change_1h: Optional[float]
    price_change_24h: Optional[float]
    price_change_7d: Optional[float]
    price_change_30d: Optional[float]

    # Individual metrics
    metrics: List[FundamentalMetric]

    # Summary
    summary: str
    timestamp: datetime


class FundamentalAnalyzer:
    """
    Analyzes crypto fundamentals and market metrics.

    Metrics analyzed:
    - Market cap ranking
    - Volume vs historical average
    - Price position in 52-week range
    - Correlation with BTC/ETH
    - Momentum across timeframes
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize fundamental analyzer.

        Config options:
        - fundamental_weight: Weight in composite score (default: 0.30)
        - min_volume_ratio: Minimum volume ratio for interest (default: 1.0)
        - prefer_uncorrelated: Favor less correlated assets (default: False)
        """
        self.config = config
        self.min_volume_ratio = config.get("min_volume_ratio", 1.0)
        self.prefer_uncorrelated = config.get("prefer_uncorrelated", False)

        # Cache for market data
        self._market_data_cache: Dict[str, Dict] = {}
        self._cache_timestamp: Optional[datetime] = None

    def analyze(
        self,
        symbol: str,
        current_price: float,
        volume_24h: Optional[float] = None,
        avg_volume: Optional[float] = None,
        high_52w: Optional[float] = None,
        low_52w: Optional[float] = None,
        market_cap_rank: Optional[int] = None,
        price_changes: Optional[Dict[str, float]] = None,
        btc_prices: Optional[List[float]] = None,
        eth_prices: Optional[List[float]] = None,
        asset_prices: Optional[List[float]] = None
    ) -> FundamentalAnalysis:
        """
        Analyze fundamentals for a crypto asset.

        Args:
            symbol: Trading pair symbol (e.g., "BTC-USD")
            current_price: Current price
            volume_24h: 24-hour trading volume in USD
            avg_volume: Average volume for comparison
            high_52w: 52-week high price
            low_52w: 52-week low price
            market_cap_rank: Market cap ranking
            price_changes: Dict with keys like '1h', '24h', '7d', '30d'
            btc_prices: BTC price history for correlation
            eth_prices: ETH price history for correlation
            asset_prices: Asset price history for correlation

        Returns:
            FundamentalAnalysis with complete fundamental information
        """
        metrics = []
        price_changes = price_changes or {}

        # Volume analysis
        volume_ratio = None
        volume_percentile = 50.0
        if volume_24h and avg_volume and avg_volume > 0:
            volume_ratio = volume_24h / avg_volume
            # Higher ratio = better (more activity)
            volume_percentile = min(100, volume_ratio * 50)  # 2x avg = 100%

            rating = self._rate_value(volume_percentile)
            metrics.append(FundamentalMetric(
                name="Volume Ratio",
                value=volume_ratio,
                percentile=volume_percentile,
                rating=rating,
                description=f"Volume is {volume_ratio:.1f}x average"
            ))

        # Price position in range
        price_percentile = 50.0
        distance_from_ath = None
        distance_from_atl = None

        if high_52w and low_52w and high_52w > low_52w:
            price_range = high_52w - low_52w
            if price_range > 0:
                price_percentile = ((current_price - low_52w) / price_range) * 100
                price_percentile = max(0, min(100, price_percentile))

            distance_from_ath = ((high_52w - current_price) / high_52w) * 100
            distance_from_atl = ((current_price - low_52w) / low_52w) * 100 if low_52w > 0 else None

            # For value plays, lower percentile might be attractive
            # For momentum, higher percentile is preferred
            rating = self._rate_value(price_percentile)
            metrics.append(FundamentalMetric(
                name="Price Position",
                value=price_percentile,
                percentile=price_percentile,
                rating=rating,
                description=f"At {price_percentile:.0f}% of 52-week range"
            ))

        # Market cap rank
        rank_percentile = 50.0
        if market_cap_rank:
            # Top 10 = excellent, top 50 = good, top 100 = moderate
            if market_cap_rank <= 10:
                rank_percentile = 95
            elif market_cap_rank <= 50:
                rank_percentile = 80
            elif market_cap_rank <= 100:
                rank_percentile = 60
            elif market_cap_rank <= 250:
                rank_percentile = 40
            else:
                rank_percentile = 20

            rating = self._rate_value(rank_percentile)
            metrics.append(FundamentalMetric(
                name="Market Cap Rank",
                value=market_cap_rank,
                percentile=rank_percentile,
                rating=rating,
                description=f"Ranked #{market_cap_rank} by market cap"
            ))

        # Correlations
        btc_correlation = None
        eth_correlation = None

        if asset_prices and len(asset_prices) >= 10:
            if btc_prices and len(btc_prices) >= 10:
                btc_correlation = self._calculate_correlation(asset_prices, btc_prices)
            if eth_prices and len(eth_prices) >= 10:
                eth_correlation = self._calculate_correlation(asset_prices, eth_prices)

        # Momentum analysis
        momentum_score = 50.0
        momentum_signals = []

        change_1h = price_changes.get("1h")
        change_24h = price_changes.get("24h")
        change_7d = price_changes.get("7d")
        change_30d = price_changes.get("30d")

        if change_24h is not None:
            if change_24h > 5:
                momentum_signals.append("strong 24h gain")
            elif change_24h > 0:
                momentum_signals.append("positive 24h")
            elif change_24h < -5:
                momentum_signals.append("strong 24h drop")

        if change_7d is not None:
            if change_7d > 10:
                momentum_signals.append("strong weekly gain")
            elif change_7d < -10:
                momentum_signals.append("strong weekly drop")

        # Calculate momentum percentile
        if change_24h is not None and change_7d is not None:
            # Combine short and medium term momentum
            momentum_score = 50 + (change_24h * 2) + (change_7d * 0.5)
            momentum_score = max(0, min(100, momentum_score))

            rating = self._rate_value(momentum_score)
            metrics.append(FundamentalMetric(
                name="Momentum",
                value=momentum_score,
                percentile=momentum_score,
                rating=rating,
                description=", ".join(momentum_signals) if momentum_signals else "Neutral momentum"
            ))

        # Calculate overall score
        score = self._calculate_score(metrics)
        overall_rating = self._rate_value(score)

        # Generate summary
        summary = self._generate_summary(
            symbol, score, overall_rating, metrics,
            volume_ratio, price_percentile, market_cap_rank
        )

        return FundamentalAnalysis(
            symbol=symbol,
            score=score,
            rating=overall_rating,
            market_cap_rank=market_cap_rank,
            volume_24h=volume_24h,
            volume_ratio=volume_ratio,
            volume_percentile=volume_percentile,
            price_percentile=price_percentile,
            distance_from_ath=distance_from_ath,
            distance_from_atl=distance_from_atl,
            btc_correlation=btc_correlation,
            eth_correlation=eth_correlation,
            price_change_1h=change_1h,
            price_change_24h=change_24h,
            price_change_7d=change_7d,
            price_change_30d=change_30d,
            metrics=metrics,
            summary=summary,
            timestamp=datetime.now()
        )

    def _calculate_correlation(
        self,
        prices1: List[float],
        prices2: List[float]
    ) -> Optional[float]:
        """Calculate Pearson correlation between two price series"""
        n = min(len(prices1), len(prices2))
        if n < 5:
            return None

        # Use returns instead of prices
        returns1 = [(prices1[i] - prices1[i-1]) / prices1[i-1]
                    for i in range(1, n) if prices1[i-1] != 0]
        returns2 = [(prices2[i] - prices2[i-1]) / prices2[i-1]
                    for i in range(1, n) if prices2[i-1] != 0]

        if len(returns1) < 5 or len(returns2) < 5:
            return None

        n = min(len(returns1), len(returns2))
        returns1 = returns1[:n]
        returns2 = returns2[:n]

        mean1 = sum(returns1) / n
        mean2 = sum(returns2) / n

        cov = sum((returns1[i] - mean1) * (returns2[i] - mean2) for i in range(n)) / n
        std1 = (sum((r - mean1) ** 2 for r in returns1) / n) ** 0.5
        std2 = (sum((r - mean2) ** 2 for r in returns2) / n) ** 0.5

        if std1 == 0 or std2 == 0:
            return None

        correlation = cov / (std1 * std2)
        return max(-1, min(1, correlation))

    def _rate_value(self, percentile: float) -> FundamentalRating:
        """Rate a percentile value"""
        if percentile >= 70:
            return FundamentalRating.STRONG
        elif percentile >= 40:
            return FundamentalRating.MODERATE
        elif percentile >= 0:
            return FundamentalRating.WEAK
        else:
            return FundamentalRating.UNKNOWN

    def _calculate_score(self, metrics: List[FundamentalMetric]) -> float:
        """Calculate overall fundamental score"""
        if not metrics:
            return 50.0

        # Weight different metrics
        weights = {
            "Volume Ratio": 0.25,
            "Price Position": 0.20,
            "Market Cap Rank": 0.25,
            "Momentum": 0.30
        }

        total_weight = 0
        weighted_sum = 0

        for metric in metrics:
            weight = weights.get(metric.name, 0.25)
            weighted_sum += metric.percentile * weight
            total_weight += weight

        if total_weight == 0:
            return 50.0

        return weighted_sum / total_weight

    def _generate_summary(
        self,
        symbol: str,
        score: float,
        rating: FundamentalRating,
        metrics: List[FundamentalMetric],
        volume_ratio: Optional[float],
        price_percentile: float,
        market_cap_rank: Optional[int]
    ) -> str:
        """Generate human-readable summary"""
        parts = [f"{symbol}: {rating.value.title()} fundamentals (score: {score:.0f})"]

        if market_cap_rank:
            if market_cap_rank <= 10:
                parts.append(f"Top 10 crypto by market cap")
            elif market_cap_rank <= 50:
                parts.append(f"Top 50 crypto")

        if volume_ratio:
            if volume_ratio > 2:
                parts.append(f"Unusual volume ({volume_ratio:.1f}x avg)")
            elif volume_ratio > 1.5:
                parts.append(f"Above-average volume")

        if price_percentile < 30:
            parts.append("Near 52-week lows (potential value)")
        elif price_percentile > 80:
            parts.append("Near 52-week highs (momentum)")

        # Add strong/weak metrics
        strong = [m.name for m in metrics if m.rating == FundamentalRating.STRONG]
        weak = [m.name for m in metrics if m.rating == FundamentalRating.WEAK]

        if strong:
            parts.append(f"Strengths: {', '.join(strong)}")
        if weak:
            parts.append(f"Weaknesses: {', '.join(weak)}")

        return ". ".join(parts)

    def compare_assets(
        self,
        analyses: List[FundamentalAnalysis]
    ) -> List[FundamentalAnalysis]:
        """
        Compare multiple assets and rank them.

        Returns list sorted by fundamental score (highest first).
        """
        return sorted(analyses, key=lambda a: a.score, reverse=True)
