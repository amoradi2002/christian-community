import json
from bot.strategies.base import Strategy
from bot.strategies.mentorship import MentorshipStrategy
from bot.strategies.builtin.rsi_reversal import RSIReversalStrategy
from bot.strategies.builtin.macd_crossover import MACDCrossoverStrategy
from bot.strategies.builtin.bollinger_squeeze import BollingerSqueezeStrategy
from bot.strategies.builtin.pullback import PullbackStrategy
from bot.strategies.builtin.gap_and_go import GapAndGoStrategy
from bot.strategies.builtin.vwap_reclaim import VWAPReclaimStrategy
from bot.strategies.builtin.orb import ORBStrategy
from bot.strategies.builtin.swing_setups import (
    SwingEMAPullbackStrategy,
    SwingDowntrendBreakStrategy,
    SwingOversoldBounceStrategy,
    BearFlagStrategy,
)
from bot.strategies.store import list_strategies


class StrategyRegistry:
    def __init__(self):
        self._strategies: list[Strategy] = []

    def load_builtins(self):
        """Load all built-in strategies."""
        self._strategies.extend([
            # Original strategies
            RSIReversalStrategy(),
            MACDCrossoverStrategy(),
            BollingerSqueezeStrategy(),
            # Day trade strategies
            PullbackStrategy(),
            GapAndGoStrategy(),
            VWAPReclaimStrategy(),
            ORBStrategy(),
            # Swing trade strategies
            SwingEMAPullbackStrategy(),
            SwingDowntrendBreakStrategy(),
            SwingOversoldBounceStrategy(),
            # Short / bearish strategies
            BearFlagStrategy(),
        ])

    def load_mentorship_strategies(self):
        """Load user-defined mentorship strategies from the database."""
        db_strategies = list_strategies(active_only=True)
        for s in db_strategies:
            if s["type"] == "mentorship":
                rules = json.loads(s["rules_json"])
                ms = MentorshipStrategy.from_dict(rules)
                self._strategies.append(ms)

    def load_all(self):
        self.load_builtins()
        self.load_mentorship_strategies()

    def get_all(self) -> list[Strategy]:
        return self._strategies

    def get_by_name(self, name: str) -> Strategy | None:
        for s in self._strategies:
            if s.name == name:
                return s
        return None

    def get_by_style(self, style: str) -> list[Strategy]:
        """Get strategies by trading style (day, swing)."""
        style_map = {
            "day": ["Pullback Pattern", "Gap and Go", "VWAP Reclaim",
                     "Opening Range Breakout"],
            "swing": ["Swing: 8 EMA Pullback", "Swing: Downtrend Break",
                       "Swing: Oversold Bounce", "Bear Flag Breakdown"],
            "general": ["RSI Reversal", "MACD Crossover", "Bollinger Squeeze"],
        }
        names = style_map.get(style, [])
        return [s for s in self._strategies if s.name in names]

    def reload(self):
        """Reload all strategies (useful after adding new ones)."""
        self._strategies.clear()
        self.load_all()
