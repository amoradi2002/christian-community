"""
Market hours utilities — prevents the bot from scanning when markets are closed.
Handles regular hours, pre-market, after-hours, weekends, and US market holidays.
"""

from datetime import datetime, date, time
import logging

logger = logging.getLogger(__name__)

# US market holidays for 2025-2026 (NYSE/NASDAQ)
US_MARKET_HOLIDAYS = {
    # 2025
    date(2025, 1, 1),    # New Year's Day
    date(2025, 1, 20),   # MLK Day
    date(2025, 2, 17),   # Presidents' Day
    date(2025, 4, 18),   # Good Friday
    date(2025, 5, 26),   # Memorial Day
    date(2025, 6, 19),   # Juneteenth
    date(2025, 7, 4),    # Independence Day
    date(2025, 9, 1),    # Labor Day
    date(2025, 11, 27),  # Thanksgiving
    date(2025, 12, 25),  # Christmas
    # 2026
    date(2026, 1, 1),    # New Year's Day
    date(2026, 1, 19),   # MLK Day
    date(2026, 2, 16),   # Presidents' Day
    date(2026, 4, 3),    # Good Friday
    date(2026, 5, 25),   # Memorial Day
    date(2026, 6, 19),   # Juneteenth
    date(2026, 7, 3),    # Independence Day (observed)
    date(2026, 9, 7),    # Labor Day
    date(2026, 11, 26),  # Thanksgiving
    date(2026, 12, 25),  # Christmas
}

# Early close days (1 PM ET) — day before Independence Day, day after Thanksgiving, Christmas Eve
US_EARLY_CLOSE = {
    date(2025, 7, 3),    # Day before July 4th
    date(2025, 11, 28),  # Day after Thanksgiving
    date(2025, 12, 24),  # Christmas Eve
    date(2026, 7, 2),    # Day before July 4th (observed)
    date(2026, 11, 27),  # Day after Thanksgiving
    date(2026, 12, 24),  # Christmas Eve
}


def _now_et() -> datetime:
    """Get current time in US Eastern."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/New_York"))
    except ImportError:
        import os
        os.environ.setdefault("TZ", "America/New_York")
        return datetime.now()


def is_market_holiday(d: date = None) -> bool:
    if d is None:
        d = _now_et().date()
    return d in US_MARKET_HOLIDAYS


def is_weekend(d: date = None) -> bool:
    if d is None:
        d = _now_et().date()
    return d.weekday() >= 5


def is_early_close(d: date = None) -> bool:
    if d is None:
        d = _now_et().date()
    return d in US_EARLY_CLOSE


def is_premarket() -> bool:
    """4:00 AM - 9:29 AM ET, weekdays, not holidays."""
    now = _now_et()
    if is_weekend(now.date()) or is_market_holiday(now.date()):
        return False
    t = now.time()
    return time(4, 0) <= t < time(9, 30)


def is_market_open() -> bool:
    """9:30 AM - 4:00 PM ET (or 1:00 PM on early close days), weekdays, not holidays."""
    now = _now_et()
    if is_weekend(now.date()) or is_market_holiday(now.date()):
        return False
    t = now.time()
    open_time = time(9, 30)
    if is_early_close(now.date()):
        close_time = time(13, 0)
    else:
        close_time = time(16, 0)
    return open_time <= t < close_time


def is_after_hours() -> bool:
    """4:00 PM - 8:00 PM ET, weekdays, not holidays."""
    now = _now_et()
    if is_weekend(now.date()) or is_market_holiday(now.date()):
        return False
    t = now.time()
    close = time(13, 0) if is_early_close(now.date()) else time(16, 0)
    return close <= t < time(20, 0)


def is_trading_hours() -> bool:
    """Any trading session: premarket, market, or after-hours."""
    return is_premarket() or is_market_open() or is_after_hours()


def market_status() -> str:
    """Human-readable market status."""
    now = _now_et()
    if is_weekend(now.date()):
        return "CLOSED (weekend)"
    if is_market_holiday(now.date()):
        return "CLOSED (holiday)"
    if is_premarket():
        return "PRE-MARKET (4:00-9:30 AM ET)"
    if is_market_open():
        close = "1:00 PM" if is_early_close() else "4:00 PM"
        return f"OPEN (until {close} ET)"
    if is_after_hours():
        return "AFTER-HOURS (4:00-8:00 PM ET)"
    return "CLOSED"


def next_market_open() -> str:
    """When the market opens next."""
    from datetime import timedelta
    now = _now_et()
    d = now.date()
    if now.time() >= time(16, 0) or is_weekend(d) or is_market_holiday(d):
        d += timedelta(days=1)
    while is_weekend(d) or is_market_holiday(d):
        d += timedelta(days=1)
    return f"{d.strftime('%A %B %d')} at 9:30 AM ET"
