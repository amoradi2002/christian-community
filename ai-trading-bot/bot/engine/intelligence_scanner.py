"""
Intelligence Scanner - Scans Unusual Whales, Finviz, and Earnings Whispers
for actionable alerts and sends them through the alert system.

Runs alongside the regular strategy scanner to provide additional intelligence:
- Whale flow alerts (big money options bets)
- Earnings warnings (watchlist stocks reporting soon)
- Insider buying activity
- Unusual volume + oversold screener picks
"""

import requests
from datetime import datetime

from bot.config.settings import CONFIG
from bot.engine.signal import Signal


def scan_whale_flow() -> list[dict]:
    """
    Scan for whale-level options flow that matches watchlist stocks.
    Returns alerts for unusually large options bets.
    """
    try:
        from bot.data.unusual_whales import get_options_flow
        watchlist = set(CONFIG.get("bot", {}).get("watchlist", []))
        flows = get_options_flow(min_premium=500000, limit=100)

        alerts = []
        for flow in flows:
            in_watchlist = flow.ticker in watchlist

            alert = {
                "type": "whale_flow",
                "ticker": flow.ticker,
                "message": (
                    f"{'[WATCHLIST] ' if in_watchlist else ''}"
                    f"WHALE {flow.sentiment.upper()} — {flow.ticker} "
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

        return alerts
    except Exception as e:
        print(f"Whale flow scan error: {e}")
        return []


def scan_earnings_warnings() -> list[dict]:
    """
    Check if any watchlist stocks have earnings in the next 7 days.
    Critical for avoiding surprise earnings moves.
    """
    try:
        from bot.data.earnings import get_watchlist_earnings
        watchlist = CONFIG.get("bot", {}).get("watchlist", [])
        events = get_watchlist_earnings(watchlist, days_ahead=7)

        alerts = []
        for event in events:
            whisper_note = f" | Whisper: ${event.eps_whisper}" if event.eps_whisper else ""
            estimate_note = f" | Est: ${event.eps_estimate}" if event.eps_estimate else ""

            alert = {
                "type": "earnings_warning",
                "ticker": event.symbol,
                "message": (
                    f"EARNINGS ALERT — {event.symbol} reports {event.date} "
                    f"({event.time or 'TBD'})"
                    f"{estimate_note}{whisper_note}"
                ),
                "date": event.date,
                "data": event.to_dict(),
            }
            alerts.append(alert)

        return alerts
    except Exception as e:
        print(f"Earnings scan error: {e}")
        return []


def scan_insider_buys() -> list[dict]:
    """
    Scan for significant insider buying activity.
    Insider buys are a strong bullish signal.
    """
    try:
        from bot.data.finviz_provider import get_insider_trades
        watchlist = set(CONFIG.get("bot", {}).get("watchlist", []))
        trades = get_insider_trades()

        alerts = []
        for trade in trades:
            is_buy = "buy" in trade.transaction.lower() or "purchase" in trade.transaction.lower()
            if not is_buy:
                continue

            in_watchlist = trade.ticker.upper() in watchlist

            alert = {
                "type": "insider_buy",
                "ticker": trade.ticker,
                "message": (
                    f"{'[WATCHLIST] ' if in_watchlist else ''}"
                    f"INSIDER BUY — {trade.ticker}: {trade.owner} ({trade.relationship}) "
                    f"bought {trade.shares:,} shares (${trade.value:,.0f})"
                ),
                "in_watchlist": in_watchlist,
                "data": trade.to_dict(),
            }
            alerts.append(alert)

        return alerts[:20]
    except Exception as e:
        print(f"Insider scan error: {e}")
        return []


def scan_unusual_volume() -> list[dict]:
    """
    Scan Finviz for stocks with unusual volume.
    These often precede big price moves.
    """
    try:
        from bot.data.finviz_provider import screen_stocks
        results = screen_stocks(signal="unusual_volume")

        watchlist = set(CONFIG.get("bot", {}).get("watchlist", []))
        alerts = []

        for stock in results[:20]:
            ticker = stock.get("ticker", "")
            in_watchlist = ticker in watchlist

            alert = {
                "type": "unusual_volume",
                "ticker": ticker,
                "message": (
                    f"{'[WATCHLIST] ' if in_watchlist else ''}"
                    f"UNUSUAL VOLUME — {ticker} ({stock.get('company', '')}) "
                    f"Price: {stock.get('price', '')} Change: {stock.get('change', '')} "
                    f"Vol: {stock.get('volume', '')}"
                ),
                "in_watchlist": in_watchlist,
                "data": stock,
            }
            alerts.append(alert)

        return alerts
    except Exception as e:
        print(f"Volume scan error: {e}")
        return []


def scan_options_opportunities() -> list[dict]:
    """
    Scan watchlist for options strategy opportunities based on IV rank
    and recent signals. High IV = sell premium, Low IV = buy options.
    """
    try:
        from bot.engine.options_strategies import OptionsEngine
        from bot.engine.analyzer import analyze_symbol

        watchlist = CONFIG.get("bot", {}).get("watchlist", [])
        engine = OptionsEngine()
        alerts = []

        for symbol in watchlist[:10]:  # Limit to avoid slow scans
            try:
                analysis = analyze_symbol(symbol)
                if not analysis or not analysis.get("signal"):
                    continue

                signal = analysis["signal"]
                confidence = analysis.get("confidence", 0.5)
                if confidence < 0.6:
                    continue

                direction = "bullish" if signal == "BUY" else "bearish" if signal == "SELL" else "neutral"
                setups = engine.recommend(symbol, direction=direction, confidence=confidence)
                tradeable = [s for s in setups if s.can_trade]

                if tradeable:
                    best = tradeable[0]
                    alert = {
                        "type": "options_opportunity",
                        "ticker": symbol,
                        "message": (
                            f"OPTIONS — {symbol}: {best.strategy_name.replace('_', ' ').upper()} "
                            f"({direction}) | Max loss ${best.max_loss:.0f}, "
                            f"Max profit ${best.max_profit:.0f} | "
                            f"R/R {best.risk_reward_ratio:.1f}x | IV rank {best.iv_rank:.0f}%"
                        ),
                        "in_watchlist": True,
                        "data": best.to_dict(),
                    }
                    alerts.append(alert)
            except Exception:
                continue

        return alerts
    except Exception as e:
        print(f"Options opportunity scan error: {e}")
        return []


def run_intelligence_scan() -> list[dict]:
    """
    Run all intelligence scans and return combined alerts.
    Prioritizes watchlist matches.
    """
    print("\nRunning intelligence scan...")

    all_alerts = []
    all_alerts.extend(scan_whale_flow())
    all_alerts.extend(scan_earnings_warnings())
    all_alerts.extend(scan_insider_buys())
    all_alerts.extend(scan_unusual_volume())
    all_alerts.extend(scan_options_opportunities())

    # Sort: watchlist items first, then by type
    all_alerts.sort(key=lambda a: (not a.get("in_watchlist", False), a.get("type", "")))

    print(f"Intelligence scan: {len(all_alerts)} alerts found")

    # Send Discord summary
    if all_alerts:
        _send_intelligence_discord(all_alerts)

    return all_alerts


def _send_intelligence_discord(alerts: list[dict]):
    """Send intelligence scan results to Discord."""
    cfg = CONFIG.get("alerts", {}).get("discord", {})
    webhook_url = cfg.get("webhook_url", "")
    if not webhook_url:
        return

    # Group by type
    whales = [a for a in alerts if a["type"] == "whale_flow" and a.get("in_watchlist")]
    earnings = [a for a in alerts if a["type"] == "earnings_warning"]
    insiders = [a for a in alerts if a["type"] == "insider_buy" and a.get("in_watchlist")]

    lines = []
    if earnings:
        lines.append("**:calendar: Upcoming Earnings:**")
        for a in earnings:
            lines.append(f"  {a['message']}")

    if whales:
        lines.append("\n**:whale: Whale Flow (Watchlist):**")
        for a in whales[:5]:
            lines.append(f"  {a['message']}")

    if insiders:
        lines.append("\n**:bust_in_silhouette: Insider Buys (Watchlist):**")
        for a in insiders[:5]:
            lines.append(f"  {a['message']}")

    options = [a for a in alerts if a["type"] == "options_opportunity"]
    if options:
        lines.append("\n**:chart_with_upwards_trend: Options Opportunities:**")
        for a in options[:5]:
            lines.append(f"  {a['message']}")

    if not lines:
        return

    payload = {
        "username": "AI Trading Bot",
        "embeds": [{
            "title": ":brain: Intelligence Scan",
            "description": "\n".join(lines),
            "color": 0x8b5cf6,
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {"text": "AI Trading Bot | Intelligence Module"},
        }]
    }

    try:
        requests.post(webhook_url, json=payload, timeout=10)
    except Exception:
        pass
