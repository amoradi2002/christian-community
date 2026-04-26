"""
Mentorship Strategy - Learn from trading mentor's rules.

Users define strategies as structured conditions. The bot evaluates them,
tracks performance, and feeds results back into the AI model so it learns
which mentorship strategies actually work over time.

Example rules:
{
    "name": "RSI Dip Buy",
    "conditions": [
        {"indicator": "rsi_14", "operator": "<=", "value": 30},
        {"indicator": "macd_histogram", "operator": ">", "value": 0},
        {"indicator": "close", "operator": ">", "ref": "sma_200"}
    ],
    "signal": "BUY",
    "timeframe": "1d",
    "symbols": ["AAPL", "SPY"]
}
"""

import json
from bot.strategies.base import Strategy
from bot.data.models import MarketSnapshot
from bot.engine.signal import Signal

OPERATORS = {
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: abs(a - b) < 0.001,
    "crosses_above": lambda a, b: None,  # handled specially
    "crosses_below": lambda a, b: None,
}


class MentorshipStrategy(Strategy):
    def __init__(self, name, description, conditions, signal_action, symbols=None):
        self.name = name
        self.description = description
        self.conditions = conditions
        self.signal_action = signal_action
        self.symbols = symbols or []

    def _get_indicator_value(self, snapshot: MarketSnapshot, indicator_name: str) -> float:
        """Resolve an indicator name to its current value."""
        ind = snapshot.indicators
        latest = snapshot.latest

        mapping = {
            "rsi_14": ind.rsi_14,
            "macd_line": ind.macd_line,
            "macd_signal": ind.macd_signal,
            "macd_histogram": ind.macd_histogram,
            "bb_upper": ind.bb_upper,
            "bb_middle": ind.bb_middle,
            "bb_lower": ind.bb_lower,
            "sma_20": ind.sma_20,
            "sma_50": ind.sma_50,
            "sma_200": ind.sma_200,
            "ema_12": ind.ema_12,
            "ema_26": ind.ema_26,
            "atr_14": ind.atr_14,
            "volume_sma_20": ind.volume_sma_20,
            "close": latest.close,
            "open": latest.open,
            "high": latest.high,
            "low": latest.low,
            "volume": float(latest.volume),
        }
        return mapping.get(indicator_name, 0.0)

    def analyze(self, snapshot: MarketSnapshot) -> Signal | None:
        if self.symbols and snapshot.symbol not in self.symbols:
            return None

        reasons = []
        all_met = True

        for cond in self.conditions:
            indicator = cond["indicator"]
            operator = cond["operator"]
            left_val = self._get_indicator_value(snapshot, indicator)

            # Value can be a number or a reference to another indicator
            if "ref" in cond:
                right_val = self._get_indicator_value(snapshot, cond["ref"])
                compare_label = cond["ref"]
            else:
                right_val = float(cond["value"])
                compare_label = str(right_val)

            op_func = OPERATORS.get(operator)
            if op_func is None:
                continue

            result = op_func(left_val, right_val)
            if result:
                reasons.append(f"{indicator}({left_val:.2f}) {operator} {compare_label}({right_val:.2f})")
            else:
                all_met = False
                break

        if all_met and reasons:
            return Signal(
                action=self.signal_action,
                confidence=0.7,
                strategy_name=self.name,
                symbol=snapshot.symbol,
                price=snapshot.latest.close,
                reasons=reasons,
            )
        return None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "conditions": self.conditions,
            "signal": self.signal_action,
            "symbols": self.symbols,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MentorshipStrategy":
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            conditions=data["conditions"],
            signal_action=data["signal"],
            symbols=data.get("symbols", []),
        )
