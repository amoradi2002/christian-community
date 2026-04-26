"""
Earnings data provider - calendar, estimates, and earnings surprises.

Data sources (in priority order):
1. Finnhub (free API, reliable) - calendar, EPS estimates, surprises
2. Yahoo Finance (free, no key) - earnings dates, estimates, history
3. Earnings Whispers (best-effort scrape) - whisper numbers only

Note: Earnings Whispers has no API and uses JavaScript rendering,
so scraping is fragile. Finnhub is the primary source.
"""

import os
import re
import json
from datetime import datetime, timedelta
from dataclasses import dataclass, field

import requests

from bot.db.database import get_connection


@dataclass
class EarningsEvent:
    """Represents an upcoming or past earnings event."""
    symbol: str
    company: str = ""
    date: str = ""            # YYYY-MM-DD
    time: str = ""            # "BMO" (before market open), "AMC" (after market close)
    eps_estimate: float | None = None
    eps_whisper: float | None = None   # The whisper/crowd estimate
    eps_actual: float | None = None
    revenue_estimate: float | None = None
    revenue_actual: float | None = None
    surprise_pct: float | None = None
    confirmed: bool = False
    quarters_beat: int = 0     # How many of last 4 quarters beat estimates
    source: str = ""           # "finnhub", "yahoo", "whispers"

    @property
    def has_whisper(self) -> bool:
        return self.eps_whisper is not None

    @property
    def beat_whisper(self) -> bool | None:
        if self.eps_actual is not None and self.eps_whisper is not None:
            return self.eps_actual > self.eps_whisper
        return None

    @property
    def beat_estimate(self) -> bool | None:
        if self.eps_actual is not None and self.eps_estimate is not None:
            return self.eps_actual > self.eps_estimate
        return None

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "company": self.company,
            "date": self.date,
            "time": self.time,
            "eps_estimate": self.eps_estimate,
            "eps_whisper": self.eps_whisper,
            "eps_actual": self.eps_actual,
            "revenue_estimate": self.revenue_estimate,
            "revenue_actual": self.revenue_actual,
            "surprise_pct": self.surprise_pct,
            "confirmed": self.confirmed,
            "quarters_beat": self.quarters_beat,
            "source": self.source,
            "has_whisper": self.has_whisper,
            "beat_whisper": self.beat_whisper,
            "beat_estimate": self.beat_estimate,
        }


# ─── Finnhub (Primary Source) ─────────────────────────────────────────

