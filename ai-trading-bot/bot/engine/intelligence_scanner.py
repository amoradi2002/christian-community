"""
Intelligence Scanner - Scans Unusual Whales, Finviz, and Earnings Whispers
for actionable alerts and sends them through the alert system.

Runs alongside the regular strategy scanner to provide additional intelligence:
- Whale flow alerts (big money options bets)
- Earnings warnings (watchlist stocks reporting soon, with urgency levels)
- Insider buying activity
- Unusual volume + oversold screener picks
- Options opportunities (decoupled from analyzer)
- Sector movers (unusual sector-level moves)
- Dark pool activity
"""

import hashlib
import logging
import os
import time

import requests
from datetime import datetime, timedelta

from bot.config.settings import CONFIG
from bot.engine.signal import Signal

logger = logging.getLogger("bot.engine.intelligence_scanner")

# --------------------------------------------------------------------------- #
# Alert deduplication
# --------------------------------------------------------------------------- #
_seen_alerts: set[str] = set()
_SEEN_ALERTS_MAX = 5000


def _alert_key(alert_type: str, ticker: str, date_str: str) -> str:
    """Generate a dedup key from type + ticker + date."""
    raw = f"{alert_type}|{ticker}|{date_str}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _is_duplicate(alert_type: str, ticker: str, date_str: str = "") -> bool:
    """Return True if this alert has already been emitted today."""
    if not date_str:
        date_str = datetime.utcnow().strftime("%Y-%m-%d")
    key = _alert_key(alert_type, ticker, date_str)
    if key in _seen_alerts:
        return True
    # Evict oldest entries if set grows too large
    if len(_seen_alerts) >= _SEEN_ALERTS_MAX:
        _seen_alerts.clear()
    _seen_alerts.add(key)
    return False


# --------------------------------------------------------------------------- #
# Config helpers
# --------------------------------------------------------------------------- #

def _get_watchlist() -> list[str]:
    return CONFIG.get("bot", {}).get("watchlist", [])


def _get_watchlist_set() -> set[str]:
    return set(_get_watchlist())


def _scanner_cfg() -> dict:
    """Return the intelligence_scanner sub-config with sensible defaults."""
    defaults = {
        "whale_min_premium": 500_000,
        "whale_limit": 100,
        "earnings_days_ahead": 30,
        "insider_limit": 20,
        "unusual_volume_limit": 20,
        "options_max_symbols": 10,
        "options_min_iv_rank": 30,
        "sector_move_threshold_pct": 1.5,
        "dark_pool_min_notional": 1_000_000,
        "rate_limit_delay": 0.5,
    }
    cfg = CONFIG.get("intelligence_scanner", {})
    for k, v in defaults.items():
        cfg.setdefault(k, v)
    return cfg


def _rate_pause():
    """Sleep briefly between API calls to respect rate limits."""
    time.sleep(_scanner_cfg().get("rate_limit_delay", 0.5))


# --------------------------------------------------------------------------- #
# Discord embed colour map
# --------------------------------------------------------------------------- #
EMBED_COLOURS = {
    "whale_flow":           0x1E90FF,  # blue
    "earnings_warning":     0xFF8C00,  # orange
    "insider_buy":          0x2ECC71,  # green
    "unusual_volume":       0x9B59B6,  # purple
    "options_opportunity":  0x3498DB,  # light blue
    "sector_mover":         0xE67E22,  # dark orange
    "dark_pool":            0x34495E,  # dark grey-blue
}


# =========================================================================== #
# Scan: Whale Flow
# =========================================================================== #

