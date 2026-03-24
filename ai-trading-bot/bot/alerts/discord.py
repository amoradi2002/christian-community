import requests
from bot.alerts.base import AlertChannel
from bot.engine.signal import Signal
from bot.config.settings import CONFIG

COLORS = {"BUY": 0x00FF00, "SELL": 0xFF0000, "HOLD": 0xFFFF00}


class DiscordChannel(AlertChannel):
    def send(self, signal: Signal) -> bool:
        cfg = CONFIG.get("alerts", {}).get("discord", {})
        webhook_url = cfg.get("webhook_url", "")
        if not webhook_url:
            return False

        color = COLORS.get(signal.action, 0xFFFFFF)
        reasons = "\n".join(f"- {r}" for r in signal.reasons)

        payload = {
            "embeds": [{
                "title": f"{signal.action} {signal.symbol} @ ${signal.price:.2f}",
                "description": (
                    f"**Confidence:** {signal.confidence:.1%}\n"
                    f"**Strategy:** {signal.strategy_name}\n\n"
                    f"**Reasons:**\n{reasons}"
                ),
                "color": color,
            }]
        }

        try:
            resp = requests.post(webhook_url, json=payload, timeout=10)
            return resp.status_code in (200, 204)
        except Exception as e:
            print(f"Discord alert failed: {e}")
            return False
