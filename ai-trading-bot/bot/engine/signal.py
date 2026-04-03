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
    target_price: float = 0.0  # Alias for target (used by some modules)
    entry_price: float = 0.0   # Explicit entry price
    risk_reward: float = 0.0
    catalyst: str = ""
    catalyst_tier: str = ""  # "S", "A", "B", "C", "Skip"
    candle_pattern: str = ""
    sector: str = ""
    # Options-specific fields
    option_type: str = ""      # "call" or "put"
    strike: float = 0.0        # Strike price
    expiry: str = ""           # Expiration date "2026-04-17"
    premium: float = 0.0       # Option premium per contract
    iv: float = 0.0            # Implied volatility
    delta: float = 0.0         # Delta
    contracts: int = 0         # Suggested number of contracts
    spread_type: str = ""      # "vertical", "iron_condor", "straddle", etc.
    spread_legs: list = field(default_factory=list)  # Multi-leg details
    # Broker routing
    broker: str = ""           # Which broker to execute on

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
        if self.target or self.target_price:
            d["target"] = self.target or self.target_price
        if self.entry_price:
            d["entry_price"] = self.entry_price
        if self.risk_reward:
            d["risk_reward"] = self.risk_reward
        if self.catalyst:
            d["catalyst"] = self.catalyst
        if self.catalyst_tier:
            d["catalyst_tier"] = self.catalyst_tier
        if self.candle_pattern:
            d["candle_pattern"] = self.candle_pattern
        # Options fields
        if self.option_type:
            d["option_type"] = self.option_type
        if self.strike:
            d["strike"] = self.strike
        if self.expiry:
            d["expiry"] = self.expiry
        if self.premium:
            d["premium"] = self.premium
        if self.iv:
            d["iv"] = self.iv
        if self.delta:
            d["delta"] = self.delta
        if self.contracts:
            d["contracts"] = self.contracts
        if self.spread_type:
            d["spread_type"] = self.spread_type
            d["spread_legs"] = self.spread_legs
        if self.broker:
            d["broker"] = self.broker
        return d
