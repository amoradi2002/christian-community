"""
Gap and Go Strategy

Entry: Break of premarket high on volume at open.
Works best with stocks that gap up on a catalyst (Tier S or A).
"""

from bot.strategies.base import Strategy
from bot.data.models import MarketSnapshot
from bot.engine.signal import Signal


class GapAndGoStrategy(Strategy):
    name = "Gap and Go"
    description = "Buy on break of premarket high with volume confirmation"

    def analyze(self, snapshot: MarketSnapshot) -> Signal | None:
        candles = snapshot.candles
        ind = snapshot.indicators
        if len(candles) < 5:
            return None

        price = snapshot.latest.close

        # Need significant gap up (at least 5%)
        if ind.day_change_pct < 5:
            return None

        # Need strong relative volume
        if ind.relative_volume < 2.0:
            return None

        # Price making new highs — latest candle high is the highest
        recent = candles[-5:]
        if snapshot.latest.high < max(c.high for c in recent[:-1]):
            return None

        # MACD confirms bullish momentum
        if ind.macd_line < ind.macd_signal:
            return None

        # Volume on latest candle should be strong
        if snapshot.latest.volume < ind.volume_sma_20 * 1.5:
            return None

        # Calculate levels
        recent_low = min(c.low for c in recent)
        stop_loss = recent_low
        risk = price - stop_loss
        if risk <= 0:
            return None

        # Target: 2x the gap size from open
        gap_size = price * (ind.day_change_pct / 100)
        target = price + gap_size * 0.5  # Measured move
        reward = target - price
        rr = reward / risk if risk > 0 else 0

        if rr < 2.0:
            return None

        confidence = 0.6
        if ind.relative_volume >= 5.0:
            confidence += 0.1
        if ind.day_change_pct >= 10:
            confidence += 0.05
        if price > ind.vwap:
            confidence += 0.05

        return Signal(
            action="BUY",
            confidence=min(confidence, 0.9),
            strategy_name=self.name,
            symbol=snapshot.symbol,
            price=price,
            reasons=[
                f"Gap up {ind.day_change_pct:+.1f}% breaking to new highs",
                f"Relative volume: {ind.relative_volume:.1f}x",
                f"R:R = {rr:.1f}:1 | Stop: ${stop_loss:.2f} | Target: ${target:.2f}",
                f"MACD bullish, price {'above' if price > ind.vwap else 'below'} VWAP",
            ],
            style="day",
            setup="Gap and Go",
            stop_loss=stop_loss,
            target=target,
            risk_reward=round(rr, 1),
        )

    def to_dict(self):
        return {"name": self.name, "type": "builtin"}

    @classmethod
    def from_dict(cls, data):
        return cls()
