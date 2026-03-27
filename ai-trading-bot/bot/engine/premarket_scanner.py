"""
Pre-Market Scanner

Runs before market open (4:00 AM - 9:30 AM ET) to identify:
- Gap up/down stocks (>3%)
- High premarket volume vs average (>2x)
- Earnings movers and catalyst-driven names

Feeds into the day scanner for 5-pillar checks once market opens.
"""

import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional
from zoneinfo import ZoneInfo

import yfinance as yf

from bot.engine.day_scanner import grade_catalyst, check_five_pillars


ET = ZoneInfo("America/New_York")

# Default watchlist of liquid, commonly gapping tickers
DEFAULT_WATCHLIST = [
    # Popular day-trade names
    "AAPL", "TSLA", "NVDA", "AMD", "META", "AMZN", "MSFT", "GOOGL", "NFLX",
    "BABA", "NIO", "PLTR", "SOFI", "RIVN", "LCID", "COIN", "MARA", "RIOT",
    "SQ", "SNAP", "ROKU", "SHOP", "UBER", "ABNB", "HOOD", "DKNG", "RBLX",
    "BA", "DIS", "JPM", "GS", "XOM", "CVX", "PFE", "MRNA",
]

# Minimum thresholds
MIN_GAP_PCT = 3.0
MIN_VOLUME_RATIO = 2.0


@dataclass
class PremarketMover:
    symbol: str
    gap_pct: float = 0.0           # gap up/down percentage
    premarket_volume: int = 0
    avg_volume: int = 0
    volume_ratio: float = 0.0      # premarket vol vs avg
    catalyst: str = ""             # earnings, news, etc.
    price: float = 0.0
    prev_close: float = 0.0
    direction: str = ""            # "gap_up" or "gap_down"
    meets_5_pillars: bool = False  # quick check
    notes: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "gap_pct": self.gap_pct,
            "premarket_volume": self.premarket_volume,
            "avg_volume": self.avg_volume,
            "volume_ratio": self.volume_ratio,
            "catalyst": self.catalyst,
            "price": self.price,
            "prev_close": self.prev_close,
            "direction": self.direction,
            "meets_5_pillars": self.meets_5_pillars,
            "notes": self.notes,
        }


def scan_premarket(watchlist: list = None) -> List[PremarketMover]:
    """
    Scan for premarket movers using yfinance.

    Checks each symbol for:
    - Gap percentage vs previous close (must be > 3%)
    - Premarket volume vs 50-day average volume (must be > 2x)
    - Catalyst presence (earnings, news keywords)

    Args:
        watchlist: List of ticker symbols to scan. Defaults to DEFAULT_WATCHLIST.

    Returns:
        List of PremarketMover objects sorted by absolute gap percentage descending.
    """
    symbols = watchlist or DEFAULT_WATCHLIST
    movers: List[PremarketMover] = []

    for symbol in symbols:
        try:
            mover = _analyze_symbol(symbol)
            if mover is not None:
                movers.append(mover)
        except Exception as e:
            # Don't let one bad ticker kill the whole scan
            continue

    # Sort by absolute gap size
    movers.sort(key=lambda m: abs(m.gap_pct), reverse=True)
    return movers


