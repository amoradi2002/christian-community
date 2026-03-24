"""
Earnings data provider - calendar, whisper numbers, and earnings surprises.

Sources:
- Earnings Whispers (earningswhispers.com) - whisper numbers and calendar
- Yahoo Finance - as fallback for earnings dates and estimates
- Finviz - earnings date from fundamentals

Earnings Whispers doesn't have an official API, so we scrape their
public calendar and whisper data.
"""

import re
import json
from datetime import datetime, timedelta
from dataclasses import dataclass, field

import requests
from bs4 import BeautifulSoup

from bot.db.database import get_connection


@dataclass
class EarningsEvent:
    """Represents an upcoming or past earnings event."""
    symbol: str
    company: str = ""
    date: str = ""            # YYYY-MM-DD
    time: str = ""            # "BMO" (before market open), "AMC" (after market close)
    eps_estimate: float | None = None
    eps_whisper: float | None = None   # The whisper number (crowd estimate)
    eps_actual: float | None = None
    revenue_estimate: float | None = None
    revenue_actual: float | None = None
    surprise_pct: float | None = None
    confirmed: bool = False

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
            "has_whisper": self.has_whisper,
            "beat_whisper": self.beat_whisper,
            "beat_estimate": self.beat_estimate,
        }


_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def get_earnings_calendar(days_ahead: int = 7) -> list[EarningsEvent]:
    """
    Get upcoming earnings calendar.
    Tries Earnings Whispers first, falls back to Yahoo Finance.
    """
    events = _fetch_earnings_whispers_calendar(days_ahead)
    if not events:
        events = _fetch_yahoo_earnings_calendar(days_ahead)

    # Cache results
    _cache_earnings(events)
    return events


def get_earnings_whisper(symbol: str) -> EarningsEvent | None:
    """
    Get the whisper number for a specific stock's upcoming earnings.
    The whisper number is the unofficial crowd estimate that often
    differs from Wall Street consensus.
    """
    try:
        url = f"https://www.earningswhispers.com/stocks/{symbol.lower()}"
        resp = requests.get(url, headers=_HEADERS, timeout=10)
        if resp.status_code != 200:
            return None

        soup = BeautifulSoup(resp.text, "html.parser")

        event = EarningsEvent(symbol=symbol.upper())

        # Extract company name
        title = soup.find("title")
        if title:
            event.company = title.text.split("|")[0].strip().replace(" Earnings Whispers", "")

        # Extract whisper number
        whisper_el = soup.find("div", class_="whisper")
        if not whisper_el:
            whisper_el = soup.find(id="whisper")
        if whisper_el:
            whisper_text = whisper_el.get_text(strip=True)
            event.eps_whisper = _parse_number(whisper_text)

        # Extract consensus estimate
        estimate_el = soup.find("div", class_="estimate")
        if not estimate_el:
            estimate_el = soup.find(id="estimate")
        if estimate_el:
            estimate_text = estimate_el.get_text(strip=True)
            event.eps_estimate = _parse_number(estimate_text)

        # Extract earnings date
        date_el = soup.find("div", class_="date")
        if not date_el:
            date_el = soup.find(id="date")
        if date_el:
            date_text = date_el.get_text(strip=True)
            event.date = _parse_date(date_text)

        # Try to find BMO/AMC
        page_text = soup.get_text().lower()
        if "before market" in page_text or "bmo" in page_text:
            event.time = "BMO"
        elif "after market" in page_text or "amc" in page_text:
            event.time = "AMC"

        # Look for confirmed status
        if "confirmed" in page_text:
            event.confirmed = True

        if event.eps_whisper or event.eps_estimate or event.date:
            _cache_earnings([event])
            return event
        return None

    except Exception as e:
        print(f"Earnings Whispers fetch error for {symbol}: {e}")
        return None


def get_earnings_history(symbol: str, quarters: int = 8) -> list[EarningsEvent]:
    """
    Get past earnings history with actual vs estimate.
    Uses Yahoo Finance earnings data.
    """
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)

        # Get earnings history
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
            )
            events.append(event)

        return events
    except Exception as e:
        print(f"Earnings history error for {symbol}: {e}")
        return []


def get_watchlist_earnings(watchlist: list[str], days_ahead: int = 30) -> list[EarningsEvent]:
    """
    Check which watchlist stocks have upcoming earnings.
    Returns only stocks with earnings in the next N days.
    """
    events = []
    today = datetime.now()
    cutoff = today + timedelta(days=days_ahead)

    for symbol in watchlist:
        try:
            # Try Earnings Whispers first for the whisper number
            event = get_earnings_whisper(symbol)
            if event and event.date:
                try:
                    event_date = datetime.strptime(event.date, "%Y-%m-%d")
                    if today <= event_date <= cutoff:
                        events.append(event)
                except ValueError:
                    events.append(event)
            else:
                # Fallback: check Yahoo for earnings date
                event = _get_yahoo_next_earnings(symbol)
                if event and event.date:
                    try:
                        event_date = datetime.strptime(event.date, "%Y-%m-%d")
                        if today <= event_date <= cutoff:
                            events.append(event)
                    except ValueError:
                        pass
        except Exception:
            continue

    events.sort(key=lambda e: e.date)
    return events


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

        return [
            EarningsEvent(**json.loads(r["data_json"]))
            for r in rows
            if r["data_json"]
        ]
    except Exception:
        return []