def _finnhub_get(endpoint: str, params: dict | None = None) -> dict | list | None:
    """Make request to Finnhub API."""
    token = os.getenv("FINNHUB_API_KEY")
    if not token:
        return None

    try:
        params = params or {}
        params["token"] = token
        resp = requests.get(
            f"https://finnhub.io/api/v1/{endpoint}",
            params=params,
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception:
        return None


def _finnhub_earnings_calendar(from_date: str, to_date: str) -> list[EarningsEvent]:
    """Fetch earnings calendar from Finnhub."""
    data = _finnhub_get("calendar/earnings", {
        "from": from_date,
        "to": to_date,
    })

    if not data or "earningsCalendar" not in data:
        return []

    events = []
    for item in data["earningsCalendar"]:
        event = EarningsEvent(
            symbol=item.get("symbol", ""),
            date=item.get("date", ""),
            time=_map_finnhub_hour(item.get("hour", "")),
            eps_estimate=_safe_float(item.get("epsEstimate")),
            eps_actual=_safe_float(item.get("epsActual")),
            revenue_estimate=_safe_float(item.get("revenueEstimate")),
            revenue_actual=_safe_float(item.get("revenueActual")),
            quarters_beat=item.get("quarter", 0),
            source="finnhub",
        )

        # Calculate surprise
        if event.eps_actual is not None and event.eps_estimate is not None and event.eps_estimate != 0:
            event.surprise_pct = round(
                ((event.eps_actual - event.eps_estimate) / abs(event.eps_estimate)) * 100, 2
            )

        events.append(event)

    return events


def _finnhub_earnings_surprises(symbol: str) -> list[EarningsEvent]:
    """Fetch earnings surprise history from Finnhub."""
    data = _finnhub_get("stock/earnings", {"symbol": symbol.upper()})
    if not data or not isinstance(data, list):
        return []

    events = []
    for item in data:
        event = EarningsEvent(
            symbol=symbol.upper(),
            date=item.get("period", ""),
            eps_estimate=_safe_float(item.get("estimate")),
            eps_actual=_safe_float(item.get("actual")),
            surprise_pct=_safe_float(item.get("surprisePercent")),
            source="finnhub",
        )
        events.append(event)

    return events


def _map_finnhub_hour(hour: str) -> str:
    """Map Finnhub hour codes to readable format."""
    mapping = {"bmo": "BMO", "amc": "AMC", "dmh": "DMH"}
    return mapping.get(hour.lower(), hour.upper()) if hour else ""


# ─── Yahoo Finance (Fallback) ─────────────────────────────────────────

def _yahoo_next_earnings(symbol: str) -> EarningsEvent | None:
    """Get next earnings date from Yahoo Finance."""
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        cal = ticker.calendar

        if cal is None or cal.empty:
            return None

        if "Earnings Date" in cal.index:
            dates = cal.loc["Earnings Date"]
            if len(dates) > 0:
                event = EarningsEvent(
                    symbol=symbol.upper(),
                    date=str(dates.iloc[0])[:10],
                    source="yahoo",
                )
                if "EPS Estimate" in cal.index:
                    event.eps_estimate = _safe_float(cal.loc["EPS Estimate"].iloc[0])
                if "Revenue Estimate" in cal.index:
                    event.revenue_estimate = _safe_float(cal.loc["Revenue Estimate"].iloc[0])
                return event
        return None
    except Exception:
        return None


def _yahoo_earnings_history(symbol: str, quarters: int = 8) -> list[EarningsEvent]:
    """Get past earnings history from Yahoo Finance."""
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        earnings = ticker.earnings_history

        if earnings is None or earnings.empty:
            return []

        events = []
        for _, row in earnings.tail(quarters).iterrows():
            event = EarningsEvent(
                symbol=symbol.upper(),
                date=str(row.get("Earnings Date", ""))[:10] if "Earnings Date" in row else "",
                eps_estimate=_safe_float(row.get("EPS Estimate")),
                eps_actual=_safe_float(row.get("Reported EPS")),
                surprise_pct=_safe_float(row.get("Surprise(%)")),
                source="yahoo",
            )
            events.append(event)
        return events
    except Exception:
        return []


# ─── Earnings Whispers (Best-Effort) ──────────────────────────────────

def _try_earnings_whispers(symbol: str) -> float | None:
    """
    Best-effort attempt to get the whisper number from Earnings Whispers.

    WARNING: This scrapes a JavaScript-rendered site and may break at any time.
    The site has no API. This is supplementary data only.
    """
    try:
        from bs4 import BeautifulSoup
        url = f"https://www.earningswhispers.com/stocks/{symbol.lower()}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        resp = requests.get(url, headers=headers, timeout=8)
        if resp.status_code != 200:
            return None

        soup = BeautifulSoup(resp.text, "html.parser")

        # Try multiple selectors since the site changes
        for selector in ["#whisper", ".whisper", "[class*=whisper]"]:
            el = soup.select_one(selector)
            if el:
                text = el.get_text(strip=True)
                num = _parse_number(text)
                if num is not None:
                    return num

        return None
    except Exception:
        return None


# ─── Public API ────────────────────────────────────────────────────────

def get_earnings_calendar(days_ahead: int = 7) -> list[EarningsEvent]:
    """
    Get upcoming earnings calendar.
    Uses Finnhub first, falls back to Yahoo.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    end = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

    # Try Finnhub first (most reliable)
    events = _finnhub_earnings_calendar(today, end)
    if events:
        _cache_earnings(events)
        return events

    # Fallback: return cached data
    cached = get_cached_earnings()
    if cached:
        return cached

    return []


def get_earnings_whisper(symbol: str) -> EarningsEvent | None:
    """
    Get earnings data for a specific stock, including whisper number if available.
    Combines: Finnhub estimates + Earnings Whispers whisper number + Yahoo fallback.
    """
    symbol = symbol.upper()

    # Start with Finnhub data
    upcoming = _finnhub_earnings_calendar(
        datetime.now().strftime("%Y-%m-%d"),
        (datetime.now() + timedelta(days=90)).strftime("%Y-%m-%d"),
    )
    event = next((e for e in upcoming if e.symbol == symbol), None)

    # If Finnhub didn't have it, try Yahoo
    if not event:
        event = _yahoo_next_earnings(symbol)

    if not event:
        event = EarningsEvent(symbol=symbol, source="none")

    # Try to get whisper number (best-effort, may fail)
    whisper = _try_earnings_whispers(symbol)
    if whisper is not None:
        event.eps_whisper = whisper

    if event.date or event.eps_estimate or event.eps_whisper:
        _cache_earnings([event])
        return event

    return None


def get_earnings_history(symbol: str, quarters: int = 8) -> list[EarningsEvent]:
    """
    Get past earnings history with actual vs estimate.
    Tries Finnhub first, falls back to Yahoo.
    """
    # Try Finnhub
    events = _finnhub_earnings_surprises(symbol)
    if events:
        return events[:quarters]

    # Fallback to Yahoo
    return _yahoo_earnings_history(symbol, quarters)


def get_watchlist_earnings(watchlist: list[str], days_ahead: int = 30) -> list[EarningsEvent]:
    """
    Check which watchlist stocks have upcoming earnings.
    Returns only stocks with earnings in the next N days.
    """
    today = datetime.now()
    end = today + timedelta(days=days_ahead)
    today_str = today.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")

    # Batch fetch from Finnhub calendar
    all_events = _finnhub_earnings_calendar(today_str, end_str)

    watchlist_set = set(s.upper() for s in watchlist)
    watchlist_events = [e for e in all_events if e.symbol in watchlist_set]

    # For watchlist matches, try to get whisper numbers
    for event in watchlist_events:
        whisper = _try_earnings_whispers(event.symbol)
        if whisper is not None:
            event.eps_whisper = whisper

    # If Finnhub didn't have data, try Yahoo per-symbol
    found_symbols = set(e.symbol for e in watchlist_events)
    for symbol in watchlist:
        if symbol.upper() not in found_symbols:
            event = _yahoo_next_earnings(symbol)
            if event and event.date:
                try:
                    event_date = datetime.strptime(event.date, "%Y-%m-%d")
                    if today <= event_date <= end:
                        watchlist_events.append(event)
                except ValueError:
                    pass

    watchlist_events.sort(key=lambda e: e.date or "9999")
    _cache_earnings(watchlist_events)
    return watchlist_events


def get_cached_earnings(symbol: str | None = None) -> list[EarningsEvent]:
    """Get cached earnings data from database."""
    try:
        conn = get_connection()
        if symbol:
            rows = conn.execute(
                "SELECT data_json FROM earnings_cache WHERE symbol = ? ORDER BY date DESC LIMIT 10",
                (symbol.upper(),),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT data_json FROM earnings_cache ORDER BY date DESC LIMIT 50",
            ).fetchall()
        conn.close()

        events = []
        for r in rows:
            if r["data_json"]:
                data = json.loads(r["data_json"])
                # Remove properties that shouldn't be passed to constructor
                data.pop("has_whisper", None)
                data.pop("beat_whisper", None)
                data.pop("beat_estimate", None)
                events.append(EarningsEvent(**data))
        return events
    except Exception:
        return []


# ─── Helpers ───────────────────────────────────────────────────────────

def _cache_earnings(events: list[EarningsEvent]):
    """Cache earnings events to database."""
    try:
        conn = get_connection()
        for event in events:
            if not event.symbol:
                continue
            conn.execute(
                """INSERT OR REPLACE INTO earnings_cache
                   (symbol, date, data_json, updated_at)
                   VALUES (?, ?, ?, ?)""",
                (event.symbol, event.date, json.dumps(event.to_dict()),
                 datetime.now().isoformat()),
            )
        conn.commit()
        conn.close()
    except Exception:
        pass


def _parse_number(text: str) -> float | None:
    """Extract a number from text like '$1.25' or '1.25'."""
    if not text:
        return None
    match = re.search(r'-?\d+\.?\d*', text.replace(",", ""))
    return float(match.group()) if match else None


def _safe_float(val, default=None):
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default
