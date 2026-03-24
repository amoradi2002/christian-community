from bot.strategies.base import Strategy
from bot.data.models import MarketSnapshot
from bot.engine.signal import Signal


class BollingerSqueezeStrategy(Strategy):
    name = "Bollinger Squeeze"
    description = "Detect Bollinger Band squeeze and breakout direction"

    def analyze(self, snapshot: MarketSnapshot) -> Signal | None:
        ind = snapshot.indicators
        price = snapshot.latest.close

        if ind.bb_upper == 0 or ind.bb_lower == 0:
            return None

        band_width = (ind.bb_upper - ind.bb_lower) / ind.bb_middle
        squeeze_threshold = 0.04  # Tight bands

        # Breakout above upper band during squeeze
        if band_width < squeeze_threshold and price > ind.bb_upper:
            return Signal(
                action="BUY",
                confidence=0.65,
                strategy_name=self.name,
                symbol=snapshot.symbol,
                price=price,
                reasons=[
                    f"Bollinger squeeze breakout UP (width: {band_width:.4f})",
                    f"Price ({price:.2f}) > upper band ({ind.bb_upper:.2f})",
                ],
            )
        # Breakdown below lower band during squeeze
        elif band_width < squeeze_threshold and price < ind.bb_lower:
            return Signal(
                action="SELL",
                confidence=0.65,
                strategy_name=self.name,
                symbol=snapshot.symbol,
                price=price,
                reasons=[
                    f"Bollinger squeeze breakout DOWN (width: {band_width:.4f})",
                    f"Price ({price:.2f}) < lower band ({ind.bb_lower:.2f})",
                ],
            )
        # Price touching upper band with wide bands (potential reversal)
        elif price >= ind.bb_upper and band_width > 0.08:
            return Signal(
                action="SELL",
                confidence=0.55,
                strategy_name=self.name,
                symbol=snapshot.symbol,
                price=price,
                reasons=[f"Price at upper Bollinger Band with wide bands ({band_width:.4f})"],
            )
        return None

    def to_dict(self):
        return {"name": self.name, "type": "builtin", "params": {"squeeze_threshold": 0.04}}

    @classmethod
    def from_dict(cls, data):
        return cls()
