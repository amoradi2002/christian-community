"""
Alpaca Markets data provider - real-time quotes, 1m/5m bars, and websocket streaming.

Requires ALPACA_API_KEY and ALPACA_SECRET_KEY in .env file.
Free tier: 200 req/min, IEX real-time data.
Paid tier: unlimited, SIP (all exchanges) data.
"""

import os
from datetime import datetime, timedelta

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import (
    StockBarsRequest,
    StockLatestQuoteRequest,
    StockSnapshotRequest,
)
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

from bot.data.models import Candle
from bot.db.database import get_connection


# Map string intervals to Alpaca TimeFrame objects
TIMEFRAME_MAP = {
    "1m": TimeFrame(1, TimeFrameUnit.Minute),
    "5m": TimeFrame(5, TimeFrameUnit.Minute),
    "15m": TimeFrame(15, TimeFrameUnit.Minute),
    "30m": TimeFrame(30, TimeFrameUnit.Minute),
    "1h": TimeFrame(1, TimeFrameUnit.Hour),
    "1d": TimeFrame(1, TimeFrameUnit.Day),
    "1w": TimeFrame(1, TimeFrameUnit.Week),
}


def _get_client() -> StockHistoricalDataClient:
    """Create Alpaca data client from env vars."""
    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")
    if not api_key or not secret_key:
        raise ValueError("ALPACA_API_KEY and ALPACA_SECRET_KEY must be set in .env")
    return StockHistoricalDataClient(api_key, secret_key)


def fetch_alpaca_bars(symbol: str, interval: str = "1d", days: int = 365) -> list[Candle]:
    """
    Fetch historical bars from Alpaca with smart caching.

    Args:
        symbol: Stock ticker (e.g. "AAPL")
        interval: Bar size - "1m", "5m", "15m", "30m", "1h", "1d", "1w"
        days: How many days of history to fetch
    """
    client = _get_client()
    timeframe = TIMEFRAME_MAP.get(interval)
    if not timeframe:
        raise ValueError(f"Unsupported interval: {interval}. Use: {list(TIMEFRAME_MAP.keys())}")

    conn = get_connection()

    # Check cache freshness
    last_cached = conn.execute(
        "SELECT MAX(date) as last_date FROM market_cache WHERE symbol = ? AND timeframe = ?",
        (symbol, interval),
    ).fetchone()

    last_date = last_cached["last_date"] if last_cached else None
    now = datetime.now()

    # For intraday, cache is fresh if less than 2 minutes old
    # For daily, cache is fresh if today's data exists
    if last_date:
        if interval == "1d" and last_date == now.strftime("%Y-%m-%d"):
            conn.close()
            return _get_cached(symbol, interval)
        elif interval != "1d":
            try:
                last_dt = datetime.strptime(last_date, "%Y-%m-%d %H:%M")
                if (now - last_dt).total_seconds() < 120:
                    conn.close()
                    return _get_cached(symbol, interval)
            except ValueError:
                pass

    # Determine start date
    if last_date and interval == "1d":
        start = datetime.strptime(last_date, "%Y-%m-%d") - timedelta(days=1)
    else:
        start = now - timedelta(days=days)

    try:
        request = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=timeframe,
            start=start,
        )
        bars = client.get_stock_bars(request)
        bar_list = bars[symbol] if symbol in bars else []
    except Exception as e:
        print(f"Alpaca bars fetch failed for {symbol}: {e}")
        cached = _get_cached(symbol, interval)
        conn.close()
        return cached if cached else []

    # Cache results
    for bar in bar_list:
        if interval == "1d":
            date_str = bar.timestamp.strftime("%Y-%m-%d")
        else:
            date_str = bar.timestamp.strftime("%Y-%m-%d %H:%M")

        conn.execute(
            """INSERT OR REPLACE INTO market_cache
               (symbol, timeframe, date, open_price, high_price, low_price, close_price, volume)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (symbol, interval, date_str,
             round(bar.open, 4), round(bar.high, 4),
             round(bar.low, 4), round(bar.close, 4),
             int(bar.volume)),
        )

    conn.commit()
    conn.close()
    return _get_cached(symbol, interval)


def fetch_alpaca_realtime(symbol: str) -> dict | None:
    """
    Get real-time quote from Alpaca (no 15-min delay like Yahoo).
    Returns latest quote with bid/ask spread.
    """
    try:
        client = _get_client()
        request = StockLatestQuoteRequest(symbol_or_symbols=symbol)
        quotes = client.get_stock_latest_quote(request)
        quote = quotes[symbol]

        # Also get snapshot for OHLCV context
        snap_request = StockSnapshotRequest(symbol_or_symbols=symbol)
        snapshots = client.get_stock_snapshot(snap_request)
        snap = snapshots.get(symbol)

        result = {
            "symbol": symbol,
            "bid": round(quote.bid_price, 4),
            "ask": round(quote.ask_price, 4),
            "price": round((quote.bid_price + quote.ask_price) / 2, 4),  # midpoint
            "bid_size": quote.bid_size,
            "ask_size": quote.ask_size,
            "spread": round(quote.ask_price - quote.bid_price, 4),
        }

        if snap and snap.daily_bar:
            result.update({
                "open": round(snap.daily_bar.open, 4),
                "high": round(snap.daily_bar.high, 4),
                "low": round(snap.daily_bar.low, 4),
                "close": round(snap.daily_bar.close, 4),
                "volume": int(snap.daily_bar.volume),
                "previous_close": round(snap.previous_daily_bar.close, 4) if snap.previous_daily_bar else None,
            })

        return result
    except Exception as e:
        print(f"Alpaca real-time fetch failed for {symbol}: {e}")
        return None


def fetch_alpaca_snapshot(symbols: list[str]) -> dict:
    """
    Batch fetch snapshots for multiple symbols (efficient for watchlist).
    Returns dict of symbol -> price info.
    """
    try:
        client = _get_client()
        request = StockSnapshotRequest(symbol_or_symbols=symbols)
        snapshots = client.get_stock_snapshot(request)

        results = {}
        for sym, snap in snapshots.items():
            if snap and snap.latest_quote:
                q = snap.latest_quote
                d = snap.daily_bar
                prev = snap.previous_daily_bar

                results[sym] = {
                    "symbol": sym,
                    "price": round((q.bid_price + q.ask_price) / 2, 4),
                    "bid": round(q.bid_price, 4),
                    "ask": round(q.ask_price, 4),
                    "open": round(d.open, 4) if d else None,
                    "high": round(d.high, 4) if d else None,
                    "low": round(d.low, 4) if d else None,
                    "volume": int(d.volume) if d else 0,
                    "previous_close": round(prev.close, 4) if prev else None,
                }

        return results
    except Exception as e:
        print(f"Alpaca snapshot batch failed: {e}")
        return {}


def _get_cached(symbol: str, timeframe: str, limit: int = 500) -> list[Candle]:
    """Get cached data from SQLite."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT date, open_price, high_price, low_price, close_price, volume
           FROM market_cache WHERE symbol = ? AND timeframe = ?
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
