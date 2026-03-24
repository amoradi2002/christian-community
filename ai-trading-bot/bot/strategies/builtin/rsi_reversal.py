from bot.strategies.base import Strategy
from bot.data.models import MarketSnapshot
from bot.engine.signal import Signal


class RSIReversalStrategy(Strategy):
    name = "RSI Reversal"
    description = "Buy when RSI < 30 (oversold), Sell when RSI > 70 (overbought)"

    def analyze(self, snapshot: MarketSnapshot) -> Signal | None:
        rsi = snapshot.indicators.rsi_14
        price = snapshot.latest.close

        if rsi <= 30:
            return Signal(
                action="BUY",
                confidence=min(0.5 + (30 - rsi) / 60, 0.95),
                strategy_name=self.name,
                symbol=snapshot.symbol,
                price=price,
                reasons=[f"RSI oversold at {rsi:.1f}"],
            )
        elif rsi >= 70:
            return Signal(
                action="SELL",
                confidence=min(0.5 + (rsi - 70) / 60, 0.95),
                strategy_name=self.name,
                symbol=snapshot.symbol,
                price=price,
                reasons=[f"RSI overbought at {rsi:.1f}"],
            )
        return None

    def to_dict(self):
        return {"name": self.name, "type": "builtin", "params": {"oversold": 30, "overbought": 70}}

    @classmethod
    def from_dict(cls, data):
        return cls()
