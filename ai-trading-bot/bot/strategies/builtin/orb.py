"""
Opening Range Breakout (ORB) Strategy

Entry: Candle close above 5 or 15-minute opening range high with volume.
Works on intraday timeframes.
"""

from bot.strategies.base import Strategy
from bot.data.models import MarketSnapshot
from bot.engine.signal import Signal


class ORBStrategy(Strategy):
    name = "Opening Range Breakout"
    description = "Buy/sell on break of the opening range high/low with volume"

    def analyze(self, snapshot: MarketSnapshot) -> Signal | None:
        candles = snapshot.candles
        ind = snapshot.indicators
        if len(candles) < 5:
            return None

        price = snapshot.latest.close
        latest = snapshot.latest

        # Define opening range from first few candles
        opening = candles[:3]  # First 3 candles as opening range
        orb_high = max(c.high for c in opening)
        orb_low = min(c.low for c in opening)
        orb_range = orb_high - orb_low

        if orb_range <= 0:
            return None

        # Check for breakout above ORB high
        if latest.close > orb_high and latest.close > latest.open:
            # Volume confirmation
            if latest.volume < ind.volume_sma_20:
                return None

            stop_loss = orb_low
            target = orb_high + orb_range  # Measured move
            risk = price - stop_loss
            reward = target - price
            rr = reward / risk if risk > 0 else 0

            if rr < 1.5:
                return None

            confidence = 0.6
            if ind.macd_line > ind.macd_signal:
                confidence += 0.1
            if price > ind.vwap:
                confidence += 0.05
            if ind.relative_volume >= 2.0:
                confidence += 0.05

            return Signal(
                action="BUY",
                confidence=min(confidence, 0.9),
                strategy_name=self.name,
                symbol=snapshot.symbol,
                price=price,
                reasons=[
                    f"ORB breakout: price ${price:.2f} above opening range high ${orb_high:.2f}",
                    f"Opening range: ${orb_low:.2f} - ${orb_high:.2f}",
                    f"R:R = {rr:.1f}:1 | Stop: ${stop_loss:.2f} | Target: ${target:.2f}",
                ],
                style="day",
                setup="Opening Range Breakout",
                stop_loss=stop_loss,
                target=target,
                risk_reward=round(rr, 1),
            )

        # Check for breakdown below ORB low
        elif latest.close < orb_low and latest.close < latest.open:
            if latest.volume < ind.volume_sma_20:
                return None

            stop_loss = orb_high
            target = orb_low - orb_range
            risk = stop_loss - price
            reward = price - target
            rr = reward / risk if risk > 0 else 0

            if rr < 1.5:
                return None

            confidence = 0.6
            if ind.macd_line < ind.macd_signal:
                confidence += 0.1
            if price < ind.vwap:
                confidence += 0.05

            return Signal(
                action="SELL",
                confidence=min(confidence, 0.9),
                strategy_name=self.name,
                symbol=snapshot.symbol,
                price=price,
                reasons=[
                    f"ORB breakdown: price ${price:.2f} below opening range low ${orb_low:.2f}",
                    f"Opening range: ${orb_low:.2f} - ${orb_high:.2f}",
                    f"R:R = {rr:.1f}:1 | Stop: ${stop_loss:.2f} | Target: ${target:.2f}",
                ],
                style="day",
                setup="Opening Range Breakdown",
                stop_loss=stop_loss,
                target=target,
                risk_reward=round(rr, 1),
            )

        return None

    def to_dict(self):
        return {"name": self.name, "type": "builtin"}

    @classmethod
    def from_dict(cls, data):
        return cls()