def scan_whale_flow() -> list[dict]:
    """
    Scan for whale-level options flow that matches watchlist stocks.
    Returns alerts for unusually large options bets.
    """
    try:
        from bot.data.unusual_whales import get_options_flow

        cfg = _scanner_cfg()
        watchlist = _get_watchlist_set()
        flows = get_options_flow(
            min_premium=cfg["whale_min_premium"],
            limit=cfg["whale_limit"],
        )

        alerts = []
        for flow in flows:
            if _is_duplicate("whale_flow", flow.ticker):
                continue

            in_watchlist = flow.ticker in watchlist

            alert = {
                "type": "whale_flow",
                "ticker": flow.ticker,
                "message": (
                    f"{'[WATCHLIST] ' if in_watchlist else ''}"
                    f"WHALE {flow.sentiment.upper()} -- {flow.ticker} "
                    f"{flow.option_type.upper()} ${flow.strike} exp {flow.expiration} "
                    f"| Premium: ${flow.premium:,.0f} "
                    f"{'| SWEEP' if flow.is_sweep else ''}"
                ),
                "sentiment": flow.sentiment,
                "premium": flow.premium,
                "in_watchlist": in_watchlist,
                "data": flow.to_dict(),
            }
            alerts.append(alert)

        logger.info("Whale flow scan: %d alerts", len(alerts))
        return alerts
    except Exception as e:
        logger.error("Whale flow scan failed: %s", e, exc_info=True)
        return []


# =========================================================================== #
# Scan: Earnings Warnings  (30-day lookahead, urgency levels)
# =========================================================================== #

def _urgency_label(days_until: int) -> str:
    """Classify how urgent the earnings event is."""
    if days_until <= 0:
        return "TODAY"
    elif days_until <= 2:
        return "this_week"
    elif days_until <= 7:
        return "this_week"
    elif days_until <= 14:
        return "next_week"
    else:
        return "this_month"


def _urgency_emoji(urgency: str) -> str:
    if urgency == "TODAY":
        return ":rotating_light:"
    elif urgency == "this_week":
        return ":warning:"
    elif urgency == "next_week":
        return ":calendar:"
    return ":spiral_calendar:"


def scan_earnings_warnings() -> list[dict]:
    """
    Check if any watchlist stocks have earnings in the next 30 days.
    Critical for avoiding surprise earnings moves.
    """
    try:
        from bot.data.earnings import get_watchlist_earnings

        cfg = _scanner_cfg()
        watchlist = _get_watchlist()
        days_ahead = cfg.get("earnings_days_ahead", 30)
        events = get_watchlist_earnings(watchlist, days_ahead=days_ahead)

        alerts = []
        today = datetime.utcnow().date()
        for event in events:
            if _is_duplicate("earnings_warning", event.symbol, event.date):
                continue

            try:
                event_date = datetime.strptime(event.date, "%Y-%m-%d").date()
                days_until = (event_date - today).days
            except (ValueError, TypeError):
                days_until = 999

            urgency = _urgency_label(days_until)

            whisper_note = f" | Whisper: ${event.eps_whisper}" if event.eps_whisper else ""
            estimate_note = f" | Est: ${event.eps_estimate}" if event.eps_estimate else ""

            alert = {
                "type": "earnings_warning",
                "ticker": event.symbol,
                "urgency": urgency,
                "days_until": days_until,
                "message": (
                    f"{_urgency_emoji(urgency)} EARNINGS {urgency.upper().replace('_', ' ')} -- "
                    f"{event.symbol} reports {event.date} "
                    f"({event.time or 'TBD'})"
                    f"{estimate_note}{whisper_note}"
                ),
                "date": event.date,
                "in_watchlist": True,
                "data": event.to_dict(),
            }
            alerts.append(alert)

        # Sort most urgent first
        alerts.sort(key=lambda a: a.get("days_until", 999))
        logger.info("Earnings scan: %d alerts (%d-day lookahead)", len(alerts), days_ahead)
        return alerts
    except Exception as e:
        logger.error("Earnings scan failed: %s", e, exc_info=True)
        return []


# =========================================================================== #
# Scan: Insider Buys
# =========================================================================== #

