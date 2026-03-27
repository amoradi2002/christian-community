"""
Pullback Pattern — Core Day Trade Setup

From the trading skill:
1. Stock hits 5 Pillars — surges on news
2. Price pulls back — let it, don't chase
3. Watch for bottom: hammer, doji, volume drying up
4. ENTRY: First 1-min candle to CLOSE above the high of the last red candle
5. STOP: Low of the pullback
6. TARGET: Retest of the high of day (minimum)
7. MINIMUM R:R: 2:1 — if you can't get it, skip

Green light: Volume drops on red candles, hammer/doji forming, MACD staying positive
Red flag: Heavy volume on red candles, MACD crossing negative, stock gave back 80%+ of move
"""

from bot.strategies.base import Strategy
from bot.data.models import MarketSnapshot
from bot.engine.signal import Signal
from bot.data.candle_patterns import detect_patterns


class PullbackStrategy(Strategy):
    name = "Pullback Pattern"
    description = "Core day trade: buy first candle to close above last red candle high after pullback"

    def analyze(self, snapshot: MarketSnapshot) -> Signal | None:
        candles = snapshot.candles
        ind = snapshot.indicators
        if len(candles) < 10:
            return None

        price = snapshot.latest.close

        # Need recent strong move up first
        if ind.day_change_pct < 3:
            return None

        # Find the recent high, then a pullback
        recent = candles[-10:]
        high_of_day = max(c.high for c in recent)
        high_idx = next(i for i, c in enumerate(recent) if c.high == high_of_day)

        # Must have pulled back after the high
        if high_idx >= len(recent) - 2:
            return None  # High is too recent, no pullback yet

        # Find pullback candles (after the high)
        pullback_candles = recent[high_idx + 1:]
        if len(pullback_candles) < 2:
            return None

        # Check volume drying up on pullback (green light)
        pullback_volumes = [c.volume for c in pullback_candles]
        surge_volume = recent[high_idx].volume
        volume_drying = all(v < surge_volume * 0.7 for v in pullback_volumes)

        # Check MACD still positive (green light)
        macd_positive = ind.macd_line > ind.macd_signal

        # Check for reversal candle patterns at bottom
        patterns = detect_patterns(candles[-5:])
        bullish_patterns = [p for p in patterns if p.direction == "bullish"]

        # Red flag: gave back 80%+ of the move
        move_start = min(c.low for c in recent[:high_idx + 1])
        move_size = high_of_day - move_start
        pullback_low = min(c.low for c in pullback_candles)
        gave_back = (high_of_day - pullback_low) / move_size if move_size > 0 else 1.0
        if gave_back > 0.8:
            return None  # Gave back too much

        # ENTRY: Latest candle closes above last red candle's high
        last_red = None
        for c in reversed(pullback_candles[:-1]):
            if c.close < c.open:
                last_red = c
                break

        if last_red is None:
            return None

        latest = candles[-1]
        if latest.close <= last_red.high:
            return None  # Hasn't broken above last red

        if not latest.close > latest.open:
            return None  # Latest should be green

        # Calculate R:R
        stop_loss = pullback_low
        target = high_of_day
        risk = price - stop_loss
        reward = target - price

        if risk <= 0:
            return None
        rr = reward / risk
        if rr < 2.0:
            return None  # Minimum 2:1 required

        # Score confidence
        confidence = 0.55
        if volume_drying:
            confidence += 0.1
        if macd_positive:
            confidence += 0.1
        if bullish_patterns:
            confidence += 0.1
        if rr >= 3.0:
            confidence += 0.05

        confidence = min(confidence, 0.95)

        reasons = [
            f"Pullback pattern: price broke above last red candle high (${last_red.high:.2f})",
            f"Pullback held — gave back {gave_back:.0%} of move (under 80%)",
            f"R:R = {rr:.1f}:1 | Stop: ${stop_loss:.2f} | Target: ${target:.2f}",
        ]
        if volume_drying:
            reasons.append("Volume drying up on pullback (healthy)")
        if macd_positive:
            reasons.append("MACD staying positive (bullish)")
        if bullish_patterns:
            reasons.append(f"Candle signal: {', '.join(p.name for p in bullish_patterns)}")

        return Signal(
            action="BUY",
            confidence=confidence,
            strategy_name=self.name,
            symbol=snapshot.symbol,
            price=price,
            reasons=reasons,
            style="day",
            setup="Pullback",
            stop_loss=stop_loss,
            target=target,
            risk_reward=round(rr, 1),
            candle_pattern=bullish_patterns[0].name if bullish_patterns else "",
        )

    def to_dict(self):
        return {"name": self.name, "type": "builtin"}

    @classmethod
    def from_dict(cls, data):
        return cls()