# --- Private helpers ---

def _fetch_earnings_whispers_calendar(days_ahead: int) -> list[EarningsEvent]:
    """Scrape the Earnings Whispers calendar page."""
    try:
        url = "https://www.earningswhispers.com/calendar"
        resp = requests.get(url, headers=_HEADERS, timeout=10)
        if resp.status_code != 200:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        events = []

        # Look for earnings calendar entries
        rows = soup.find_all("div", class_="cal-row")
        if not rows:
            rows = soup.find_all("li", class_="cal-item")
        if not rows:
            # Try table format
            tables = soup.find_all("table")
            for table in tables:
                for tr in table.find_all("tr")[1:]:  # Skip header
                    cells = tr.find_all("td")
                    if len(cells) >= 3:
                        event = EarningsEvent(
                            symbol=cells[0].get_text(strip=True).upper(),
                            company=cells[1].get_text(strip=True) if len(cells) > 1 else "",
                            date=_parse_date(cells[2].get_text(strip=True)) if len(cells) > 2 else "",
                        )
                        if event.symbol and len(event.symbol) <= 5:
                            events.append(event)

        for row in rows:
            try:
                ticker_el = row.find(class_="ticker") or row.find("a")
                if not ticker_el:
                    continue

                symbol = ticker_el.get_text(strip=True).upper()
                if not symbol or len(symbol) > 5:
                    continue

                event = EarningsEvent(symbol=symbol)

                company_el = row.find(class_="company")
                if company_el:
                    event.company = company_el.get_text(strip=True)

                date_el = row.find(class_="date")
                if date_el:
                    event.date = _parse_date(date_el.get_text(strip=True))

                whisper_el = row.find(class_="whisper")
                if whisper_el:
                    event.eps_whisper = _parse_number(whisper_el.get_text(strip=True))

                estimate_el = row.find(class_="estimate")
                if estimate_el:
                    event.eps_estimate = _parse_number(estimate_el.get_text(strip=True))

                events.append(event)
            except Exception:
                continue

        return events

    except Exception as e:
        print(f"Earnings Whispers calendar error: {e}")
        return []


def _fetch_yahoo_earnings_calendar(days_ahead: int) -> list[EarningsEvent]:
    """Fetch earnings calendar from Yahoo Finance as fallback."""
    try:
        import yfinance as yf
        from datetime import date

        start = date.today()
        end = start + timedelta(days=days_ahead)

        # Yahoo doesn't have a direct calendar API, use their earnings module
        url = f"https://finance.yahoo.com/calendar/earnings?from={start}&to={end}"
        resp = requests.get(url, headers=_HEADERS, timeout=10)
        if resp.status_code != 200:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        events = []

        table = soup.find("table")
        if not table:
            return []

        for tr in table.find_all("tr")[1:]:
            cells = tr.find_all("td")
            if len(cells) >= 5:
                event = EarningsEvent(
                    symbol=cells[0].get_text(strip=True),
                    company=cells[1].get_text(strip=True),
                    date=_parse_date(cells[2].get_text(strip=True)),
                    time=cells[3].get_text(strip=True) if len(cells) > 3 else "",
                    eps_estimate=_parse_number(cells[4].get_text(strip=True)) if len(cells) > 4 else None,
                )
                events.append(event)

        return events
    except Exception as e:
        print(f"Yahoo earnings calendar error: {e}")
        return []


def _get_yahoo_next_earnings(symbol: str) -> EarningsEvent | None:
    """Get next earnings date from Yahoo Finance for a specific stock."""
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        cal = ticker.calendar

        if cal is None or cal.empty:
            return None

        # Calendar has Earnings Date
        if "Earnings Date" in cal.index:
            dates = cal.loc["Earnings Date"]
            if len(dates) > 0:
                date_val = dates.iloc[0]
                event = EarningsEvent(
                    symbol=symbol.upper(),
                    date=str(date_val)[:10],
                )

                if "EPS Estimate" in cal.index:
                    event.eps_estimate = _safe_float(cal.loc["EPS Estimate"].iloc[0])

                if "Revenue Estimate" in cal.index:
                    event.revenue_estimate = _safe_float(cal.loc["Revenue Estimate"].iloc[0])

                return event
        return None
    except Exception:
        return None


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


def _parse_date(text: str) -> str:
    """Try to parse various date formats to YYYY-MM-DD."""
    if not text:
        return ""
    # Already in YYYY-MM-DD format
    if re.match(r'\d{4}-\d{2}-\d{2}', text):
        return text[:10]
    # Try common formats
    for fmt in ["%b %d, %Y", "%B %d, %Y", "%m/%d/%Y", "%m/%d/%y", "%d-%b-%Y"]:
        try:
            return datetime.strptime(text.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return text


def _safe_float(val, default=None):
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default