def scan_insider_buys() -> list[dict]:
    """
    Scan for significant insider buying activity.
    Insider buys are a strong bullish signal.
    """
    try:
        from bot.data.finviz_provider import get_insider_trades

        cfg = _scanner_cfg()
        watchlist = _get_watchlist_set()
        trades = get_insider_trades()

        _rate_pause()

        alerts = []
        for trade in trades:
            is_buy = "buy" in trade.transaction.lower() or "purchase" in trade.transaction.lower()
            if not is_buy:
                continue

            ticker = trade.ticker.upper()
            if _is_duplicate("insider_buy", ticker):
                continue

            in_watchlist = ticker in watchlist

            alert = {
                "type": "insider_buy",
                "ticker": ticker,
                "message": (
                    f"{'[WATCHLIST] ' if in_watchlist else ''}"
                    f"INSIDER BUY -- {ticker}: {trade.owner} ({trade.relationship}) "
                    f"bought {trade.shares:,} shares (${trade.value:,.0f})"
                ),
                "in_watchlist": in_watchlist,
                "data": trade.to_dict(),
            }
            alerts.append(alert)

        alerts = alerts[: cfg.get("insider_limit", 20)]
        logger.info("Insider scan: %d alerts", len(alerts))
        return alerts
    except Exception as e:
        logger.error("Insider scan failed: %s", e, exc_info=True)
        return []


# =========================================================================== #
# Scan: Unusual Volume
# =========================================================================== #

def scan_unusual_volume() -> list[dict]:
    """
    Scan Finviz for stocks with unusual volume.
    These often precede big price moves.
    """
    try:
        from bot.data.finviz_provider import screen_stocks

        cfg = _scanner_cfg()
        results = screen_stocks(signal="unusual_volume")

        _rate_pause()

        watchlist = _get_watchlist_set()
        alerts = []

        for stock in results[: cfg.get("unusual_volume_limit", 20)]:
            ticker = stock.get("ticker", "")
            if not ticker or _is_duplicate("unusual_volume", ticker):
                continue

            in_watchlist = ticker in watchlist

            alert = {
                "type": "unusual_volume",
                "ticker": ticker,
                "message": (
                    f"{'[WATCHLIST] ' if in_watchlist else ''}"
                    f"UNUSUAL VOLUME -- {ticker} ({stock.get('company', '')}) "
                    f"Price: {stock.get('price', '')} Change: {stock.get('change', '')} "
                    f"Vol: {stock.get('volume', '')}"
                ),
                "in_watchlist": in_watchlist,
                "data": stock,
            }
            alerts.append(alert)

        logger.info("Unusual volume scan: %d alerts", len(alerts))
        return alerts
    except Exception as e:
        logger.error("Unusual volume scan failed: %s", e, exc_info=True)
        return []


# =========================================================================== #
# Scan: Options Opportunities  (decoupled from Analyzer)
# =========================================================================== #

