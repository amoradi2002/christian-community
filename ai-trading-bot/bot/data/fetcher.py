import yfinance as yf
import pandas as pd
from bot.data.models import Candle
from bot.db.database import get_connection


def fetch_market_data(symbol, period="1y", interval="1d"):
    """Fetch market data from Yahoo Finance and cache it."""
    ticker = yf.Ticker(symbol)
    df = ticker.history(period=period, interval=interval)

    if df.empty:
        return []

    candles = []
    conn = get_connection()
    for date, row in df.iterrows():
        date_str = date.strftime("%Y-%m-%d")
        candle = Candle(
            date=date_str,
            open=round(row["Open"], 4),
            high=round(row["High"], 4),
            low=round(row["Low"], 4),
            close=round(row["Close"], 4),
            volume=int(row["Volume"]),
        )
        candles.append(candle)

        # Cache to database
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
