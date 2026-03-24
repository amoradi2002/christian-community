from abc import ABC, abstractmethod
from bot.engine.signal import Signal


class AlertChannel(ABC):
    @abstractmethod
    def send(self, signal: Signal) -> bool:
        """Send an alert. Returns True on success."""
        ...