def scan_options_opportunities() -> list[dict]:
    """
    Scan watchlist for options strategy opportunities based on IV rank
    and flow sentiment.  Does NOT depend on the Analyzer class -- instead
    it uses flow sentiment from Unusual Whales to determine direction and
    OptionsEngine for strategy selection.
    """
    try:
        from bot.engine.options_strategies import OptionsEngine

        cfg = _scanner_cfg()
        watchlist = _get_watchlist()
        engine = OptionsEngine()
        alerts = []
        min_iv = cfg.get("options_min_iv_rank", 30)

        for symbol in watchlist[: cfg.get("options_max_symbols", 10)]:
            try:
                _rate_pause()

                # Determine direction from flow sentiment instead of Analyzer
                direction = "neutral"
                confidence = 0.6
                try:
                    from bot.data.unusual_whales import get_ticker_sentiment
                    sentiment = get_ticker_sentiment(symbol)
                    if isinstance(sentiment, dict):
                        sent_label = sentiment.get("sentiment", "neutral").lower()
                        if sent_label == "bullish":
                            direction = "bullish"
                            confidence = 0.7
                        elif sent_label == "bearish":
                            direction = "bearish"
                            confidence = 0.7
                except Exception:
                    logger.debug("Could not fetch sentiment for %s, using neutral", symbol)

                setups = engine.recommend(symbol, direction=direction, confidence=confidence)
                tradeable = [s for s in setups if s.can_trade and s.iv_rank >= min_iv]

                if tradeable:
                    if _is_duplicate("options_opportunity", symbol):
                        continue

                    best = tradeable[0]
                    alert = {
                        "type": "options_opportunity",
                        "ticker": symbol,
                        "message": (
                            f"OPTIONS -- {symbol}: {best.strategy_name.replace('_', ' ').upper()} "
                            f"({direction}) | Max loss ${best.max_loss:.0f}, "
                            f"Max profit ${best.max_profit:.0f} | "
                            f"R/R {best.risk_reward_ratio:.1f}x | IV rank {best.iv_rank:.0f}%"
                        ),
                        "in_watchlist": True,
                        "data": best.to_dict(),
                    }
                    alerts.append(alert)
            except Exception as e:
                logger.warning("Options scan error for %s: %s", symbol, e)
                continue

        logger.info("Options opportunity scan: %d alerts", len(alerts))
        return alerts
    except Exception as e:
        logger.error("Options opportunity scan failed: %s", e, exc_info=True)
        return []


# =========================================================================== #
# Scan: Sector Movers  (NEW)
# =========================================================================== #

def scan_sector_movers() -> list[dict]:
    """
    Find sectors with unusual daily moves by comparing sector ETF
    performance to SPY.  Highlights sectors moving significantly more
    than the broad market -- useful for sector rotation trades.
    """
    try:
        from bot.engine.sector_rotation import SECTOR_ETFS

        cfg = _scanner_cfg()
        threshold = cfg.get("sector_move_threshold_pct", 1.5)

        # Fetch daily change for SPY and each sector ETF
        try:
            from bot.data.fetcher import fetch_market_data
        except ImportError:
            logger.debug("fetch_market_data unavailable for sector scan")
            return []

        _rate_pause()

        # Get SPY baseline
        spy_candles = fetch_market_data("SPY", period="5d", interval="1d")
        if not spy_candles or len(spy_candles) < 2:
            return []

        spy_change = 0.0
        if hasattr(spy_candles[-1], "close") and hasattr(spy_candles[-2], "close"):
            prev = spy_candles[-2].close
            if prev:
                spy_change = ((spy_candles[-1].close - prev) / prev) * 100
        elif isinstance(spy_candles[-1], dict):
            prev = spy_candles[-2].get("close", 0)
            if prev:
                spy_change = ((spy_candles[-1].get("close", 0) - prev) / prev) * 100

        alerts = []
        for etf, info in SECTOR_ETFS.items():
            try:
                _rate_pause()
                candles = fetch_market_data(etf, period="5d", interval="1d")
                if not candles or len(candles) < 2:
                    continue

                if hasattr(candles[-1], "close") and hasattr(candles[-2], "close"):
                    prev = candles[-2].close
                    curr = candles[-1].close
                elif isinstance(candles[-1], dict):
                    prev = candles[-2].get("close", 0)
                    curr = candles[-1].get("close", 0)
                else:
                    continue

                if not prev:
                    continue

                sector_change = ((curr - prev) / prev) * 100
                relative = sector_change - spy_change

                if abs(relative) < threshold:
                    continue

                if _is_duplicate("sector_mover", etf):
                    continue

                direction = "outperforming" if relative > 0 else "underperforming"
                alert = {
                    "type": "sector_mover",
                    "ticker": etf,
                    "message": (
                        f"SECTOR MOVE -- {info['name']} ({etf}) "
                        f"{direction} SPY by {relative:+.2f}% "
                        f"| Sector: {sector_change:+.2f}% vs SPY: {spy_change:+.2f}%"
                    ),
                    "in_watchlist": False,
                    "data": {
                        "etf": etf,
                        "sector": info["name"],
                        "sector_change_pct": round(sector_change, 2),
                        "spy_change_pct": round(spy_change, 2),
                        "relative_pct": round(relative, 2),
                        "direction": direction,
                    },
                }
                alerts.append(alert)
            except Exception as e:
                logger.debug("Sector scan error for %s: %s", etf, e)
                continue

        # Sort by magnitude of relative move
        alerts.sort(key=lambda a: abs(a["data"].get("relative_pct", 0)), reverse=True)
        logger.info("Sector movers scan: %d alerts (threshold %.1f%%)", len(alerts), threshold)
        return alerts
    except Exception as e:
        logger.error("Sector movers scan failed: %s", e, exc_info=True)
        return []


