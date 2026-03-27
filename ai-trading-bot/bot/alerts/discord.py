import requests
from datetime import datetime
from bot.alerts.base import AlertChannel
from bot.engine.signal import Signal
from bot.config.settings import CONFIG

COLORS = {"BUY": 0x00FF00, "SELL": 0xFF0000, "HOLD": 0xFFFF00}
ICONS = {"BUY": ":green_circle:", "SELL": ":red_circle:", "HOLD": ":yellow_circle:"}
STYLE_LABELS = {"day": "Day Trade", "swing": "Swing Trade", "options": "Options"}


class DiscordChannel(AlertChannel):
    def send(self, signal: Signal) -> bool:
        cfg = CONFIG.get("alerts", {}).get("discord", {})
        webhook_url = cfg.get("webhook_url", "")
        if not webhook_url:
            return False

        color = COLORS.get(signal.action, 0xFFFFFF)
        icon = ICONS.get(signal.action, ":white_circle:")
        style_label = STYLE_LABELS.get(signal.style, "")

        # Build the trade analysis template from the skill
        fields = [
            {"name": "Action", "value": signal.action, "inline": True},
            {"name": "Confidence", "value": f"{signal.confidence:.0%}", "inline": True},
            {"name": "Price", "value": f"${signal.price:.2f}", "inline": True},
        ]

        if style_label:
            fields.append({"name": "Style", "value": style_label, "inline": True})
        if signal.setup:
            fields.append({"name": "Setup", "value": signal.setup, "inline": True})
        if signal.catalyst_tier:
            fields.append({"name": "Catalyst Tier", "value": signal.catalyst_tier, "inline": True})

        # Trade levels
        if signal.stop_loss:
            fields.append({"name": "Stop Loss", "value": f"${signal.stop_loss:.2f}", "inline": True})
        if signal.target:
            fields.append({"name": "Target", "value": f"${signal.target:.2f}", "inline": True})
        if signal.risk_reward:
            fields.append({"name": "R:R", "value": f"{signal.risk_reward:.1f}:1", "inline": True})

        if signal.candle_pattern:
            fields.append({"name": "Candle Signal", "value": signal.candle_pattern, "inline": True})

        reasons = "\n".join(f"- {r}" for r in signal.reasons)

        # Title includes setup name if available
        title_parts = [icon, signal.action, "—", signal.symbol]
        if signal.setup:
            title_parts.extend(["—", signal.setup])

        payload = {
            "username": "AI Trading Bot",
            "embeds": [{
                "title": " ".join(title_parts),
                "description": f"**Strategy:** {signal.strategy_name}\n\n**Analysis:**\n{reasons}",
                "color": color,
                "timestamp": datetime.utcnow().isoformat(),
                "footer": {"text": "AI Trading Bot | Not financial advice | You make your own decisions"},
                "fields": fields,
            }]
        }

        try:
            resp = requests.post(webhook_url, json=payload, timeout=10)
            return resp.status_code in (200, 204)
        except Exception as e:
            print(f"Discord alert failed: {e}")
            return False

    def send_summary(self, signals: list[Signal]) -> bool:
        """Send a summary of all signals from a scan."""
        cfg = CONFIG.get("alerts", {}).get("discord", {})
        webhook_url = cfg.get("webhook_url", "")
        if not webhook_url or not signals:
            return False

        buys = [s for s in signals if s.action == "BUY"]
        sells = [s for s in signals if s.action == "SELL"]

        # Group by style
        day_signals = [s for s in signals if s.style == "day"]
        swing_signals = [s for s in signals if s.style == "swing"]
        other_signals = [s for s in signals if s.style not in ("day", "swing")]

        lines = []

        if day_signals:
            lines.append("**:zap: Day Trade Signals:**")
            for s in day_signals:
                icon = ":green_circle:" if s.action == "BUY" else ":red_circle:"
                setup_info = f" [{s.setup}]" if s.setup else ""
                rr_info = f" R:R {s.risk_reward:.1f}:1" if s.risk_reward else ""
                lines.append(f"  {icon} {s.symbol} @ ${s.price:.2f} ({s.confidence:.0%}){setup_info}{rr_info}")

        if swing_signals:
            lines.append("**:chart_with_upwards_trend: Swing Trade Signals:**")
            for s in swing_signals:
                icon = ":green_circle:" if s.action == "BUY" else ":red_circle:"
                setup_info = f" [{s.setup}]" if s.setup else ""
                rr_info = f" R:R {s.risk_reward:.1f}:1" if s.risk_reward else ""
                lines.append(f"  {icon} {s.symbol} @ ${s.price:.2f} ({s.confidence:.0%}){setup_info}{rr_info}")

        if other_signals:
            lines.append("**:bar_chart: Other Signals:**")
            for s in other_signals:
                icon = ":green_circle:" if s.action == "BUY" else ":red_circle:"
                lines.append(f"  {icon} {s.symbol} @ ${s.price:.2f} ({s.confidence:.0%}) — {s.strategy_name}")

        # Add summary stats
        lines.append("")
        lines.append(f"**Total:** {len(buys)} BUY | {len(sells)} SELL")

        payload = {
            "username": "AI Trading Bot",
            "embeds": [{
                "title": f"Scan Summary — {len(signals)} Signal(s)",
                "description": "\n".join(lines),
                "color": 0x58a6ff,
                "timestamp": datetime.utcnow().isoformat(),
                "footer": {"text": "AI Trading Bot | Not financial advice"},
            }]
        }

        try:
            resp = requests.post(webhook_url, json=payload, timeout=10)
            return resp.status_code in (200, 204)
        except Exception as e:
            print(f"Discord summary failed: {e}")
            return False

    def send_sector_report(self, report: dict) -> bool:
        """Send sector rotation report to Discord."""
        cfg = CONFIG.get("alerts", {}).get("discord", {})
        webhook_url = cfg.get("webhook_url", "")
        if not webhook_url:
            return False

        regime_icons = {"risk-on": ":rocket:", "risk-off": ":shield:", "mixed": ":scales:"}
        icon = regime_icons.get(report.get("market_regime", ""), ":bar_chart:")

        lines = [f"**Market Regime:** {icon} {report.get('market_regime', 'unknown').title()}"]
        lines.append("")

        top = report.get("top_sectors", [])
        bottom = report.get("bottom_sectors", [])

        if top:
            lines.append("**Leading Sectors:**")
            for s in report.get("sectors", [])[:3]:
                lines.append(f"  :arrow_up: {s['symbol']} ({s['name']}) {s['relative_to_spy']:+.1f}% vs SPY")
        if bottom:
            lines.append("**Lagging Sectors:**")
            for s in report.get("sectors", [])[-3:]:
                lines.append(f"  :arrow_down: {s['symbol']} ({s['name']}) {s['relative_to_spy']:+.1f}% vs SPY")

        lines.append("")
        lines.append(f"**Recommendation:** {report.get('recommendation', '')}")

        payload = {
            "username": "AI Trading Bot",
            "embeds": [{
                "title": "Sector Rotation Report",
                "description": "\n".join(lines),
                "color": 0x9b59b6,
                "timestamp": datetime.utcnow().isoformat(),
                "footer": {"text": "AI Trading Bot | Weekly sector analysis"},
            }]
        }

        try:
            resp = requests.post(webhook_url, json=payload, timeout=10)
            return resp.status_code in (200, 204)
        except Exception as e:
            print(f"Discord sector report failed: {e}")
            return False

    def send_journal_review(self, review: dict) -> bool:
        """Send weekly trade journal review to Discord."""
        cfg = CONFIG.get("alerts", {}).get("discord", {})
        webhook_url = cfg.get("webhook_url", "")
        if not webhook_url:
            return False

        lines = [f"**Week:** {review.get('week', '')}"]
        lines.append(f"**Total Trades:** {review.get('total_trades', 0)}")
        lines.append(f"**Win Rate:** {review.get('win_rate', 0):.1f}%")
        lines.append(f"**Total P&L:** ${review.get('total_pnl', 0):.2f}")
        lines.append(f"**Avg R Winner:** {review.get('avg_r_winner', 0):+.2f}R")
        lines.append(f"**Avg R Loser:** {review.get('avg_r_loser', 0):+.2f}R")
        lines.append(f"**Process Score:** {review.get('avg_process_score', 0):.1f}/5")

        best = review.get("best_trade")
        worst = review.get("worst_trade")
        if best:
            lines.append(f"\n**Best Trade:** {best['symbol']} ${best['pnl_dollars']:+.2f} ({best.get('setup', '')})")
        if worst:
            lines.append(f"**Worst Trade:** {worst['symbol']} ${worst['pnl_dollars']:+.2f} ({worst.get('setup', '')})")

        rules = review.get("rules_broken", [])
        if rules:
            lines.append("\n**Rules Broken:**")
            for r in rules:
                lines.append(f"  :warning: {r}")

        color = 0x00FF00 if review.get("total_pnl", 0) >= 0 else 0xFF0000

        payload = {
            "username": "AI Trading Bot",
            "embeds": [{
                "title": "Weekly Trade Journal Review",
                "description": "\n".join(lines),
                "color": color,
                "timestamp": datetime.utcnow().isoformat(),
                "footer": {"text": "AI Trading Bot | Review your process, not just results"},
            }]
        }

        try:
            resp = requests.post(webhook_url, json=payload, timeout=10)
            return resp.status_code in (200, 204)
        except Exception as e:
            print(f"Discord journal review failed: {e}")
            return False
