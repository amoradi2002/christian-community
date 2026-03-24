from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Candle:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass
class IndicatorSet:
    rsi_14: float = 0.0
    macd_line: float = 0.0
    macd_signal: float = 0.0
    macd_histogram: float = 0.0
    bb_upper: float = 0.0
    bb_middle: float = 0.0
    bb_lower: float = 0.0
    sma_20: float = 0.0
    sma_50: float = 0.0
    sma_200: float = 0.0
    ema_12: float = 0.0
    ema_26: float = 0.0
    atr_14: float = 0.0
    volume_sma_20: float = 0.0


@dataclass
class MarketSnapshot:
    symbol: str
    timeframe: str
    candles: list  # list[Candle]
    indicators: IndicatorSet = field(default_factory=IndicatorSet)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def latest(self) -> Candle:
        return self.candles[-1]
