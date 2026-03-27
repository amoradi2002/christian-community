"""
Economic Calendar

Tracks high-impact economic events that affect trading decisions:
- FOMC meetings (rate decisions)
- CPI releases (inflation data)
- NFP / Jobs Report (first Friday of each month)
- GDP, PPI, retail sales, and other major releases

Provides caution warnings on high-impact days to prevent
entering positions right before major volatility events.
"""

import os
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from typing import List, Optional
from zoneinfo import ZoneInfo
import calendar


ET = ZoneInfo("America/New_York")


@dataclass
class EconomicEvent:
    date: str                # YYYY-MM-DD
    time: str                # HH:MM ET or "all_day"
    event: str
    importance: str = "medium"   # "high", "medium", "low"
    forecast: str = ""
    previous: str = ""
    impact: str = "neutral"      # "risk_off", "volatile", "neutral"
    trading_note: str = ""       # e.g. "Avoid new positions"

    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "time": self.time,
            "event": self.event,
            "importance": self.importance,
            "forecast": self.forecast,
            "previous": self.previous,
            "impact": self.impact,
            "trading_note": self.trading_note,
        }


# ---------------------------------------------------------------------------
# Known FOMC meeting dates (announcement day, typically Wednesday)
# ---------------------------------------------------------------------------
FOMC_DATES = {
    2025: [
        "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18",
        "2025-07-30", "2025-09-17", "2025-11-05", "2025-12-17",
    ],
    2026: [
        "2026-01-28", "2026-03-18", "2026-05-06", "2026-06-17",
        "2026-07-29", "2026-09-16", "2026-11-04", "2026-12-16",
    ],
}


def _get_second_week_day(year: int, month: int, target_weekday: int) -> date:
    """
    Get the date of the second occurrence of a given weekday in a month.
    target_weekday: 0=Monday ... 6=Sunday
    """
    cal = calendar.monthcalendar(year, month)
    count = 0
    for week in cal:
        if week[target_weekday] != 0:
            count += 1
            if count == 2:
                return date(year, month, week[target_weekday])
    # Fallback: shouldn't happen
    return date(year, month, 10)


def _get_first_friday(year: int, month: int) -> date:
    """Get the first Friday of the given month."""
    cal = calendar.monthcalendar(year, month)
    for week in cal:
        if week[calendar.FRIDAY] != 0:
            return date(year, month, week[calendar.FRIDAY])
    return date(year, month, 7)  # fallback


def _generate_cpi_dates(year: int) -> List[str]:
    """
    Generate CPI release dates for a year.
    CPI is typically released on the second Tuesday or Wednesday of each month.
    Using second Wednesday as the common pattern for recent years.
    """
    dates = []
    for month in range(1, 13):
        # CPI is usually second Wednesday (some months second Tuesday)
        d = _get_second_week_day(year, month, calendar.WEDNESDAY)
        dates.append(d.strftime("%Y-%m-%d"))
    return dates


def _generate_nfp_dates(year: int) -> List[str]:
    """
    Generate Non-Farm Payrolls (Jobs Report) dates for a year.
    NFP is released on the first Friday of each month.
    """
    dates = []
    for month in range(1, 13):
        d = _get_first_friday(year, month)
        dates.append(d.strftime("%Y-%m-%d"))
    return dates


# Pre-compute schedules for known years
CPI_DATES = {
    2025: _generate_cpi_dates(2025),
    2026: _generate_cpi_dates(2026),
}

NFP_DATES = {
    2025: _generate_nfp_dates(2025),
    2026: _generate_nfp_dates(2026),
}


# ---------------------------------------------------------------------------
# Recurring events template — maps event type to metadata
# ---------------------------------------------------------------------------
RECURRING_EVENTS = {
    "FOMC": {
        "time": "14:00",
        "importance": "high",
        "impact": "volatile",
        "trading_note": "Avoid new positions before 2PM ET — FOMC decision incoming",
        "description": "Federal Reserve Interest Rate Decision",
    },
    "CPI": {
        "time": "08:30",
        "importance": "high",
        "impact": "volatile",
        "trading_note": "CPI release at 8:30 AM ET — expect high volatility at open",
        "description": "Consumer Price Index (Inflation Data)",
    },
    "NFP": {
        "time": "08:30",
        "importance": "high",
        "impact": "volatile",
        "trading_note": "Jobs Report at 8:30 AM ET — tighten stops, reduce position size",
        "description": "Non-Farm Payrolls (Jobs Report)",
    },
    "PPI": {
        "time": "08:30",
        "importance": "medium",
        "impact": "volatile",
        "trading_note": "PPI release at 8:30 AM — may move markets on inflation read",
        "description": "Producer Price Index",
    },
    "GDP": {
        "time": "08:30",
        "importance": "medium",
        "impact": "volatile",
        "trading_note": "GDP data at 8:30 AM — watch for surprises",
        "description": "Gross Domestic Product",
    },
    "RETAIL_SALES": {
        "time": "08:30",
        "importance": "medium",
        "impact": "neutral",
        "trading_note": "Retail Sales at 8:30 AM — consumer spending indicator",
        "description": "Retail Sales Report",
    },
    "JOBLESS_CLAIMS": {
        "time": "08:30",
        "importance": "low",
        "impact": "neutral",
        "trading_note": "Weekly jobless claims — usually low impact unless a surprise",
        "description": "Initial Jobless Claims (Weekly)",
    },
}


