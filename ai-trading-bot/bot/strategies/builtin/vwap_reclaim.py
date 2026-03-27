"""
VWAP Reclaim Strategy

Entry: First candle to close above VWAP after a dip below it.
VWAP reclaim with strong candle = long entry signal.
Price above VWAP = bullish day bias.
"""

from bot.strategies.base import Strategy
from bot.data.models import MarketSnapshot
from bot.engine.signal import Signal


class VWAPReclaimStrategy(Strategy):
    name = "VWAP Reclaim"
    description = "Buy first candle to close above VWAP after a dip below"

    def analyze(self, snapshot: MarketSnapshot) -> Signal | None:
        candles = snapshot.candles
        ind = snapshot.indicators
        if len(candles) < 5 or ind.vwap <= 0:
            return None

        price = snapshot.latest.close
        latest = snapshot.latest

        # Current candle must close above VWAP
        if price <= ind.vwap:
            return None

        # Previous candle(s) should have been below VWAP (the dip)
        recent = candles[-5:-1]
        below_vwap = [c for c in recent if c.close < ind.vwap]
        if len(below_vwap) < 1:
            return None  # No dip below VWAP

        # The reclaim candle should be green and strong
        if latest.close <= latest.open:
            return None

        body = latest.close - latest.open
        candle_range = latest.high - latest.low
        if candle_range > 0 and body / candle_range < 0.4:
            return None  # Weak candle (too much wick)

        # Volume confirmation
        if latest.volume < ind.volume_sma_20:
            return None

        # Calculate trade levels
        stop_loss = min(c.low for c in recent[-3:])
        risk = price - stop_loss
        if risk <= 0:
            return None

        # Target: high of day or previous resistance
        target_hod = max(c.high for c in candles[-10:])
        reward = target_hod - price
        rr = reward / risk if risk > 0 else 0

        if rr < 1.5:
            return None

        confidence = 0.6
        if ind.macd_line > ind.macd_signal:
            confidence += 0.1
        if ind.relative_volume >= 2.0:
            confidence += 0.05
        if rr >= 3.0:
            confidence += 0.05

        return Signal(
            action="BUY",
            confidence=min(confidence, 0.9),
            strategy_name=self.name,
            symbol=snapshot.symbol,
            price=price,
            reasons=[
                f"VWAP reclaim: price ${price:.2f} closed above VWAP ${ind.vwap:.2f}",
                f"Strong green candle on volume ({latest.volume:,} vs avg {ind.volume_sma_20:,.0f})",
                f"R:R = {rr:.1f}:1 | Stop: ${stop_loss:.2f} | Target: ${target_hod:.2f}",
            ],
            style="day",
            setup="VWAP Reclaim",
            stop_loss=stop_loss,
            target=target_hod,
            risk_reward=round(rr, 1),
        )

    def to_dict(self):
        return {"name": self.name, "type": "builtin"}

    @classmethod
    def from_dict(cls, data):
        return cls()
