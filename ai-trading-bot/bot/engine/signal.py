from dataclasses import dataclass, field


@dataclass
class Signal:
    action: str  # "BUY", "SELL", "HOLD"
    confidence: float  # 0.0 to 1.0
    strategy_name: str = ""
    symbol: str = ""
    price: float = 0.0
    reasons: list = field(default_factory=list)

    def to_dict(self):
        return {
            "action": self.action,
            "confidence": self.confidence,
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "price": self.price,
            "reasons": self.reasons,
        }
