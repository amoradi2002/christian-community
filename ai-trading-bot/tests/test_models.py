"""Tests for data models."""
import pytest
from bot.data.models import Candle, IndicatorSet, MarketSnapshot


class TestCandle:
    def test_candle_creation(self):
        c = Candle(date="2024-01-01", open=100.0, high=105.0, low=95.0, close=102.0, volume=1000000)
        assert c.date == "2024-01-01"
        assert c.open == 100.0
        assert c.close == 102.0

    def test_candle_fields(self):
        c = Candle(date="2024-01-01", open=100, high=110, low=90, close=105, volume=5000000)
        assert c.high > c.low
        assert c.volume > 0


class TestIndicatorSet:
    def test_default_values(self):
        ind = IndicatorSet()
        assert ind.rsi_14 == 0.0
        assert ind.macd_line == 0.0
        assert ind.sma_20 == 0.0

    def test_custom_values(self):
        ind = IndicatorSet(rsi_14=65.0, sma_20=150.0)
        assert ind.rsi_14 == 65.0
        assert ind.sma_20 == 150.0


class TestMarketSnapshot:
    def test_snapshot_latest(self):
        candles = [
            Candle(date="2024-01-01", open=100, high=105, low=95, close=102, volume=1000000),
            Candle(date="2024-01-02", open=102, high=107, low=100, close=105, volume=1200000),
        ]
        snap = MarketSnapshot(symbol="AAPL", timeframe="1d", candles=candles)
        assert snap.latest.close == 105
        assert snap.symbol == "AAPL"
        assert snap.timeframe == "1d"

    def test_snapshot_with_indicators(self, sample_indicators):
        candles = [Candle(date="2024-01-01", open=100, high=105, low=95, close=102, volume=1000000)]
        snap = MarketSnapshot(symbol="SPY", timeframe="1d", candles=candles, indicators=sample_indicators)
        assert snap.indicators.rsi_14 == 55.0