def _analyze_symbol(symbol: str) -> Optional[PremarketMover]:
    """Analyze a single symbol for premarket activity. Returns None if it doesn't qualify."""
    ticker = yf.Ticker(symbol)

    try:
        info = ticker.fast_info
        current_price = info.last_price
        prev_close = info.previous_close
    except Exception:
        return None

    if not current_price or not prev_close or prev_close == 0:
        return None

    # Calculate gap
    gap_pct = ((current_price - prev_close) / prev_close) * 100.0

    if abs(gap_pct) < MIN_GAP_PCT:
        return None

    direction = "gap_up" if gap_pct > 0 else "gap_down"

    # Volume analysis
    try:
        avg_volume = int(getattr(info, "three_month_average_volume", 0) or 0)
    except Exception:
        avg_volume = 0

    # Get current session volume (premarket will show limited volume)
    try:
        current_volume = int(getattr(info, "last_volume", 0) or 0)
    except Exception:
        current_volume = 0

    # If avg_volume not available from fast_info, fetch from history
    if avg_volume == 0:
        try:
            hist = ticker.history(period="3mo", interval="1d")
            if not hist.empty and "Volume" in hist.columns:
                avg_volume = int(hist["Volume"].mean())
        except Exception:
            avg_volume = 1  # avoid division by zero

    volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0.0

    # Build notes
    notes = []
    catalyst = ""

    # Check for earnings
    try:
        cal = ticker.calendar
        if cal is not None:
            # yfinance calendar can be a dict or DataFrame
            if isinstance(cal, dict):
                earnings_date = cal.get("Earnings Date")
                if earnings_date:
                    today = datetime.now(ET).date()
                    if isinstance(earnings_date, list) and len(earnings_date) > 0:
                        for ed in earnings_date:
                            ed_date = ed.date() if hasattr(ed, "date") else ed
                            if ed_date == today:
                                catalyst = "Earnings today"
                                notes.append("Reporting earnings today")
                                break
                            elif ed_date == today - timedelta(days=1):
                                catalyst = "Earnings beat" if gap_pct > 0 else "Earnings miss"
                                notes.append("Reported earnings yesterday")
                                break
                    elif hasattr(earnings_date, "date"):
                        ed_date = earnings_date.date()
                        if ed_date == today:
                            catalyst = "Earnings today"
                            notes.append("Reporting earnings today")
                        elif ed_date == today - timedelta(days=1):
                            catalyst = "Earnings beat" if gap_pct > 0 else "Earnings miss"
                            notes.append("Reported earnings yesterday")
    except Exception:
        pass

    # Add gap context
    if abs(gap_pct) >= 10:
        notes.append(f"Major gap {'up' if gap_pct > 0 else 'down'} — look for catalyst confirmation")
    if volume_ratio >= 5:
        notes.append("Extreme volume — high institutional interest likely")
    elif volume_ratio >= MIN_VOLUME_RATIO:
        notes.append("Elevated volume — above-average interest")

    if not catalyst:
        if abs(gap_pct) >= 5:
            catalyst = "Gap (unknown catalyst — research needed)"
        else:
            catalyst = "Moderate gap — check news"

    # Quick 5-pillar check for small-cap candidates
    meets_5_pillars = False
    try:
        market_cap = getattr(info, "market_cap", 0) or 0
        float_shares = getattr(info, "shares", 0) or 0
        float_shares_m = float_shares / 1_000_000 if float_shares else 0

        if market_cap and market_cap < 1_000_000_000:
            candidate = check_five_pillars(
                symbol=symbol,
                price=current_price,
                day_change_pct=abs(gap_pct),
                relative_volume=volume_ratio,
                catalyst=catalyst,
                float_shares_m=float_shares_m,
            )
            meets_5_pillars = candidate.passed
            if candidate.pillars_met >= 4:
                notes.append(f"5-pillar check: {candidate.pillars_met}/5 met")
    except Exception:
        pass

    # Apply volume filter (only if we have meaningful volume data)
    if avg_volume > 0 and volume_ratio < MIN_VOLUME_RATIO and current_volume > 0:
        return None

    return PremarketMover(
        symbol=symbol,
        gap_pct=round(gap_pct, 2),
        premarket_volume=current_volume,
        avg_volume=avg_volume,
        volume_ratio=round(volume_ratio, 2),
        catalyst=catalyst,
        price=round(current_price, 2),
        prev_close=round(prev_close, 2),
        direction=direction,
        meets_5_pillars=meets_5_pillars,
        notes=notes,
    )


