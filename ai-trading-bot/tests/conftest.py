"""
Shared test fixtures for the AI Trading Bot test suite.
"""
import os
import sys
import pytest
from pathlib import Path

# Ensure bot package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Set test environment variables before any imports
os.environ.setdefault("ALPACA_API_KEY", "")
os.environ.setdefault("ALPACA_SECRET_KEY", "")
os.environ.setdefault("FINNHUB_API_KEY", "")
os.environ.setdefault("DISCORD_WEBHOOK_URL", "")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "")


@pytest.fixture
def sample_candles():
    """Generate realistic sample candle data for testing."""
    from bot.data.models import Candle
    import random
    random.seed(42)

    candles = []
    price = 150.0
    for i in range(300):
        change = random.uniform(-3, 3)
        open_ = price
        close = price + change
        high = max(open_, close) + random.uniform(0, 2)
        low = min(open_, close) - random.uniform(0, 2)
        volume = random.randint(1000000, 10000000)
        date = f"2024-{(i // 30) + 1:02d}-{(i % 30) + 1:02d}"

        candles.append(Candle(
            date=date,
            open=round(open_, 2),
            high=round(high, 2),
            low=round(low, 2),
            close=round(close, 2),
            volume=volume,
        ))
        price = close
    return candles


@pytest.fixture
def sample_indicators():
    """Generate sample indicator set."""
    from bot.data.models import IndicatorSet
    return IndicatorSet(
        rsi_14=55.0,
        macd_line=1.5,
        macd_signal=1.2,
        macd_histogram=0.3,
        bb_upper=160.0,
        bb_middle=155.0,
        bb_lower=150.0,
        sma_20=154.0,
        sma_50=152.0,
        sma_200=148.0,
        ema_8=155.0,
        ema_12=154.5,
        ema_26=153.0,
        atr_14=3.5,
        volume_sma_20=5000000,
        volume_sma_50=4500000,
        vwap=155.0,
        relative_volume=1.2,
        day_change_pct=0.5,
        prev_close=154.0,
    )


@pytest.fixture
def sample_snapshot(sample_candles, sample_indicators):
    """Generate a complete market snapshot."""
    from bot.data.models import MarketSnapshot
    return MarketSnapshot(
        symbol="AAPL",
        timeframe="1d",
        candles=sample_candles,
        indicators=sample_indicators,
    )


@pytest.fixture
def sample_signal():
    """Generate a sample trading signal."""
    from bot.engine.signal import Signal
    return Signal(
        action="BUY",
        confidence=0.78,
        strategy_name="RSI Reversal",
        symbol="AAPL",
        price=155.50,
        reasons=["RSI oversold bounce", "MACD bullish crossover"],
        style="swing",
        setup="RSI Reversal",
        stop_loss=150.0,
        target=165.0,
        risk_reward=2.7,
    )