def _build_event(event_date: str, event_type: str) -> EconomicEvent:
    """Build an EconomicEvent from a date and event type key."""
    meta = RECURRING_EVENTS[event_type]
    return EconomicEvent(
        date=event_date,
        time=meta["time"],
        event=meta["description"],
        importance=meta["importance"],
        impact=meta["impact"],
        trading_note=meta["trading_note"],
    )


def get_upcoming_events(days_ahead: int = 7) -> List[EconomicEvent]:
    """
    Get economic events in the next N days.

    Combines the hardcoded FOMC/CPI/NFP schedule with any API data
    if available (tries finnhub economic calendar).

    Args:
        days_ahead: Number of days to look ahead (default 7).

    Returns:
        List of EconomicEvent objects sorted by date.
    """
    today = datetime.now(ET).date()
    end_date = today + timedelta(days=days_ahead)
    events: List[EconomicEvent] = []

    year = today.year

    # Check FOMC dates
    for yr in [year, year + 1]:
        for date_str in FOMC_DATES.get(yr, []):
            d = date.fromisoformat(date_str)
            if today <= d <= end_date:
                events.append(_build_event(date_str, "FOMC"))

    # Check CPI dates
    for yr in [year, year + 1]:
        for date_str in CPI_DATES.get(yr, []):
            d = date.fromisoformat(date_str)
            if today <= d <= end_date:
                events.append(_build_event(date_str, "CPI"))

    # Check NFP dates
    for yr in [year, year + 1]:
        for date_str in NFP_DATES.get(yr, []):
            d = date.fromisoformat(date_str)
            if today <= d <= end_date:
                events.append(_build_event(date_str, "NFP"))

    # Try to supplement with finnhub if API key is available
    finnhub_key = os.getenv("FINNHUB_API_KEY")
    if finnhub_key:
        api_events = _fetch_finnhub_calendar(
            finnhub_key,
            today.strftime("%Y-%m-%d"),
            end_date.strftime("%Y-%m-%d"),
        )
        # Merge without duplicating known events
        known_dates_events = {(e.date, e.event) for e in events}
        for evt in api_events:
            if (evt.date, evt.event) not in known_dates_events:
                events.append(evt)

    events.sort(key=lambda e: (e.date, e.time))
    return events


def _fetch_finnhub_calendar(api_key: str, from_date: str, to_date: str) -> List[EconomicEvent]:
    """Fetch economic calendar from finnhub API."""
    events = []
    try:
        import requests
        url = "https://finnhub.io/api/v1/calendar/economic"
        params = {
            "from": from_date,
            "to": to_date,
            "token": api_key,
        }
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            for item in data.get("economicCalendar", []):
                importance = _map_finnhub_impact(item.get("impact", 0))
                events.append(EconomicEvent(
                    date=item.get("date", from_date),
                    time=item.get("time", ""),
                    event=item.get("event", "Unknown Event"),
                    importance=importance,
                    forecast=str(item.get("estimate", "")),
                    previous=str(item.get("prev", "")),
                    impact="volatile" if importance == "high" else "neutral",
                    trading_note=_auto_trading_note(item.get("event", ""), importance),
                ))
    except Exception:
        pass
    return events


def _map_finnhub_impact(impact_value) -> str:
    """Map finnhub's numeric impact to our importance levels."""
    try:
        val = int(impact_value)
    except (TypeError, ValueError):
        return "low"
    if val >= 3:
        return "high"
    elif val == 2:
        return "medium"
    return "low"


def _auto_trading_note(event_name: str, importance: str) -> str:
    """Generate a trading note based on event name and importance."""
    event_lower = event_name.lower()

    if "fomc" in event_lower or "interest rate" in event_lower or "fed" in event_lower:
        return "Fed event — avoid new positions before announcement"
    elif "cpi" in event_lower or "consumer price" in event_lower:
        return "Inflation data — expect volatility at open"
    elif "nonfarm" in event_lower or "payroll" in event_lower or "employment" in event_lower:
        return "Jobs data — tighten stops, reduce size"
    elif "gdp" in event_lower:
        return "GDP release — watch for surprises"
    elif importance == "high":
        return "High-impact event — consider reducing exposure"
    elif importance == "medium":
        return "Medium-impact event — monitor for surprises"
    return ""


