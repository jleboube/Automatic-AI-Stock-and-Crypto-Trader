"""
Gem Analyzer

Scores potential gems using technical, fundamental, and momentum analysis.
Produces a composite score (0-100) for each candidate.
"""

import structlog
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

from .screener import ScreenerResult

logger = structlog.get_logger()


@dataclass
class GemAnalysis:
    """Complete analysis result for a stock"""
    symbol: str
    current_price: float

    # Individual scores (0-100)
    technical_score: float
    fundamental_score: float
    momentum_score: float
    composite_score: float

    # Trading levels
    entry_price: float
    target_price: float
    stop_loss: float

    # Risk/reward
    upside_potential: float  # % to target
    downside_risk: float  # % to stop
    risk_reward_ratio: float

    # Entry criteria
    entry_trigger: str  # "breakout", "pullback", "immediate"
    entry_conditions: Dict[str, Any]

    # Analysis reasoning
    reasoning: str

    # Raw data
    raw_data: ScreenerResult


class GemAnalyzer:
    """
    Analyzes screened stocks and produces scored recommendations.

    Scoring breakdown:
    - Technical (40%): RSI, moving averages, volume
    - Fundamental (30%): P/E, growth metrics, value
    - Momentum (30%): Trend strength, relative performance
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize analyzer with configuration.

        Config options:
        - technical_weight: Weight for technical score (default: 0.40)
        - fundamental_weight: Weight for fundamental score (default: 0.30)
        - momentum_weight: Weight for momentum score (default: 0.30)
        - stop_loss_pct: Default stop loss % (default: 0.08)
        - take_profit_pct: Default take profit % (default: 0.20)
        """
        self.config = config
        self.technical_weight = config.get("technical_weight", 0.40)
        self.fundamental_weight = config.get("fundamental_weight", 0.30)
        self.momentum_weight = config.get("momentum_weight", 0.30)
        self.stop_loss_pct = config.get("stop_loss_pct", 0.08)
        self.take_profit_pct = config.get("take_profit_pct", 0.20)

    def _score_technical(self, result: ScreenerResult) -> float:
        """
        Score technical factors (0-100).

        Factors:
        - RSI position (oversold = good, neutral = ok, overbought = bad)
        - Price vs moving averages
        - Volume confirmation
        """
        score = 50.0  # Start neutral

        # RSI scoring (oversold is bullish for entry)
        if result.rsi < 30:
            score += 25  # Very oversold - excellent entry
        elif result.rsi < 40:
            score += 15  # Oversold - good entry
        elif result.rsi < 50:
            score += 5  # Neutral-bearish
        elif result.rsi < 60:
            score += 0  # Neutral
        elif result.rsi < 70:
            score -= 10  # Getting overbought
        else:
            score -= 20  # Overbought - risky entry

        # Moving average alignment
        if result.current_price > result.sma_200:
            score += 10  # Above long-term trend
        else:
            score -= 15  # Below long-term trend

        if result.current_price > result.sma_50:
            score += 5
        if result.current_price > result.sma_20:
            score += 5

        # Golden/death cross proximity
        if result.sma_50 > result.sma_200:
            score += 5  # Bullish alignment
        else:
            score -= 5  # Bearish alignment

        # Volume confirmation
        if result.volume_ratio > 2.0:
            score += 15  # Strong volume
        elif result.volume_ratio > 1.5:
            score += 10  # Good volume
        elif result.volume_ratio > 1.0:
            score += 5  # Normal volume
        else:
            score -= 5  # Low volume

        return max(0, min(100, score))

    def _score_fundamental(self, result: ScreenerResult) -> float:
        """
        Score fundamental factors (0-100).

        Factors:
        - P/E ratio (value)
        - Revenue growth
        - Earnings growth
        - Distance from 52-week high (value opportunity)
        """
        score = 50.0

        # P/E scoring
        if result.pe_ratio is not None:
            if result.pe_ratio < 10:
                score += 20  # Very cheap
            elif result.pe_ratio < 15:
                score += 15  # Cheap
            elif result.pe_ratio < 20:
                score += 10  # Fair value
            elif result.pe_ratio < 30:
                score += 0  # Neutral
            elif result.pe_ratio < 50:
                score -= 10  # Expensive
            else:
                score -= 15  # Very expensive
        else:
            # No P/E (growth stock or unprofitable)
            score += 5  # Neutral, could be growth

        # Revenue growth
        if result.revenue_growth is not None:
            if result.revenue_growth > 0.30:
                score += 20  # Excellent growth
            elif result.revenue_growth > 0.20:
                score += 15
            elif result.revenue_growth > 0.10:
                score += 10
            elif result.revenue_growth > 0:
                score += 5
            else:
                score -= 10  # Declining revenue

        # Earnings growth
        if result.earnings_growth is not None:
            if result.earnings_growth > 0.30:
                score += 15
            elif result.earnings_growth > 0.15:
                score += 10
            elif result.earnings_growth > 0:
                score += 5
            else:
                score -= 10

        # Value opportunity (down from high)
        if result.distance_from_52w_high > 30:
            score += 10  # Significant pullback
        elif result.distance_from_52w_high > 20:
            score += 5

        return max(0, min(100, score))

    def _score_momentum(self, result: ScreenerResult) -> float:
        """
        Score momentum factors (0-100).

        Factors:
        - Trend direction
        - Relative strength
        - Distance from lows (uptrend strength)
        """
        score = 50.0

        # MA trend alignment
        if (result.current_price > result.sma_20 > result.sma_50 > result.sma_200):
            score += 25  # Perfect bullish alignment
        elif (result.current_price > result.sma_20 and result.current_price > result.sma_50):
            score += 15  # Good alignment
        elif result.current_price > result.sma_20:
            score += 5  # Short-term bullish
        elif result.current_price < result.sma_20 < result.sma_50:
            score -= 15  # Bearish alignment

        # Distance from 52-week low (higher = stronger momentum)
        if result.distance_from_52w_low > 50:
            score += 15
        elif result.distance_from_52w_low > 30:
            score += 10
        elif result.distance_from_52w_low > 15:
            score += 5
        elif result.distance_from_52w_low < 5:
            score -= 10  # Near lows

        # RSI momentum
        if 50 < result.rsi < 60:
            score += 10  # Healthy momentum
        elif 60 < result.rsi < 70:
            score += 5  # Strong momentum

        return max(0, min(100, score))

    def _determine_entry_trigger(self, result: ScreenerResult, tech_score: float) -> tuple:
        """Determine the best entry strategy"""
        if result.rsi < 35 and result.volume_ratio > 1.5:
            return "immediate", {
                "reason": "Oversold with volume confirmation",
                "wait_for": None
            }

        if result.distance_from_52w_high < 5 and result.volume_ratio > 2.0:
            return "breakout", {
                "reason": "Near highs with volume surge",
                "wait_for": f"Break above ${result.current_price * 1.02:.2f}"
            }

        if result.current_price < result.sma_20 and result.current_price > result.sma_50:
            return "pullback", {
                "reason": "Pullback to support in uptrend",
                "wait_for": f"Bounce from ${result.sma_50:.2f}"
            }

        return "immediate", {
            "reason": "Standard entry based on analysis",
            "wait_for": None
        }

    def _generate_reasoning(
        self,
        result: ScreenerResult,
        tech_score: float,
        fund_score: float,
        mom_score: float,
        composite: float
    ) -> str:
        """Generate human-readable analysis reasoning"""
        parts = []

        parts.append(f"**{result.symbol}** - Composite Score: {composite:.0f}/100\n")

        # Technical analysis
        parts.append(f"**Technical ({tech_score:.0f}/100):**")
        if result.rsi < 35:
            parts.append(f"- RSI at {result.rsi:.1f} indicates oversold conditions")
        elif result.rsi > 65:
            parts.append(f"- RSI at {result.rsi:.1f} suggests overbought, wait for pullback")
        else:
            parts.append(f"- RSI at {result.rsi:.1f} is neutral")

        if result.current_price > result.sma_200:
            parts.append("- Trading above 200-day MA (long-term bullish)")
        if result.volume_ratio > 1.5:
            parts.append(f"- Volume {result.volume_ratio:.1f}x above average (institutional interest)")

        # Fundamental analysis
        parts.append(f"\n**Fundamental ({fund_score:.0f}/100):**")
        if result.pe_ratio:
            parts.append(f"- P/E ratio: {result.pe_ratio:.1f}")
        if result.revenue_growth:
            parts.append(f"- Revenue growth: {result.revenue_growth * 100:.1f}%")
        parts.append(f"- Down {result.distance_from_52w_high:.1f}% from 52-week high")

        # Momentum
        parts.append(f"\n**Momentum ({mom_score:.0f}/100):**")
        parts.append(f"- Up {result.distance_from_52w_low:.1f}% from 52-week low")
        if result.sma_50 > result.sma_200:
            parts.append("- Golden cross (50 > 200 MA) intact")

        return "\n".join(parts)

    def analyze(self, result: ScreenerResult) -> GemAnalysis:
        """
        Perform complete analysis on a screened stock.

        Returns a GemAnalysis with scores and trading levels.
        """
        # Calculate individual scores
        tech_score = self._score_technical(result)
        fund_score = self._score_fundamental(result)
        mom_score = self._score_momentum(result)

        # Calculate composite score
        composite = (
            tech_score * self.technical_weight +
            fund_score * self.fundamental_weight +
            mom_score * self.momentum_weight
        )

        # Determine entry strategy
        entry_trigger, entry_conditions = self._determine_entry_trigger(result, tech_score)

        # Calculate trading levels
        entry_price = result.current_price
        stop_loss = entry_price * (1 - self.stop_loss_pct)
        target_price = entry_price * (1 + self.take_profit_pct)

        # Risk/reward
        upside = self.take_profit_pct * 100
        downside = self.stop_loss_pct * 100
        risk_reward = upside / downside if downside > 0 else 0

        # Generate reasoning
        reasoning = self._generate_reasoning(result, tech_score, fund_score, mom_score, composite)

        return GemAnalysis(
            symbol=result.symbol,
            current_price=result.current_price,
            technical_score=tech_score,
            fundamental_score=fund_score,
            momentum_score=mom_score,
            composite_score=composite,
            entry_price=entry_price,
            target_price=target_price,
            stop_loss=stop_loss,
            upside_potential=upside,
            downside_risk=downside,
            risk_reward_ratio=risk_reward,
            entry_trigger=entry_trigger,
            entry_conditions=entry_conditions,
            reasoning=reasoning,
            raw_data=result
        )

    def analyze_batch(
        self,
        results: List[ScreenerResult],
        min_score: float = 60
    ) -> List[GemAnalysis]:
        """
        Analyze a batch of screener results.

        Args:
            results: List of screener results to analyze
            min_score: Minimum composite score to include (default: 60)

        Returns:
            List of GemAnalysis sorted by composite score (descending)
        """
        analyses = []

        for result in results:
            try:
                analysis = self.analyze(result)
                if analysis.composite_score >= min_score:
                    analyses.append(analysis)
            except Exception as e:
                logger.warning("Failed to analyze", symbol=result.symbol, error=str(e))

        # Sort by composite score (highest first)
        analyses.sort(key=lambda x: -x.composite_score)

        logger.info(
            "Batch analysis complete",
            total=len(results),
            passed=len(analyses),
            min_score=min_score
        )

        return analyses
