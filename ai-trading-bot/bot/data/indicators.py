import pandas as pd
import numpy as np
from bot.data.models import Candle, IndicatorSet


def compute_indicators(candles: list) -> IndicatorSet:
    """Compute all technical indicators from a list of candles."""
    if len(candles) < 26:
        return IndicatorSet()

    closes = pd.Series([c.close for c in candles])
    highs = pd.Series([c.high for c in candles])
    lows = pd.Series([c.low for c in candles])
    volumes = pd.Series([float(c.volume) for c in candles])
    opens = pd.Series([c.open for c in candles])

    indicators = IndicatorSet()

    # RSI (14)
    indicators.rsi_14 = _rsi(closes, 14)

    # MACD (12, 26, 9)
    ema_12 = closes.ewm(span=12, adjust=False).mean()
    ema_26 = closes.ewm(span=26, adjust=False).mean()
    macd_line = ema_12 - ema_26
    macd_signal = macd_line.ewm(span=9, adjust=False).mean()

    indicators.ema_12 = round(ema_12.iloc[-1], 4)
    indicators.ema_26 = round(ema_26.iloc[-1], 4)
    indicators.macd_line = round(macd_line.iloc[-1], 4)
    indicators.macd_signal = round(macd_signal.iloc[-1], 4)
    indicators.macd_histogram = round((macd_line - macd_signal).iloc[-1], 4)

    # 8 EMA (key swing trading indicator)
    ema_8 = closes.ewm(span=8, adjust=False).mean()
    indicators.ema_8 = round(ema_8.iloc[-1], 4)

    # Bollinger Bands (20, 2)
    sma_20 = closes.rolling(window=20).mean()
    std_20 = closes.rolling(window=20).std()
    indicators.bb_upper = round((sma_20 + 2 * std_20).iloc[-1], 4)
    indicators.bb_middle = round(sma_20.iloc[-1], 4)
    indicators.bb_lower = round((sma_20 - 2 * std_20).iloc[-1], 4)

    # SMAs
    indicators.sma_20 = round(sma_20.iloc[-1], 4)
    if len(closes) >= 50:
        indicators.sma_50 = round(closes.rolling(window=50).mean().iloc[-1], 4)
    if len(closes) >= 200:
        indicators.sma_200 = round(closes.rolling(window=200).mean().iloc[-1], 4)

    # ATR (14)
    tr = pd.concat([
        highs - lows,
        (highs - closes.shift(1)).abs(),
        (lows - closes.shift(1)).abs(),
    ], axis=1).max(axis=1)
    indicators.atr_14 = round(tr.rolling(window=14).mean().iloc[-1], 4)

    # Volume SMA (20 and 50)
    indicators.volume_sma_20 = round(volumes.rolling(window=20).mean().iloc[-1], 2)
    if len(volumes) >= 50:
        indicators.volume_sma_50 = round(volumes.rolling(window=50).mean().iloc[-1], 2)

    # VWAP (Volume Weighted Average Price)
    typical_price = (highs + lows + closes) / 3
    cum_tp_vol = (typical_price * volumes).cumsum()
    cum_vol = volumes.cumsum()
    vwap = cum_tp_vol / cum_vol.replace(0, np.nan)
    indicators.vwap = round(vwap.iloc[-1], 4) if not np.isnan(vwap.iloc[-1]) else 0.0

    # Relative Volume (current volume vs 50-day average)
    if indicators.volume_sma_50 > 0:
        indicators.relative_volume = round(float(volumes.iloc[-1]) / indicators.volume_sma_50, 2)
    elif indicators.volume_sma_20 > 0:
        indicators.relative_volume = round(float(volumes.iloc[-1]) / indicators.volume_sma_20, 2)

    # Day change percentage
    if len(closes) >= 2:
        indicators.prev_close = round(closes.iloc[-2], 4)
        if indicators.prev_close > 0:
            indicators.day_change_pct = round(
                ((closes.iloc[-1] - indicators.prev_close) / indicators.prev_close) * 100, 2
            )

    return indicators


def _rsi(series: pd.Series, period: int = 14) -> float:
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta.where(delta < 0, 0.0))

    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    val = rsi.iloc[-1]
    return round(val if not np.isnan(val) else 50.0, 2)
