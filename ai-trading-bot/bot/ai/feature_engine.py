import numpy as np
from bot.data.models import MarketSnapshot


FEATURE_NAMES = [
    "close_open_ratio", "high_low_range", "close_sma20_ratio",
    "close_sma50_ratio", "close_sma200_ratio", "rsi_14",
    "macd_line", "macd_signal", "macd_histogram",
    "bb_position", "bb_width", "atr_14_pct",
    "volume_ratio", "ema12_ema26_diff",
    "day_of_week", "price_momentum_5",
]


def build_features(snapshot: MarketSnapshot) -> np.ndarray:
    """Build feature vector from a market snapshot."""
    latest = snapshot.latest
    ind = snapshot.indicators

    close = latest.close
    safe_close = close if close != 0 else 1.0

    features = [
        # Price ratios
        close / latest.open if latest.open != 0 else 1.0,
        (latest.high - latest.low) / safe_close,

        # SMA ratios
        close / ind.sma_20 if ind.sma_20 != 0 else 1.0,
        close / ind.sma_50 if ind.sma_50 != 0 else 1.0,
        close / ind.sma_200 if ind.sma_200 != 0 else 1.0,

        # Momentum indicators
        ind.rsi_14,
        ind.macd_line,
        ind.macd_signal,
        ind.macd_histogram,

        # Bollinger position (0=lower, 0.5=middle, 1=upper)
        (close - ind.bb_lower) / (ind.bb_upper - ind.bb_lower)
        if (ind.bb_upper - ind.bb_lower) != 0 else 0.5,

        # Bollinger width
        (ind.bb_upper - ind.bb_lower) / ind.bb_middle if ind.bb_middle != 0 else 0.0,

        # Volatility
        ind.atr_14 / safe_close,

        # Volume
        latest.volume / ind.volume_sma_20 if ind.volume_sma_20 != 0 else 1.0,

        # EMA spread
        (ind.ema_12 - ind.ema_26) / safe_close,

        # Day of week (0=Monday)
        0.0,  # Will be set by caller if date available

        # Price momentum (will be 0 if not enough candles)
        0.0,
    ]

    # Calculate momentum if enough candles
    candles = snapshot.candles
    if len(candles) >= 6:
        features[-1] = (candles[-1].close - candles[-6].close) / candles[-6].close if candles[-6].close != 0 else 0.0

    return np.array(features, dtype=np.float64)


def build_features_batch(snapshots: list) -> np.ndarray:
    """Build feature matrix from multiple snapshots."""
    return np.array([build_features(s) for s in snapshots])
