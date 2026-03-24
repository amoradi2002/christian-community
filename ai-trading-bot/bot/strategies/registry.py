import json
from bot.strategies.base import Strategy
from bot.strategies.mentorship import MentorshipStrategy
from bot.strategies.builtin.rsi_reversal import RSIReversalStrategy
from bot.strategies.builtin.macd_crossover import MACDCrossoverStrategy
from bot.strategies.builtin.bollinger_squeeze import BollingerSqueezeStrategy
from bot.strategies.store import list_strategies


class StrategyRegistry:
    def __init__(self):
        self._strategies: list[Strategy] = []

    def load_builtins(self):
        """Load all built-in strategies."""
        self._strategies.extend([
            RSIReversalStrategy(),
            MACDCrossoverStrategy(),
            BollingerSqueezeStrategy(),
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

    def reload(self):
        """Reload all strategies (useful after adding new ones)."""
        self._strategies.clear()
        self.load_all()
