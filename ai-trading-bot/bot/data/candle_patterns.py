"""
Candlestick Pattern Recognition

Detects key patterns from the trading skill:
- Hammer / Hanging Man
- Shooting Star
- Doji / Gravestone Doji / Dragonfly Doji
- Engulfing (Bullish / Bearish)
- Bull Flag / Bear Flag
- Spinning Top
- Tweezer Top / Bottom
"""

from dataclasses import dataclass
from bot.data.models import Candle


@dataclass
class CandlePattern:
    name: str
    direction: str  # "bullish", "bearish", "neutral"
    strength: float  # 0.0 to 1.0
    description: str


def detect_patterns(candles: list[Candle]) -> list[CandlePattern]:
    """Detect candlestick patterns from recent candles."""
    if len(candles) < 5:
        return []

    patterns = []

    latest = candles[-1]
    prev = candles[-2]
    body = abs(latest.close - latest.open)
    upper_wick = latest.high - max(latest.close, latest.open)
    lower_wick = min(latest.close, latest.open) - latest.low
    candle_range = latest.high - latest.low
    is_green = latest.close > latest.open

    if candle_range == 0:
        return patterns

    body_pct = body / candle_range

    # --- Single Candle Patterns ---

    # Doji: body < 10% of range
    if body_pct < 0.10:
        if upper_wick > lower_wick * 2 and lower_wick < candle_range * 0.1:
            # Gravestone Doji - bearish at top
            patterns.append(CandlePattern(
                "Gravestone Doji", "bearish", 0.7,
                "Long upper wick, no lower wick. Price surged then fully reversed."
            ))
        elif lower_wick > upper_wick * 2 and upper_wick < candle_range * 0.1:
            # Dragonfly Doji - bullish at bottom
            patterns.append(CandlePattern(
                "Dragonfly Doji", "bullish", 0.7,
                "Long lower wick, no upper wick. Price dropped then fully recovered."
            ))
        else:
            patterns.append(CandlePattern(
                "Doji", "neutral", 0.4,
                "Indecision. Open and close at same price."
            ))

    # Hammer: small body at top, long lower wick (>2x body), little upper wick
    elif (lower_wick >= body * 2 and upper_wick < body * 0.5
          and body_pct < 0.35):
        patterns.append(CandlePattern(
            "Hammer", "bullish", 0.65,
            "Small body at top, long lower wick. Bullish reversal at bottom of sell-off."
        ))

    # Shooting Star: small body at bottom, long upper wick (>2x body)
    elif (upper_wick >= body * 2 and lower_wick < body * 0.5
          and body_pct < 0.35):
        patterns.append(CandlePattern(
            "Shooting Star", "bearish", 0.65,
            "Small body at bottom, long upper wick. Price rejected at high."
        ))

    # Spinning Top: small body with both wicks
    elif (body_pct < 0.3 and upper_wick > body * 0.5
          and lower_wick > body * 0.5):
        patterns.append(CandlePattern(
            "Spinning Top", "neutral", 0.3,
            "Small body with upper and lower wicks. Indecision."
        ))

    # Long Body (strong conviction)
    elif body_pct > 0.7:
        if is_green:
            patterns.append(CandlePattern(
                "Long Green Body", "bullish", 0.6,
                "Strong buying conviction. Big solid body, little wicks."
            ))
        else:
            patterns.append(CandlePattern(
                "Long Red Body", "bearish", 0.6,
                "Strong selling conviction. Big solid body, little wicks."
            ))

    # --- Two Candle Patterns ---

    prev_body = abs(prev.close - prev.open)
    prev_is_green = prev.close > prev.open

    # Bullish Engulfing
    if (not prev_is_green and is_green
            and latest.open <= prev.close and latest.close >= prev.open
            and body > prev_body):
        patterns.append(CandlePattern(
            "Bullish Engulfing", "bullish", 0.75,
            "Green candle fully engulfs previous red body. Strong reversal signal."
        ))

    # Bearish Engulfing
    if (prev_is_green and not is_green
            and latest.open >= prev.close and latest.close <= prev.open
            and body > prev_body):
        patterns.append(CandlePattern(
            "Bearish Engulfing", "bearish", 0.75,
            "Red candle fully engulfs previous green body. Strong reversal signal."
        ))

    # Tweezer Top (matching highs)
    if abs(latest.high - prev.high) < candle_range * 0.05 and not is_green and prev_is_green:
        patterns.append(CandlePattern(
            "Tweezer Top", "bearish", 0.6,
            "Two candles with matching highs. Double rejection."
        ))

    # Tweezer Bottom (matching lows)
    if abs(latest.low - prev.low) < candle_range * 0.05 and is_green and not prev_is_green:
        patterns.append(CandlePattern(
            "Tweezer Bottom", "bullish", 0.6,
            "Two candles with matching lows. Double rejection."
        ))

    # --- Multi-Candle Patterns (flags) ---
    if len(candles) >= 5:
        patterns.extend(_detect_flags(candles[-5:]))

    return patterns


def _detect_flags(candles: list[Candle]) -> list[CandlePattern]:
    """Detect bull and bear flag patterns from 5 candles."""
    patterns = []

    # Bull flag: strong up move, then 2-3 small pullback candles
    first = candles[0]
    first_move = (first.close - first.open) / first.open * 100 if first.open > 0 else 0

    if first_move > 2:  # Strong green candle
        pullback_candles = candles[1:4]
        # Pullback: mostly red or small candles, each lower high
        red_count = sum(1 for c in pullback_candles if c.close < c.open)
        bodies_small = all(
            abs(c.close - c.open) < abs(first.close - first.open) * 0.5
            for c in pullback_candles
        )
        if red_count >= 2 and bodies_small:
            last = candles[-1]
            if last.close > last.open and last.high > max(c.high for c in pullback_candles):
                patterns.append(CandlePattern(
                    "Bull Flag", "bullish", 0.8,
                    "Strong candle -> pullback -> new high. Continuation pattern."
                ))

    if first_move < -2:  # Strong red candle
        bounce_candles = candles[1:4]
        green_count = sum(1 for c in bounce_candles if c.close > c.open)
        bodies_small = all(
            abs(c.close - c.open) < abs(first.close - first.open) * 0.5
            for c in bounce_candles
        )
        if green_count >= 2 and bodies_small:
            last = candles[-1]
            if last.close < last.open and last.low < min(c.low for c in bounce_candles):
                patterns.append(CandlePattern(
                    "Bear Flag", "bearish", 0.8,
                    "Strong red candle -> bounce -> new low. Continuation down."
                ))

    return patterns


def get_pattern_summary(patterns: list[CandlePattern]) -> str:
    """Get a human-readable summary of detected patterns."""
    if not patterns:
        return "No significant candle patterns detected"
    return " | ".join(f"{p.name} ({p.direction})" for p in patterns)
