"""
Feature Engineering - Builds 40+ features from market snapshots.

Features are grouped into categories:
  - Price structure (ratios, ranges, gaps)
  - Trend (SMA/EMA ratios, ADX, regime)
  - Momentum (RSI, MACD, ROC, Stochastic)
  - Volatility (ATR, Bollinger, ranges)
  - Volume (OBV, relative volume, profile)
  - Pattern (candlestick scores, consecutive days)
  - Calendar (day of week)
"""

import logging
import numpy as np
import pandas as pd
from bot.data.models import MarketSnapshot

logger = logging.getLogger(__name__)

# ── Master feature list (order must match build_features output) ─────────────
FEATURE_NAMES = [
    # --- Price structure (7) ---
    "close_open_ratio",
    "high_low_range_pct",
    "gap_pct",
    "intraday_momentum",
    "hl_range_avg_5d",
    "dist_52w_high",
    "dist_52w_low",
    # --- Trend (9) ---
    "close_sma20_ratio",
    "close_sma50_ratio",
    "close_sma200_ratio",
    "ema12_ema26_diff",
    "sma20_slope",
    "sma50_slope",
    "adx",
    "trend_direction",
    "trend_strength",
    # --- Momentum (12) ---
    "rsi_14",
    "macd_line",
    "macd_signal",
    "macd_histogram",
    "roc_5",
    "roc_10",
    "roc_20",
    "stoch_k",
    "stoch_d",
    "price_momentum_5",
    "price_momentum_10",
    "consecutive_direction",
    # --- Volatility (5) ---
    "bb_position",
    "bb_width",
    "atr_14_pct",
    "volatility_ratio",
    "realized_vol_10",
    # --- Volume (5) ---
    "volume_ratio",
    "volume_ratio_50",
    "obv_roc_10",
    "volume_profile_ratio",
    "relative_volume",
    # --- Pattern (3) ---
    "hammer_score",
    "engulfing_score",
    "doji_score",
    # --- Calendar (1) ---
    "day_of_week",
]

NUM_FEATURES = len(FEATURE_NAMES)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _safe_div(a, b, default=0.0):
    """Safe division that handles zero, None, nan."""
    try:
        if b is None or b == 0 or (isinstance(b, float) and np.isnan(b)):
            return default
        result = a / b
        if np.isnan(result) or np.isinf(result):
            return default
        return result
    except (TypeError, ZeroDivisionError, ValueError):
        return default


def _series_from_candles(candles, attr):
    """Extract a pandas Series for a candle attribute."""
    return pd.Series([getattr(c, attr) for c in candles], dtype=np.float64)


def _roc(series, period):
    """Rate of change over N periods."""
    if len(series) <= period:
        return 0.0
    prev = series.iloc[-period - 1]
    curr = series.iloc[-1]
    return _safe_div(curr - prev, abs(prev))


def _stochastic(highs, lows, closes, k_period=14, d_period=3):
    """Compute Stochastic %K and %D."""
    if len(closes) < k_period:
        return 50.0, 50.0
    lowest = lows.rolling(window=k_period).min()
    highest = highs.rolling(window=k_period).max()
    denom = highest - lowest
    k = 100 * (closes - lowest) / denom.replace(0, np.nan)
    k = k.fillna(50.0)
    d = k.rolling(window=d_period).mean().fillna(50.0)
    return float(k.iloc[-1]), float(d.iloc[-1])


def _adx(highs, lows, closes, period=14):
    """Compute ADX (Average Directional Index)."""
    if len(closes) < period * 2:
        return 25.0  # neutral default

    plus_dm = highs.diff()
    minus_dm = -lows.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

    tr = pd.concat([
        highs - lows,
        (highs - closes.shift(1)).abs(),
        (lows - closes.shift(1)).abs(),
    ], axis=1).max(axis=1)

    atr = tr.rolling(window=period).mean()
    plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr.replace(0, np.nan))
    minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr.replace(0, np.nan))

    dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan))
    adx_val = dx.rolling(window=period).mean()

    val = adx_val.iloc[-1]
    return float(val) if not np.isnan(val) else 25.0


def _obv(closes, volumes):
    """On-Balance Volume."""
    direction = np.sign(closes.diff()).fillna(0)
    return (direction * volumes).cumsum()


def _candlestick_scores(candles):
    """Score candlestick patterns as numeric values in [-1, 1].

    Returns (hammer_score, engulfing_score, doji_score).
    """
    if len(candles) < 2:
        return 0.0, 0.0, 0.0

    c = candles[-1]
    p = candles[-2]
    body = c.close - c.open
    body_abs = abs(body)
    hl_range = c.high - c.low
    safe_range = hl_range if hl_range > 0 else 0.0001

    # -- Hammer / Inverted Hammer --
    lower_shadow = min(c.open, c.close) - c.low
    upper_shadow = c.high - max(c.open, c.close)
    hammer = 0.0
    if body_abs < safe_range * 0.35:
        if lower_shadow > body_abs * 2:
            hammer = 1.0   # bullish hammer
        elif upper_shadow > body_abs * 2:
            hammer = -1.0  # shooting star (bearish)

    # -- Engulfing --
    engulfing = 0.0
    p_body = p.close - p.open
    if p_body < 0 and body > 0 and c.open <= p.close and c.close >= p.open:
        engulfing = 1.0   # bullish engulfing
    elif p_body > 0 and body < 0 and c.open >= p.close and c.close <= p.open:
        engulfing = -1.0  # bearish engulfing

    # -- Doji --
    doji = 0.0
    if body_abs < safe_range * 0.1:
        doji = 1.0  # indecision

    return hammer, engulfing, doji


