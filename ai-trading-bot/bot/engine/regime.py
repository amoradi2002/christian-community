"""
Market Regime Detection

Identifies the current market regime (bull trend, bear trend, ranging, etc.)
and provides strategy recommendations and risk adjustments for each regime.

Usage:
    from bot.engine.regime import detect_regime, detect_market_regime

    analysis = detect_regime(candles, indicators)
    print(analysis.regime, analysis.confidence)
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

import numpy as np
import pandas as pd

from bot.data.models import Candle, IndicatorSet

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums & Data Classes
# ---------------------------------------------------------------------------

class MarketRegime(Enum):
    BULL_TREND = "bull_trend"
    BEAR_TREND = "bear_trend"
    BULL_VOLATILE = "bull_volatile"
    BEAR_VOLATILE = "bear_volatile"
    RANGING = "ranging"
    BREAKOUT = "breakout"
    CRASH = "crash"


@dataclass
class RegimeAnalysis:
    regime: MarketRegime
    confidence: float           # 0-1
    trend_strength: float       # 0-1 (0=no trend, 1=strong trend)
    volatility_percentile: float  # 0-100
    breadth_score: float        # -1 to +1 (market breadth)
    recommended_strategies: list  # strategy styles for this regime
    risk_adjustment: float      # multiplier for position sizing
    description: str


# ---------------------------------------------------------------------------
# Strategy recommendations per regime
# ---------------------------------------------------------------------------

_REGIME_STRATEGIES = {
    MarketRegime.BULL_TREND: [
        "pullback buys", "VWAP reclaim", "swing long", "sell puts",
        "trend following", "buy the dip",
    ],
    MarketRegime.BEAR_TREND: [
        "short setups", "bear put spreads", "cash preservation",
        "inverse ETFs", "sell call spreads",
    ],
    MarketRegime.BULL_VOLATILE: [
        "smaller positions", "wider stops", "straddles",
        "reduced leverage", "scale in slowly",
    ],
    MarketRegime.BEAR_VOLATILE: [
        "cash", "hedges only", "protective puts",
        "inverse ETFs small size", "wait for clarity",
    ],
    MarketRegime.RANGING: [
        "iron condors", "mean reversion", "sell strangles",
        "range fade", "support/resistance bounce",
    ],
    MarketRegime.BREAKOUT: [
        "ORB", "gap-and-go", "momentum plays",
        "breakout pullback", "volume surge entries",
    ],
    MarketRegime.CRASH: [
        "cash is king", "buy puts for protection",
        "watch for reversal signals", "VIX calls",
        "avoid catching falling knives",
    ],
}

_REGIME_RISK_MULTIPLIERS = {
    MarketRegime.BULL_TREND: 1.0,
    MarketRegime.BEAR_TREND: 0.6,
    MarketRegime.BULL_VOLATILE: 0.7,
    MarketRegime.BEAR_VOLATILE: 0.4,
    MarketRegime.RANGING: 0.8,
    MarketRegime.BREAKOUT: 0.9,
    MarketRegime.CRASH: 0.25,
}

_REGIME_DESCRIPTIONS = {
    MarketRegime.BULL_TREND: (
        "Sustained uptrend with orderly price action. Price is above the 50-SMA "
        "which is above the 200-SMA, and trend strength (ADX) confirms directional "
        "movement. Favor long entries on pullbacks."
    ),
    MarketRegime.BEAR_TREND: (
        "Sustained downtrend. Price is below the 50-SMA which is below the 200-SMA. "
        "ADX confirms strong directional selling pressure. Avoid new longs; look for "
        "short setups or stay in cash."
    ),
    MarketRegime.BULL_VOLATILE: (
        "Uptrend with elevated volatility. The broader direction is up, but large "
        "swings and ATR expansion make position sizing critical. Use smaller "
        "positions and wider stops."
    ),
    MarketRegime.BEAR_VOLATILE: (
        "Downtrend with elevated volatility. Violent rallies within a bearish "
        "structure create whipsaws. Capital preservation is the priority."
    ),
    MarketRegime.RANGING: (
        "No clear trend. ADX is low and price is oscillating around the moving "
        "averages. Mean-reversion strategies and options selling work best."
    ),
    MarketRegime.BREAKOUT: (
        "Transitioning from a range to a new trend. Volatility squeeze is releasing "
        "with a volume surge. Momentum strategies excel here."
    ),
    MarketRegime.CRASH: (
        "Extreme sell-off. Price is far below Bollinger lower band on massive volume. "
        "Cash is the primary position. Only protective hedges are appropriate."
    ),
}


# ---------------------------------------------------------------------------
# Technical calculations
# ---------------------------------------------------------------------------

def calculate_adx(candles: List[Candle], period: int = 14) -> float:
    """Calculate Average Directional Index (ADX).

    Returns a value from 0-100 where:
        < 20 = no/weak trend
        20-25 = emerging trend
        25-50 = strong trend
        50-75 = very strong trend
        > 75 = extremely strong trend
    """
    if len(candles) < period * 2 + 1:
        logger.debug("Not enough candles for ADX (%d < %d)", len(candles), period * 2 + 1)
        return 0.0

    highs = np.array([c.high for c in candles], dtype=float)
    lows = np.array([c.low for c in candles], dtype=float)
    closes = np.array([c.close for c in candles], dtype=float)

    n = len(candles)

    # True Range
    tr = np.zeros(n)
    tr[0] = highs[0] - lows[0]
    for i in range(1, n):
        tr[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )

    # +DM and -DM
    plus_dm = np.zeros(n)
    minus_dm = np.zeros(n)
    for i in range(1, n):
        up_move = highs[i] - highs[i - 1]
        down_move = lows[i - 1] - lows[i]
        if up_move > down_move and up_move > 0:
            plus_dm[i] = up_move
        if down_move > up_move and down_move > 0:
            minus_dm[i] = down_move

    # Smoothed TR, +DM, -DM using Wilder's smoothing
    atr = np.zeros(n)
    smooth_plus = np.zeros(n)
    smooth_minus = np.zeros(n)

    atr[period] = np.sum(tr[1:period + 1])
    smooth_plus[period] = np.sum(plus_dm[1:period + 1])
    smooth_minus[period] = np.sum(minus_dm[1:period + 1])

    for i in range(period + 1, n):
        atr[i] = atr[i - 1] - (atr[i - 1] / period) + tr[i]
        smooth_plus[i] = smooth_plus[i - 1] - (smooth_plus[i - 1] / period) + plus_dm[i]
        smooth_minus[i] = smooth_minus[i - 1] - (smooth_minus[i - 1] / period) + minus_dm[i]

    # +DI and -DI
    plus_di = np.zeros(n)
    minus_di = np.zeros(n)
    for i in range(period, n):
        if atr[i] != 0:
            plus_di[i] = 100.0 * smooth_plus[i] / atr[i]
            minus_di[i] = 100.0 * smooth_minus[i] / atr[i]

    # DX
    dx = np.zeros(n)
    for i in range(period, n):
        di_sum = plus_di[i] + minus_di[i]
        if di_sum != 0:
            dx[i] = 100.0 * abs(plus_di[i] - minus_di[i]) / di_sum

    # ADX: first ADX is average of first 'period' DX values
    start = period * 2
    if start >= n:
        return 0.0

    adx = np.zeros(n)
    adx[start] = np.mean(dx[period + 1:start + 1])
    for i in range(start + 1, n):
        adx[i] = (adx[i - 1] * (period - 1) + dx[i]) / period

    return round(float(adx[-1]), 2)


def calculate_volatility_percentile(candles: List[Candle], lookback: int = 252) -> float:
    """Calculate where current volatility sits as a percentile of historical volatility.

    Uses ATR as a percentage of price, measured over a rolling 14-day window.
    Returns 0-100 where 100 means current vol is at the highest level seen
    in the lookback window.
    """
    if len(candles) < 30:
        return 50.0  # default to middle if not enough data

    highs = pd.Series([c.high for c in candles], dtype=float)
    lows = pd.Series([c.low for c in candles], dtype=float)
    closes = pd.Series([c.close for c in candles], dtype=float)

    # True range
    tr = pd.concat([
        highs - lows,
        (highs - closes.shift(1)).abs(),
        (lows - closes.shift(1)).abs(),
    ], axis=1).max(axis=1)

    # ATR as percentage of price
    atr_14 = tr.rolling(window=14).mean()
    atr_pct = (atr_14 / closes) * 100.0

    # Drop NaN values
    atr_pct = atr_pct.dropna()

    if len(atr_pct) < 2:
        return 50.0

    # Limit to lookback window
    atr_pct = atr_pct.iloc[-lookback:]

    current = atr_pct.iloc[-1]
    percentile = float((atr_pct < current).sum() / len(atr_pct) * 100.0)
    return round(percentile, 1)


def _calculate_breadth_score(candles: List[Candle]) -> float:
    """Estimate breadth from a single instrument by measuring recent price action
    vs historical norms.

    Returns -1 to +1 where:
        +1 = strong bullish breadth (price consistently closing near highs)
        -1 = strong bearish breadth (price consistently closing near lows)
    """
    if len(candles) < 20:
        return 0.0

    recent = candles[-20:]
    scores = []
    for c in recent:
        rng = c.high - c.low
        if rng == 0:
            scores.append(0.0)
        else:
            # Where did the close fall within the day's range?
            position = (c.close - c.low) / rng  # 0 = closed at low, 1 = closed at high
            scores.append(position * 2 - 1)  # map 0-1 to -1 to +1

    return round(float(np.mean(scores)), 3)


def _detect_squeeze(candles: List[Candle], indicators: Optional[IndicatorSet] = None) -> bool:
    """Detect Bollinger Band squeeze (BB inside Keltner Channel).

    A simpler proxy: check if BB width is in the bottom 20% of its recent range.
    """
    if len(candles) < 50:
        return False

    closes = pd.Series([c.close for c in candles], dtype=float)
    highs = pd.Series([c.high for c in candles], dtype=float)
    lows = pd.Series([c.low for c in candles], dtype=float)

    # Bollinger Band width
    sma_20 = closes.rolling(20).mean()
    std_20 = closes.rolling(20).std()
    bb_width = (4 * std_20) / sma_20  # width as % of price

    bb_width = bb_width.dropna()
    if len(bb_width) < 20:
        return False

    current_width = bb_width.iloc[-1]
    percentile = float((bb_width < current_width).sum() / len(bb_width) * 100.0)

    return percentile < 20.0


def _detect_volume_surge(candles: List[Candle], threshold: float = 2.0) -> bool:
    """Check if recent volume is significantly above average."""
    if len(candles) < 21:
        return False

    volumes = [float(c.volume) for c in candles]
    avg_vol = np.mean(volumes[-21:-1])  # 20-day avg excluding today
    current_vol = volumes[-1]

    if avg_vol == 0:
        return False

    return current_vol > avg_vol * threshold


def _is_crash_condition(
    candles: List[Candle],
    indicators: Optional[IndicatorSet],
    volatility_pct: float,
) -> bool:
    """Detect extreme sell-off / crash conditions."""
    if len(candles) < 5:
        return False

    price = candles[-1].close

    # Check if price is below BB lower band
    below_bb = False
    if indicators and indicators.bb_lower > 0:
        below_bb = price < indicators.bb_lower

    # Check for extreme consecutive down days
    recent_changes = []
    for i in range(-5, 0):
        if abs(i) <= len(candles):
            prev_close = candles[i - 1].close if abs(i - 1) < len(candles) else candles[i].open
            if prev_close > 0:
                recent_changes.append((candles[i].close - prev_close) / prev_close * 100)

    extreme_down = sum(1 for ch in recent_changes if ch < -2.0) >= 3

    # Volume surge
    volume_surge = _detect_volume_surge(candles, threshold=2.5)

    # Volatility in extreme upper percentile
    extreme_vol = volatility_pct > 90

    # Need at least 2 of 3 crash signals plus either BB or extreme vol
    crash_signals = sum([below_bb, extreme_down, volume_surge])
    return crash_signals >= 2 and extreme_vol


# ---------------------------------------------------------------------------
# Core Detection
# ---------------------------------------------------------------------------

def detect_regime(
    candles: List[Candle],
    indicators: Optional[IndicatorSet] = None,
) -> RegimeAnalysis:
    """Detect the current market regime from price data and indicators.

    Args:
        candles: List of Candle objects (at least 50, ideally 200+).
        indicators: Pre-computed IndicatorSet. If None, critical values
                    will be computed from candles.

    Returns:
        RegimeAnalysis with regime classification, confidence, and recommendations.
    """
    if not candles or len(candles) < 26:
        logger.warning("Not enough candles for regime detection (%d)", len(candles) if candles else 0)
        return RegimeAnalysis(
            regime=MarketRegime.RANGING,
            confidence=0.0,
            trend_strength=0.0,
            volatility_percentile=50.0,
            breadth_score=0.0,
            recommended_strategies=_REGIME_STRATEGIES[MarketRegime.RANGING],
            risk_adjustment=0.5,
            description="Insufficient data for regime detection. Defaulting to RANGING with reduced risk.",
        )

    price = candles[-1].close

    # -- Gather indicator values, computing if missing --
    sma_50 = 0.0
    sma_200 = 0.0
    bb_lower = 0.0
    atr = 0.0

    if indicators:
        sma_50 = indicators.sma_50
        sma_200 = indicators.sma_200
        bb_lower = indicators.bb_lower
        atr = indicators.atr_14

    # Compute SMAs from candles if not available
    closes = [c.close for c in candles]
    if sma_50 == 0.0 and len(closes) >= 50:
        sma_50 = float(np.mean(closes[-50:]))
    if sma_200 == 0.0 and len(closes) >= 200:
        sma_200 = float(np.mean(closes[-200:]))
    if atr == 0.0 and len(candles) >= 15:
        highs = pd.Series([c.high for c in candles], dtype=float)
        lows_s = pd.Series([c.low for c in candles], dtype=float)
        closes_s = pd.Series(closes, dtype=float)
        tr = pd.concat([
            highs - lows_s,
            (highs - closes_s.shift(1)).abs(),
            (lows_s - closes_s.shift(1)).abs(),
        ], axis=1).max(axis=1)
        atr = float(tr.rolling(14).mean().iloc[-1])

    # -- Compute regime components --
    adx = calculate_adx(candles)
    volatility_pct = calculate_volatility_percentile(candles)
    breadth = _calculate_breadth_score(candles)
    squeeze = _detect_squeeze(candles, indicators)
    volume_surge = _detect_volume_surge(candles)

    # Trend direction scoring
    trend_direction = 0.0  # positive = bullish, negative = bearish
    trend_signals = 0

    # Price vs SMAs
    if sma_50 > 0:
        if price > sma_50:
            trend_direction += 1.0
        else:
            trend_direction -= 1.0
        trend_signals += 1

    if sma_200 > 0:
        if price > sma_200:
            trend_direction += 1.0
        else:
            trend_direction -= 1.0
        trend_signals += 1

    # SMA alignment (golden cross / death cross)
    if sma_50 > 0 and sma_200 > 0:
        if sma_50 > sma_200:
            trend_direction += 1.0
        else:
            trend_direction -= 1.0
        trend_signals += 1

    # Normalize trend direction
    if trend_signals > 0:
        trend_direction /= trend_signals

    # Trend strength from ADX (0-1 scale)
    trend_strength = min(adx / 50.0, 1.0)

    # High volatility threshold
    high_vol = volatility_pct > 70

    # -- Classify regime --
    regime = MarketRegime.RANGING  # default
    confidence = 0.5

    # Check crash first (highest priority)
    if _is_crash_condition(candles, indicators, volatility_pct):
        regime = MarketRegime.CRASH
        confidence = min(0.6 + (volatility_pct / 200.0), 0.95)

    # Check breakout (squeeze releasing with volume)
    elif squeeze and volume_surge and adx > 18:
        regime = MarketRegime.BREAKOUT
        confidence = 0.5 + min(adx / 100.0, 0.3)
        if trend_direction > 0:
            confidence += 0.1

    # Strong trending regimes (ADX > 25)
    elif adx > 25:
        if trend_direction > 0.3:
            if high_vol:
                regime = MarketRegime.BULL_VOLATILE
                confidence = 0.5 + trend_strength * 0.3
            else:
                regime = MarketRegime.BULL_TREND
                confidence = 0.5 + trend_strength * 0.4
        elif trend_direction < -0.3:
            if high_vol:
                regime = MarketRegime.BEAR_VOLATILE
                confidence = 0.5 + trend_strength * 0.3
            else:
                regime = MarketRegime.BEAR_TREND
                confidence = 0.5 + trend_strength * 0.4
        else:
            # ADX is high but no clear direction -- choppy/transitional
            if high_vol:
                regime = MarketRegime.BULL_VOLATILE if breadth > 0 else MarketRegime.BEAR_VOLATILE
                confidence = 0.4
            else:
                regime = MarketRegime.RANGING
                confidence = 0.4

    # Moderate trend (20 < ADX <= 25) -- emerging trend or fading
    elif adx > 20:
        if high_vol:
            if trend_direction > 0:
                regime = MarketRegime.BULL_VOLATILE
            else:
                regime = MarketRegime.BEAR_VOLATILE
            confidence = 0.45
        elif squeeze:
            regime = MarketRegime.BREAKOUT
            confidence = 0.5
        elif trend_direction > 0.5:
            regime = MarketRegime.BULL_TREND
            confidence = 0.5
        elif trend_direction < -0.5:
            regime = MarketRegime.BEAR_TREND
            confidence = 0.5
        else:
            regime = MarketRegime.RANGING
            confidence = 0.55

    # Weak trend (ADX < 20)
    else:
        if squeeze and volume_surge:
            regime = MarketRegime.BREAKOUT
            confidence = 0.55
        else:
            regime = MarketRegime.RANGING
            # Confidence in ranging is higher when ADX is very low
            confidence = 0.5 + (1.0 - adx / 20.0) * 0.3

    # Clamp confidence
    confidence = round(max(0.0, min(1.0, confidence)), 3)

    return RegimeAnalysis(
        regime=regime,
        confidence=confidence,
        trend_strength=round(trend_strength, 3),
        volatility_percentile=volatility_pct,
        breadth_score=breadth,
        recommended_strategies=_REGIME_STRATEGIES[regime],
        risk_adjustment=_REGIME_RISK_MULTIPLIERS[regime],
        description=_REGIME_DESCRIPTIONS[regime],
    )


def detect_market_regime() -> RegimeAnalysis:
    """Detect the overall market regime using SPY as a proxy.

    Fetches SPY daily candles and indicators, then classifies the regime.
    Falls back to a neutral RANGING result if data is unavailable.
    """
    try:
        from bot.data.indicators import compute_indicators
        from bot.config.settings import CONFIG

        provider = CONFIG.get("data", {}).get("provider", "yfinance")

        candles = []
        if provider == "alpaca":
            try:
                from bot.data.alpaca_provider import fetch_alpaca_bars
                candles = fetch_alpaca_bars("SPY", interval="1d", days=365)
            except (ImportError, ValueError) as exc:
                logger.debug("Alpaca unavailable for SPY: %s", exc)

        if not candles:
            from bot.data.fetcher import fetch_market_data
            candles = fetch_market_data("SPY", period="1y", interval="1d")

        if not candles or len(candles) < 50:
            logger.warning("Could not fetch sufficient SPY data for market regime")
            return RegimeAnalysis(
                regime=MarketRegime.RANGING,
                confidence=0.0,
                trend_strength=0.0,
                volatility_percentile=50.0,
                breadth_score=0.0,
                recommended_strategies=_REGIME_STRATEGIES[MarketRegime.RANGING],
                risk_adjustment=0.8,
                description="Unable to fetch market data. Defaulting to RANGING.",
            )

        indicators = compute_indicators(candles)
        analysis = detect_regime(candles, indicators)

        logger.info(
            "Market regime: %s (confidence=%.1f%%, ADX=%.1f, vol_pct=%.0f%%)",
            analysis.regime.value,
            analysis.confidence * 100,
            calculate_adx(candles),
            analysis.volatility_percentile,
        )

        return analysis

    except Exception as exc:
        logger.error("Failed to detect market regime: %s", exc, exc_info=True)
        return RegimeAnalysis(
            regime=MarketRegime.RANGING,
            confidence=0.0,
            trend_strength=0.0,
            volatility_percentile=50.0,
            breadth_score=0.0,
            recommended_strategies=_REGIME_STRATEGIES[MarketRegime.RANGING],
            risk_adjustment=0.5,
            description=f"Regime detection failed: {exc}. Defaulting to RANGING.",
        )


def get_regime_strategy_filter(regime: MarketRegime) -> list:
    """Return recommended strategy names for a given regime."""
    return _REGIME_STRATEGIES.get(regime, _REGIME_STRATEGIES[MarketRegime.RANGING])


def get_regime_risk_multiplier(regime: MarketRegime) -> float:
    """Return position-size multiplier for a given regime.

    1.0 = full size, 0.5 = half size, etc.
    """
    return _REGIME_RISK_MULTIPLIERS.get(regime, 0.5)
