import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from bot.data.models import Candle
from bot.db.database import get_connection


def fetch_market_data(symbol, period="1y", interval="1d"):
    """
    Fetch market data from Yahoo Finance with smart caching.

    On first call: downloads full history and caches it.
    On subsequent calls: only fetches new data since last cached date.
    """
    conn = get_connection()

    # Check what we already have cached
    last_cached = conn.execute(
        "SELECT MAX(date) as last_date FROM market_cache WHERE symbol = ? AND timeframe = ?",
        (symbol, interval),
    ).fetchone()

    last_date = last_cached["last_date"] if last_cached else None
    today = datetime.now().strftime("%Y-%m-%d")

    # If cache is fresh (today's data exists), use it
    if last_date == today:
        conn.close()
        return get_cached_data(symbol, interval)

    # If we have some cached data, only fetch what's missing
    if last_date:
        # Fetch from 2 days before last cached (overlap to catch corrections)
        start_date = (datetime.strptime(last_date, "%Y-%m-%d") - timedelta(days=2)).strftime("%Y-%m-%d")
        ticker = yf.Ticker(symbol)
        df = ticker.history(start=start_date, interval=interval)
    else:
        # First time: fetch full history
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval)

    if df.empty:
        # Return cached data if API fails
        cached = get_cached_data(symbol, interval)
        conn.close()
        return cached if cached else []

    # Update cache with new/corrected data
    for date, row in df.iterrows():
        date_str = date.strftime("%Y-%m-%d") if interval == "1d" else date.strftime("%Y-%m-%d %H:%M")
        conn.execute(
            """INSERT OR REPLACE INTO market_cache
               (symbol, timeframe, date, open_price, high_price, low_price, close_price, volume)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (symbol, interval, date_str,
             round(row["Open"], 4), round(row["High"], 4),
             round(row["Low"], 4), round(row["Close"], 4),
             int(row["Volume"])),
        )

    conn.commit()
    conn.close()

    # Return full cached dataset
    return get_cached_data(symbol, interval)


def fetch_realtime_price(symbol) -> dict | None:
    """
    Get the latest real-time price for a symbol.
    Uses yfinance fast_info for the most current quote.
    """
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.fast_info

        return {
            "symbol": symbol,
            "price": round(info.last_price, 4),
            "open": round(info.open, 4) if hasattr(info, "open") else None,
            "high": round(info.day_high, 4) if hasattr(info, "day_high") else None,
            "low": round(info.day_low, 4) if hasattr(info, "day_low") else None,
            "volume": int(info.last_volume) if hasattr(info, "last_volume") else 0,
            "previous_close": round(info.previous_close, 4) if hasattr(info, "previous_close") else None,
            "market_cap": info.market_cap if hasattr(info, "market_cap") else None,
        }
    except Exception as e:
        print(f"Real-time price fetch failed for {symbol}: {e}")
        return None


def fetch_intraday(symbol, interval="15m", period="5d"):
    """
    Fetch intraday candles for day trading.
    Supported intervals: 1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h
    Note: 1m data only available for last 7 days, 2m/5m/15m for last 60 days.
    """
    ticker = yf.Ticker(symbol)
    df = ticker.history(period=period, interval=interval)

    if df.empty:
        return []

    candles = []
    conn = get_connection()
    for date, row in df.iterrows():
        date_str = date.strftime("%Y-%m-%d %H:%M")
        candle = Candle(
            date=date_str,
            open=round(row["Open"], 4),
            high=round(row["High"], 4),
            low=round(row["Low"], 4),
            close=round(row["Close"], 4),
            volume=int(row["Volume"]),
        )
        candles.append(candle)

        conn.execute(
            """INSERT OR REPLACE INTO market_cache
               (symbol, timeframe, date, open_price, high_price, low_price, close_price, volume)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (symbol, interval, date_str, candle.open, candle.high, candle.low, candle.close, candle.volume),
        )

    conn.commit()
    conn.close()
    return candles


def get_cached_data(symbol, timeframe="1d", limit=365):
    """Get cached market data from SQLite."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT date, open_price, high_price, low_price, close_price, volume
           FROM market_cache
           WHERE symbol = ? AND timeframe = ?
           ORDER BY date DESC LIMIT ?""",
        (symbol, timeframe, limit),
    ).fetchall()
    conn.close()

    return [
        Candle(
            date=r["date"],
            open=r["open_price"],
            high=r["high_price"],
            low=r["low_price"],
            close=r["close_price"],
            volume=r["volume"],
        )
        for r in reversed(rows)
    ]
