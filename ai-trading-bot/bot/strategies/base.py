from abc import ABC, abstractmethod
from bot.data.models import MarketSnapshot
from bot.engine.signal import Signal


class Strategy(ABC):
    name: str = ""
    description: str = ""

    @abstractmethod
    def analyze(self, snapshot: MarketSnapshot) -> Signal | None:
        """Analyze market snapshot and return a signal or None."""
        ...

    @abstractmethod
    def to_dict(self) -> dict:
        """Serialize strategy configuration."""
        ...

    @classmethod
    @abstractmethod
    def from_dict(cls, data: dict) -> "Strategy":
        """Deserialize strategy from dict."""
        ...
