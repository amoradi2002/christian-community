from bot.strategies.base import Strategy
from bot.data.models import MarketSnapshot
from bot.engine.signal import Signal


class MACDCrossoverStrategy(Strategy):
    name = "MACD Crossover"
    description = "Buy on bullish MACD crossover, Sell on bearish crossover"

    def analyze(self, snapshot: MarketSnapshot) -> Signal | None:
        ind = snapshot.indicators
        price = snapshot.latest.close

        # Bullish: MACD histogram turns positive
        if ind.macd_histogram > 0 and ind.macd_line > ind.macd_signal:
            strength = min(abs(ind.macd_histogram) / (price * 0.001 + 0.01), 1.0)
            return Signal(
                action="BUY",
                confidence=0.5 + strength * 0.3,
                strategy_name=self.name,
                symbol=snapshot.symbol,
                price=price,
                reasons=[
                    f"MACD bullish crossover (histogram: {ind.macd_histogram:.4f})",
                    f"MACD line ({ind.macd_line:.4f}) > signal ({ind.macd_signal:.4f})",
                ],
            )
        # Bearish: MACD histogram turns negative
        elif ind.macd_histogram < 0 and ind.macd_line < ind.macd_signal:
            strength = min(abs(ind.macd_histogram) / (price * 0.001 + 0.01), 1.0)
            return Signal(
                action="SELL",
                confidence=0.5 + strength * 0.3,
                strategy_name=self.name,
                symbol=snapshot.symbol,
                price=price,
                reasons=[
                    f"MACD bearish crossover (histogram: {ind.macd_histogram:.4f})",
                    f"MACD line ({ind.macd_line:.4f}) < signal ({ind.macd_signal:.4f})",
                ],
            )
        return None

    def to_dict(self):
        return {"name": self.name, "type": "builtin"}

    @classmethod
    def from_dict(cls, data):
        return cls()