# =========================================================================== #
# Scan: Dark Pool  (NEW)
# =========================================================================== #

def scan_dark_pool() -> list[dict]:
    """
    If an Unusual Whales token is available, scan dark pool activity
    for watchlist tickers with large block prints.
    """
    if not os.getenv("UNUSUAL_WHALES_TOKEN"):
        logger.debug("Dark pool scan skipped: UNUSUAL_WHALES_TOKEN not set")
        return []

    try:
        from bot.data.unusual_whales import get_dark_pool

        cfg = _scanner_cfg()
        min_notional = cfg.get("dark_pool_min_notional", 1_000_000)
        watchlist = _get_watchlist_set()

        _rate_pause()

        # Fetch recent dark pool trades
        trades = get_dark_pool(limit=100)

        alerts = []
        for trade in trades:
            if trade.notional_value < min_notional:
                continue

            ticker = trade.ticker.upper()
            if _is_duplicate("dark_pool", ticker, trade.date):
                continue

            in_watchlist = ticker in watchlist

            alert = {
                "type": "dark_pool",
                "ticker": ticker,
                "message": (
                    f"{'[WATCHLIST] ' if in_watchlist else ''}"
                    f"DARK POOL -- {ticker} "
                    f"| {trade.size:,} shares @ ${trade.price:,.2f} "
                    f"| Notional: ${trade.notional_value:,.0f} "
                    f"| Venue: {trade.exchange or 'N/A'}"
                ),
                "in_watchlist": in_watchlist,
                "data": trade.to_dict(),
            }
            alerts.append(alert)

        # Sort by notional value descending
        alerts.sort(key=lambda a: a["data"].get("notional_value", 0), reverse=True)
        alerts = alerts[:20]
        logger.info("Dark pool scan: %d alerts (min notional $%s)", len(alerts), f"{min_notional:,}")
        return alerts
    except Exception as e:
        logger.error("Dark pool scan failed: %s", e, exc_info=True)
        return []


# =========================================================================== #
# Main orchestrator
# =========================================================================== #

def run_intelligence_scan() -> list[dict]:
    """
    Run all intelligence scans and return combined alerts.
    Prioritizes watchlist matches.
    """
    logger.info("Starting intelligence scan...")

    all_alerts: list[dict] = []

    scanners = [
        ("whale_flow", scan_whale_flow),
        ("earnings", scan_earnings_warnings),
        ("insider", scan_insider_buys),
        ("unusual_volume", scan_unusual_volume),
        ("options", scan_options_opportunities),
        ("sector_movers", scan_sector_movers),
        ("dark_pool", scan_dark_pool),
    ]

    for name, scanner_fn in scanners:
        try:
            results = scanner_fn()
            all_alerts.extend(results)
        except Exception as e:
            logger.error("Scanner '%s' raised unexpected error: %s", name, e, exc_info=True)

    # Sort: watchlist items first, then by type
    all_alerts.sort(key=lambda a: (not a.get("in_watchlist", False), a.get("type", "")))

    logger.info("Intelligence scan complete: %d total alerts", len(all_alerts))

    # Send Discord summary
    if all_alerts:
        _send_intelligence_discord(all_alerts)

    return all_alerts