def is_high_impact_day() -> bool:
    """
    Check if today has any high-impact economic events.

    High-impact events include FOMC decisions, CPI releases,
    and NFP jobs reports.

    Returns:
        True if today has at least one high-impact event.
    """
    today_str = datetime.now(ET).date().strftime("%Y-%m-%d")
    events = get_upcoming_events(days_ahead=0)

    # Also check today directly against known schedules
    year = datetime.now(ET).year
    if today_str in FOMC_DATES.get(year, []):
        return True
    if today_str in CPI_DATES.get(year, []):
        return True
    if today_str in NFP_DATES.get(year, []):
        return True

    # Check API events
    for evt in events:
        if evt.date == today_str and evt.importance == "high":
            return True

    return False


def get_trading_caution() -> Optional[str]:
    """
    If today is a high-impact day, return a caution message.

    Returns:
        A warning string if there's a high-impact event today, None otherwise.

    Examples:
        "FOMC Decision today at 2:00 PM ET - avoid new positions before announcement"
        "CPI Release today at 8:30 AM ET - expect high volatility at open"
    """
    today = datetime.now(ET).date()
    today_str = today.strftime("%Y-%m-%d")
    year = today.year

    cautions = []

    if today_str in FOMC_DATES.get(year, []):
        cautions.append(
            "FOMC Decision today at 2:00 PM ET — "
            "avoid new positions before announcement, expect sharp moves"
        )

    if today_str in CPI_DATES.get(year, []):
        cautions.append(
            "CPI Release today at 8:30 AM ET — "
            "expect high volatility at open, tighten stops"
        )

    if today_str in NFP_DATES.get(year, []):
        cautions.append(
            "Jobs Report (NFP) today at 8:30 AM ET — "
            "reduce position sizes, expect gap moves"
        )

    # Check for any additional high-impact events from API
    events = get_upcoming_events(days_ahead=0)
    known_types = {"FOMC", "CPI", "NFP"}
    for evt in events:
        if evt.date == today_str and evt.importance == "high":
            # Avoid duplicating FOMC/CPI/NFP we already added
            is_known = any(k.lower() in evt.event.lower() for k in known_types)
            if not is_known:
                cautions.append(
                    f"{evt.event} today at {evt.time} ET — {evt.trading_note}"
                )

    if not cautions:
        return None

    if len(cautions) == 1:
        return cautions[0]

    # Multiple events — combine into a clear warning
    header = "MULTIPLE HIGH-IMPACT EVENTS TODAY — exercise extreme caution:\n"
    body = "\n".join(f"  - {c}" for c in cautions)
    return header + body


def get_fomc_dates(year: int = 2026) -> list:
    """
    Return FOMC meeting dates for the specified year.

    Args:
        year: Calendar year (2025 and 2026 are hardcoded).

    Returns:
        List of date strings in YYYY-MM-DD format.
    """
    return FOMC_DATES.get(year, [])


def get_economic_summary(days_ahead: int = 7) -> str:
    """
    Get a formatted summary of upcoming economic events.

    Args:
        days_ahead: Number of days to look ahead.

    Returns:
        Formatted multi-line string with event calendar.
    """
    events = get_upcoming_events(days_ahead=days_ahead)
    now = datetime.now(ET)

    lines = [
        "=" * 60,
        f"  ECONOMIC CALENDAR — Next {days_ahead} Days",
        f"  Generated: {now.strftime('%A %B %d, %Y %I:%M %p ET')}",
        "=" * 60,
        "",
    ]

    if not events:
        lines.append("  No significant economic events in this period.")
        lines.append("")
        lines.append("=" * 60)
        return "\n".join(lines)

    current_date = ""
    for evt in events:
        if evt.date != current_date:
            current_date = evt.date
            d = date.fromisoformat(evt.date)
            day_name = d.strftime("%A %B %d")
            lines.append(f"  {day_name}")
            lines.append("  " + "-" * 40)

        importance_tag = {
            "high": "[!!!]",
            "medium": "[ ! ]",
            "low": "[ . ]",
        }.get(evt.importance, "[   ]")

        lines.append(f"    {importance_tag} {evt.time} ET — {evt.event}")
        if evt.forecast or evt.previous:
            detail = ""
            if evt.forecast:
                detail += f"Forecast: {evt.forecast}"
            if evt.previous:
                detail += f"  Previous: {evt.previous}"
            lines.append(f"           {detail.strip()}")
        if evt.trading_note:
            lines.append(f"           Note: {evt.trading_note}")
        lines.append("")

    lines.append("=" * 60)

    # Add caution if today is high impact
    caution = get_trading_caution()
    if caution:
        lines.append("")
        lines.append("  *** TODAY'S CAUTION ***")
        lines.append(f"  {caution}")
        lines.append("")

    return "\n".join(lines)