def get_earnings_today() -> list:
    """
    Get stocks reporting earnings today.

    Tries finnhub API first if FINNHUB_API_KEY is set in environment,
    then falls back to checking yfinance calendars for the default watchlist.

    Returns:
        List of dicts with symbol and earnings info.
    """
    today = datetime.now(ET).date()
    today_str = today.strftime("%Y-%m-%d")
    earnings = []

    # Try finnhub first
    finnhub_key = os.getenv("FINNHUB_API_KEY")
    if finnhub_key:
        try:
            import requests
            url = "https://finnhub.io/api/v1/calendar/earnings"
            params = {
                "from": today_str,
                "to": today_str,
                "token": finnhub_key,
            }
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("earningsCalendar", []):
                    earnings.append({
                        "symbol": item.get("symbol", ""),
                        "date": item.get("date", today_str),
                        "hour": item.get("hour", "unknown"),  # bmo, amc, dmh
                        "eps_estimate": item.get("epsEstimate"),
                        "eps_actual": item.get("epsActual"),
                        "revenue_estimate": item.get("revenueEstimate"),
                        "revenue_actual": item.get("revenueActual"),
                        "source": "finnhub",
                    })
                if earnings:
                    return earnings
        except Exception:
            pass  # Fall through to yfinance approach

    # Fallback: check yfinance calendars for common tickers
    # This is slower but doesn't require an API key
    scan_list = DEFAULT_WATCHLIST
    for symbol in scan_list:
        try:
            ticker = yf.Ticker(symbol)
            cal = ticker.calendar
            if cal is None:
                continue

            if isinstance(cal, dict):
                ed = cal.get("Earnings Date")
                if ed is None:
                    continue
                dates = ed if isinstance(ed, list) else [ed]
                for d in dates:
                    d_date = d.date() if hasattr(d, "date") else d
                    if d_date == today:
                        earnings.append({
                            "symbol": symbol,
                            "date": today_str,
                            "hour": "unknown",
                            "eps_estimate": cal.get("Earnings Average"),
                            "eps_actual": None,
                            "revenue_estimate": cal.get("Revenue Average"),
                            "revenue_actual": None,
                            "source": "yfinance",
                        })
                        break
        except Exception:
            continue

    return earnings


def get_premarket_report(movers: list) -> str:
    """
    Format premarket movers into a readable report string.

    Args:
        movers: List of PremarketMover objects.

    Returns:
        Formatted multi-line report string.
    """
    if not movers:
        return "Pre-Market Scan: No significant movers found.\n"

    now = datetime.now(ET)
    lines = [
        "=" * 60,
        f"  PRE-MARKET SCAN REPORT — {now.strftime('%A %B %d, %Y %I:%M %p ET')}",
        "=" * 60,
        "",
    ]

    gap_ups = [m for m in movers if m.direction == "gap_up"]
    gap_downs = [m for m in movers if m.direction == "gap_down"]

    if gap_ups:
        lines.append(f"  GAP UP ({len(gap_ups)} stocks)")
        lines.append("-" * 40)
        for m in gap_ups:
            pillar_tag = " [5-PILLAR]" if m.meets_5_pillars else ""
            lines.append(
                f"  {m.symbol:<6} +{m.gap_pct:>6.2f}%  ${m.price:>8.2f}  "
                f"Vol: {_fmt_volume(m.premarket_volume)} ({m.volume_ratio:.1f}x avg){pillar_tag}"
            )
            lines.append(f"         Catalyst: {m.catalyst}")
            for note in m.notes:
                lines.append(f"         > {note}")
            lines.append("")

    if gap_downs:
        lines.append(f"  GAP DOWN ({len(gap_downs)} stocks)")
        lines.append("-" * 40)
        for m in gap_downs:
            lines.append(
                f"  {m.symbol:<6} {m.gap_pct:>7.2f}%  ${m.price:>8.2f}  "
                f"Vol: {_fmt_volume(m.premarket_volume)} ({m.volume_ratio:.1f}x avg)"
            )
            lines.append(f"         Catalyst: {m.catalyst}")
            for note in m.notes:
                lines.append(f"         > {note}")
            lines.append("")

    lines.append("=" * 60)
    lines.append(f"  Total movers: {len(movers)} | Gap ups: {len(gap_ups)} | Gap downs: {len(gap_downs)}")
    lines.append("=" * 60)

    return "\n".join(lines)


def should_run_premarket() -> bool:
    """
    Check if current time is in the premarket window.

    Pre-market window: 4:00 AM - 9:30 AM Eastern Time, weekdays only.

    Returns:
        True if current time is within the premarket window.
    """
    now = datetime.now(ET)

    # Weekday check (0=Monday, 6=Sunday)
    if now.weekday() >= 5:
        return False

    hour = now.hour
    minute = now.minute

    # 4:00 AM to 9:29 AM ET
    if hour < 4:
        return False
    if hour > 9:
        return False
    if hour == 9 and minute >= 30:
        return False

    return True


def _fmt_volume(vol: int) -> str:
    """Format volume with K/M suffix for readability."""
    if vol >= 1_000_000:
        return f"{vol / 1_000_000:.1f}M"
    elif vol >= 1_000:
        return f"{vol / 1_000:.0f}K"
    else:
        return str(vol)
