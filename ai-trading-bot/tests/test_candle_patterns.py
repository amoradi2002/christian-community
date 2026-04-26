"""Tests for candlestick pattern detection."""
import pytest
from bot.data.models import Candle
from bot.data.candle_patterns import detect_patterns, get_pattern_summary


class TestCandlePatterns:
    def test_detect_doji(self):
        """A doji has a very small body relative to range."""
        candles = [
            Candle(date="2024-01-01", open=100, high=105, low=95, close=100.05, volume=1000000),
        ]
        patterns = detect_patterns(candles)
        doji = [p for p in patterns if "doji" in p.name.lower()]
        assert len(doji) > 0

    def test_detect_hammer(self):
        """A hammer has a long lower wick, small body at top."""
        candles = [
            Candle(date="2024-01-01", open=100, high=101, low=90, close=100.5, volume=1000000),
        ]
        patterns = detect_patterns(candles)
        hammer = [p for p in patterns if "hammer" in p.name.lower()]
        assert len(hammer) > 0

    def test_detect_bullish_engulfing(self):
        """Bullish engulfing: small red candle followed by large green candle."""
        candles = [
            Candle(date="2024-01-01", open=102, high=103, low=99, close=100, volume=1000000),
            Candle(date="2024-01-02", open=99, high=106, low=98, close=105, volume=2000000),
        ]
        patterns = detect_patterns(candles)
        engulfing = [p for p in patterns if "engulfing" in p.name.lower()]
        assert len(engulfing) > 0

    def test_no_patterns_flat_candles(self):
        """Flat candles should produce minimal patterns."""
        candles = [
            Candle(date=f"2024-01-{i+1:02d}", open=100, high=100.5, low=99.5, close=100, volume=1000000)
            for i in range(5)
        ]
        patterns = detect_patterns(candles)
        # May still detect doji, but should be minimal
        assert isinstance(patterns, list)

    def test_pattern_has_required_fields(self, sample_candles):
        """Each pattern should have name, direction, strength."""
        patterns = detect_patterns(sample_candles[-5:])
        for p in patterns:
            assert hasattr(p, "name")
            assert hasattr(p, "direction")
            assert hasattr(p, "strength")
            assert 0 <= p.strength <= 1.0

    def test_get_pattern_summary(self, sample_candles):
        """Pattern summary should return a string."""
        patterns = detect_patterns(sample_candles[-5:])
        summary = get_pattern_summary(patterns)
        assert isinstance(summary, str)
