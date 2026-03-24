import requests
from datetime import datetime
from bot.alerts.base import AlertChannel
from bot.engine.signal import Signal
from bot.config.settings import CONFIG

COLORS = {"BUY": 0x00FF00, "SELL": 0xFF0000, "HOLD": 0xFFFF00}
ICONS = {"BUY": ":green_circle:", "SELL": ":red_circle:", "HOLD": ":yellow_circle:"}


class DiscordChannel(AlertChannel):
    def send(self, signal: Signal) -> bool:
        cfg = CONFIG.get("alerts", {}).get("discord", {})
        webhook_url = cfg.get("webhook_url", "")
        if not webhook_url:
            return False

        color = COLORS.get(signal.action, 0xFFFFFF)
        icon = ICONS.get(signal.action, ":white_circle:")
        reasons = "\n".join(f"- {r}" for r in signal.reasons)

        # Build rich Discord embed
        payload = {
            "username": "AI Trading Bot",
            "embeds": [{
                "title": f"{icon} {signal.action} — {signal.symbol}",
                "description": (
                    f"**Price:** ${signal.price:.2f}\n"
                    f"**Confidence:** {signal.confidence:.1%}\n"
                    f"**Strategy:** {signal.strategy_name}\n\n"
                    f"**Why:**\n{reasons}"
                ),
                "color": color,
                "timestamp": datetime.utcnow().isoformat(),
                "footer": {"text": "AI Trading Bot | Not financial advice"},
                "fields": [
                    {"name": "Action", "value": signal.action, "inline": True},
                    {"name": "Confidence", "value": f"{signal.confidence:.0%}", "inline": True},
                    {"name": "Symbol", "value": signal.symbol, "inline": True},
                ],
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

        lines = []
        if buys:
            lines.append("**:green_circle: BUY Signals:**")
            for s in buys:
                lines.append(f"  {s.symbol} @ ${s.price:.2f} ({s.confidence:.0%}) — {s.strategy_name}")
        if sells:
            lines.append("**:red_circle: SELL Signals:**")
            for s in sells:
                lines.append(f"  {s.symbol} @ ${s.price:.2f} ({s.confidence:.0%}) — {s.strategy_name}")

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