# ── Main feature builder ────────────────────────────────────────────────────

def build_features(snapshot: MarketSnapshot) -> np.ndarray:
    """Build a feature vector of length NUM_FEATURES from a MarketSnapshot.

    Handles missing data gracefully -- every computation is wrapped so that
    NaN / zero-division / short history returns a sensible default.
    """
    candles = snapshot.candles
    latest = snapshot.latest
    ind = snapshot.indicators

    close = latest.close
    safe_close = close if close and close != 0 else 1.0

    closes = _series_from_candles(candles, "close")
    highs = _series_from_candles(candles, "high")
    lows = _series_from_candles(candles, "low")
    volumes = _series_from_candles(candles, "volume").astype(float)
    opens = _series_from_candles(candles, "open")

    n = len(candles)

    # ── Price structure ──────────────────────────────────────────────────
    close_open_ratio = _safe_div(close, latest.open, 1.0)
    high_low_range_pct = _safe_div(latest.high - latest.low, safe_close)

    # Gap from previous close
    gap_pct = 0.0
    if n >= 2:
        prev_close = candles[-2].close
        gap_pct = _safe_div(latest.open - prev_close, abs(prev_close))

    # Intraday momentum: where close sits in today's range
    intraday_momentum = _safe_div(
        close - latest.low, latest.high - latest.low, 0.5
    )

    # Average high-low range as % of price over last 5 days
    hl_range_avg_5d = 0.0
    if n >= 5:
        last5_ranges = (highs.iloc[-5:] - lows.iloc[-5:]) / closes.iloc[-5:].replace(0, 1.0)
        hl_range_avg_5d = float(last5_ranges.mean())

    # Distance from 52-week high/low
    dist_52w_high = 0.0
    dist_52w_low = 0.0
    lookback_252 = min(n, 252)
    if lookback_252 > 0:
        high_252 = float(highs.iloc[-lookback_252:].max())
        low_252 = float(lows.iloc[-lookback_252:].min())
        dist_52w_high = _safe_div(close - high_252, abs(high_252))
        dist_52w_low = _safe_div(close - low_252, abs(low_252)) if low_252 != 0 else 0.0

    # ── Trend ────────────────────────────────────────────────────────────
    close_sma20 = _safe_div(close, ind.sma_20, 1.0) if ind.sma_20 else 1.0
    close_sma50 = _safe_div(close, ind.sma_50, 1.0) if ind.sma_50 else 1.0
    close_sma200 = _safe_div(close, ind.sma_200, 1.0) if ind.sma_200 else 1.0
    ema12_ema26 = _safe_div(ind.ema_12 - ind.ema_26, safe_close) if ind.ema_12 and ind.ema_26 else 0.0

    # SMA slopes (% change over 5 days)
    sma20_slope = 0.0
    sma50_slope = 0.0
    if n >= 25:
        sma20_series = closes.rolling(20).mean()
        if len(sma20_series.dropna()) >= 6:
            sma20_slope = _safe_div(
                sma20_series.iloc[-1] - sma20_series.iloc[-6],
                abs(sma20_series.iloc[-6])
            )
    if n >= 55:
        sma50_series = closes.rolling(50).mean()
        if len(sma50_series.dropna()) >= 6:
            sma50_slope = _safe_div(
                sma50_series.iloc[-1] - sma50_series.iloc[-6],
                abs(sma50_series.iloc[-6])
            )

    adx_val = _adx(highs, lows, closes) if n >= 30 else 25.0

    # Market regime: trend direction (+1 up, -1 down, 0 flat)
    trend_direction = 0.0
    trend_strength = 0.0
    if ind.sma_20 and ind.sma_50:
        if ind.sma_20 > ind.sma_50:
            trend_direction = 1.0
        elif ind.sma_20 < ind.sma_50:
            trend_direction = -1.0
        trend_strength = abs(_safe_div(ind.sma_20 - ind.sma_50, ind.sma_50))

    # ── Momentum ─────────────────────────────────────────────────────────
    rsi_14 = ind.rsi_14 if ind.rsi_14 else 50.0
    macd_line = ind.macd_line if ind.macd_line is not None else 0.0
    macd_signal = ind.macd_signal if ind.macd_signal is not None else 0.0
    macd_histogram = ind.macd_histogram if ind.macd_histogram is not None else 0.0

    roc_5 = _roc(closes, 5) if n > 5 else 0.0
    roc_10 = _roc(closes, 10) if n > 10 else 0.0
    roc_20 = _roc(closes, 20) if n > 20 else 0.0

    stoch_k, stoch_d = _stochastic(highs, lows, closes) if n >= 14 else (50.0, 50.0)

    price_mom_5 = _roc(closes, 5) if n > 5 else 0.0
    price_mom_10 = _roc(closes, 10) if n > 10 else 0.0

    # Consecutive up/down days: positive = up streak, negative = down streak
    consec = 0.0
    if n >= 2:
        direction = 0
        for i in range(len(candles) - 1, 0, -1):
            d = 1 if candles[i].close > candles[i - 1].close else -1
            if direction == 0:
                direction = d
                consec = d
            elif d == direction:
                consec += d
            else:
                break

    # ── Volatility ───────────────────────────────────────────────────────
    bb_range = ind.bb_upper - ind.bb_lower if ind.bb_upper and ind.bb_lower else 0.0
    bb_position = _safe_div(close - ind.bb_lower, bb_range, 0.5) if bb_range != 0 else 0.5
    bb_width = _safe_div(bb_range, ind.bb_middle) if ind.bb_middle else 0.0
    atr_14_pct = _safe_div(ind.atr_14, safe_close)

    # Volatility ratio: current ATR vs 20-day average ATR
    volatility_ratio = 1.0
    if n >= 34:
        tr = pd.concat([
            highs - lows,
            (highs - closes.shift(1)).abs(),
            (lows - closes.shift(1)).abs(),
        ], axis=1).max(axis=1)
        atr_series = tr.rolling(14).mean().dropna()
        if len(atr_series) >= 20:
            avg_atr_20 = float(atr_series.iloc[-20:].mean())
            volatility_ratio = _safe_div(float(atr_series.iloc[-1]), avg_atr_20, 1.0)

    # Realized volatility (10-day annualized)
    realized_vol_10 = 0.0
    if n >= 11:
        log_returns = np.log(closes / closes.shift(1)).dropna()
        if len(log_returns) >= 10:
            realized_vol_10 = float(log_returns.iloc[-10:].std() * np.sqrt(252))

    # ── Volume ───────────────────────────────────────────────────────────
    vol_ratio = _safe_div(latest.volume, ind.volume_sma_20, 1.0) if ind.volume_sma_20 else 1.0
    vol_ratio_50 = _safe_div(latest.volume, ind.volume_sma_50, 1.0) if ind.volume_sma_50 else 1.0

    # OBV rate of change (10-day)
    obv_roc_10 = 0.0
    if n >= 12:
        obv = _obv(closes, volumes)
        if len(obv) >= 11:
            obv_prev = float(obv.iloc[-11])
            obv_now = float(obv.iloc[-1])
            obv_roc_10 = _safe_div(obv_now - obv_prev, abs(obv_prev)) if obv_prev != 0 else 0.0

    # Volume profile: ratio of above-average volume days in last 20
    volume_profile_ratio = 0.5
    if n >= 20 and ind.volume_sma_20:
        recent_vols = volumes.iloc[-20:]
        above = (recent_vols > ind.volume_sma_20).sum()
        volume_profile_ratio = float(above) / 20.0

    rel_volume = ind.relative_volume if ind.relative_volume else 1.0

    # ── Pattern ──────────────────────────────────────────────────────────
    hammer, engulfing, doji = _candlestick_scores(candles)

    # ── Calendar ─────────────────────────────────────────────────────────
    day_of_week = 0.0
    if latest.date:
        try:
            day_of_week = float(pd.Timestamp(latest.date).dayofweek)
        except Exception:
            day_of_week = 0.0

    # ── Assemble vector ──────────────────────────────────────────────────
    features = np.array([
        # Price structure (7)
        close_open_ratio,
        high_low_range_pct,
        gap_pct,
        intraday_momentum,
        hl_range_avg_5d,
        dist_52w_high,
        dist_52w_low,
        # Trend (9)
        close_sma20,
        close_sma50,
        close_sma200,
        ema12_ema26,
        sma20_slope,
        sma50_slope,
        adx_val,
        trend_direction,
        trend_strength,
        # Momentum (12)
        rsi_14,
        macd_line,
        macd_signal,
        macd_histogram,
        roc_5,
        roc_10,
        roc_20,
        stoch_k,
        stoch_d,
        price_mom_5,
        price_mom_10,
        consec,
        # Volatility (5)
        bb_position,
        bb_width,
        atr_14_pct,
        volatility_ratio,
        realized_vol_10,
        # Volume (5)
        vol_ratio,
        vol_ratio_50,
        obv_roc_10,
        volume_profile_ratio,
        rel_volume,
        # Pattern (3)
        hammer,
        engulfing,
        doji,
        # Calendar (1)
        day_of_week,
    ], dtype=np.float64)

    assert len(features) == NUM_FEATURES, (
        f"Feature count mismatch: built {len(features)}, expected {NUM_FEATURES}"
    )

    # Final NaN / Inf cleanup
    features = np.nan_to_num(features, nan=0.0, posinf=0.0, neginf=0.0)
    return features


def build_features_batch(snapshots: list) -> np.ndarray:
    """Build feature matrix from multiple snapshots."""
    return np.array([build_features(s) for s in snapshots])
