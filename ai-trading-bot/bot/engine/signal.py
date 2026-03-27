from dataclasses import dataclass, field


@dataclass
class Signal:
    action: str  # "BUY", "SELL", "HOLD"
    confidence: float  # 0.0 to 1.0
    strategy_name: str = ""
    symbol: str = ""
    price: float = 0.0
    reasons: list = field(default_factory=list)
    style: str = ""  # "day", "swing", "options"
    setup: str = ""  # "Pullback", "Gap and Go", "VWAP Reclaim", etc.
    entry_trigger: str = ""
    stop_loss: float = 0.0
    target: float = 0.0
    risk_reward: float = 0.0
    catalyst: str = ""
    catalyst_tier: str = ""  # "S", "A", "B", "C", "Skip"
    candle_pattern: str = ""
    sector: str = ""

    def to_dict(self):
        d = {
            "action": self.action,
            "confidence": self.confidence,
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "price": self.price,
            "reasons": self.reasons,
        }
        if self.style:
            d["style"] = self.style
        if self.setup:
            d["setup"] = self.setup
        if self.stop_loss:
            d["stop_loss"] = self.stop_loss
        if self.target:
            d["target"] = self.target
        if self.risk_reward:
            d["risk_reward"] = self.risk_reward
        if self.catalyst:
            d["catalyst"] = self.catalyst
        if self.catalyst_tier:
            d["catalyst_tier"] = self.catalyst_tier
        if self.candle_pattern:
            d["candle_pattern"] = self.candle_pattern
        return d