# =========================================================================== #
# Discord formatting  (colour-coded embeds per alert type)
# =========================================================================== #

def _send_intelligence_discord(alerts: list[dict]):
    """Send intelligence scan results to Discord as colour-coded embeds."""
    cfg = CONFIG.get("alerts", {}).get("discord", {})
    webhook_url = cfg.get("webhook_url", "")
    if not webhook_url:
        return

    embeds = []

    # --- Earnings ---
    earnings = [a for a in alerts if a["type"] == "earnings_warning"]
    if earnings:
        lines = []
        for a in earnings:
            lines.append(a["message"])
        embeds.append({
            "title": ":calendar: Upcoming Earnings",
            "description": "\n".join(lines),
            "color": EMBED_COLOURS["earnings_warning"],
        })

    # --- Whale Flow (watchlist) ---
    whales = [a for a in alerts if a["type"] == "whale_flow" and a.get("in_watchlist")]
    if whales:
        lines = [a["message"] for a in whales[:5]]
        embeds.append({
            "title": ":whale: Whale Flow (Watchlist)",
            "description": "\n".join(lines),
            "color": EMBED_COLOURS["whale_flow"],
        })

    # --- Insider Buys (watchlist) ---
    insiders = [a for a in alerts if a["type"] == "insider_buy" and a.get("in_watchlist")]
    if insiders:
        lines = [a["message"] for a in insiders[:5]]
        embeds.append({
            "title": ":bust_in_silhouette: Insider Buys (Watchlist)",
            "description": "\n".join(lines),
            "color": EMBED_COLOURS["insider_buy"],
        })

    # --- Options Opportunities ---
    options = [a for a in alerts if a["type"] == "options_opportunity"]
    if options:
        lines = [a["message"] for a in options[:5]]
        embeds.append({
            "title": ":chart_with_upwards_trend: Options Opportunities",
            "description": "\n".join(lines),
            "color": EMBED_COLOURS["options_opportunity"],
        })

    # --- Sector Movers ---
    sectors = [a for a in alerts if a["type"] == "sector_mover"]
    if sectors:
        lines = [a["message"] for a in sectors[:5]]
        embeds.append({
            "title": ":arrows_counterclockwise: Sector Movers",
            "description": "\n".join(lines),
            "color": EMBED_COLOURS["sector_mover"],
        })

    # --- Dark Pool ---
    dark = [a for a in alerts if a["type"] == "dark_pool"]
    if dark:
        lines = [a["message"] for a in dark[:5]]
        embeds.append({
            "title": ":new_moon: Dark Pool Activity",
            "description": "\n".join(lines),
            "color": EMBED_COLOURS["dark_pool"],
        })

    # --- Unusual Volume ---
    volume = [a for a in alerts if a["type"] == "unusual_volume" and a.get("in_watchlist")]
    if volume:
        lines = [a["message"] for a in volume[:5]]
        embeds.append({
            "title": ":bar_chart: Unusual Volume (Watchlist)",
            "description": "\n".join(lines),
            "color": EMBED_COLOURS["unusual_volume"],
        })

    if not embeds:
        return

    # Add timestamp and footer to last embed
    embeds[-1]["timestamp"] = datetime.utcnow().isoformat()
    embeds[-1]["footer"] = {"text": "AI Trading Bot | Intelligence Module"}

    # Discord allows max 10 embeds per message; chunk if needed
    for i in range(0, len(embeds), 10):
        payload = {
            "username": "AI Trading Bot",
            "embeds": embeds[i : i + 10],
        }
        try:
            resp = requests.post(webhook_url, json=payload, timeout=10)
            if resp.status_code >= 400:
                logger.warning("Discord webhook returned %d: %s", resp.status_code, resp.text[:200])
        except Exception as e:
            logger.error("Discord webhook post failed: %s", e, exc_info=True)
