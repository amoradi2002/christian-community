"""Tests for technical indicator calculations."""
import pytest
from bot.data.models import Candle, IndicatorSet
from bot.data.indicators import compute_indicators


class TestIndicators:
    """Test suite for indicator calculations."""

    def test_compute_indicators_returns_indicator_set(self, sample_candles):
        """compute_indicators should return an IndicatorSet."""
        result = compute_indicators(sample_candles)
        assert isinstance(result, IndicatorSet)

    def test_rsi_in_valid_range(self, sample_candles):
        """RSI should be between 0 and 100."""
        result = compute_indicators(sample_candles)
        assert 0 <= result.rsi_14 <= 100

    def test_sma_values_positive(self, sample_candles):
        """SMA values should be positive for positive price data."""
        result = compute_indicators(sample_candles)
        assert result.sma_20 > 0
        assert result.sma_50 > 0

    def test_bollinger_band_ordering(self, sample_candles):
        """BB upper > BB middle > BB lower."""
        result = compute_indicators(sample_candles)
        if result.bb_upper > 0:
            assert result.bb_upper >= result.bb_middle >= result.bb_lower

    def test_atr_positive(self, sample_candles):
        """ATR should be positive."""
        result = compute_indicators(sample_candles)
        assert result.atr_14 >= 0

    def test_volume_sma_positive(self, sample_candles):
        """Volume SMA should be positive."""
        result = compute_indicators(sample_candles)
        assert result.volume_sma_20 > 0

    def test_minimal_candles(self):
        """Should handle small candle lists gracefully."""
        candles = [
            Candle(date="2024-01-01", open=100, high=105, low=95, close=102, volume=1000000)
            for _ in range(5)
        ]
        result = compute_indicators(candles)
        assert isinstance(result, IndicatorSet)

    def test_ema_calculated(self, sample_candles):
        """EMA values should be calculated."""
        result = compute_indicators(sample_candles)
        assert result.ema_12 > 0
        assert result.ema_26 > 0

    def test_macd_components(self, sample_candles):
        """MACD line, signal, and histogram should all be computed."""
        result = compute_indicators(sample_candles)
        expected_hist = result.macd_line - result.macd_signal
        assert abs(result.macd_histogram - expected_hist) < 0.01
