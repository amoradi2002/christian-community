import requests
from bot.alerts.base import AlertChannel
from bot.engine.signal import Signal
from bot.config.settings import CONFIG


class TelegramChannel(AlertChannel):
    def send(self, signal: Signal) -> bool:
        cfg = CONFIG.get("alerts", {}).get("telegram", {})
        bot_token = cfg.get("bot_token", "")
        chat_id = cfg.get("chat_id", "")
        if not bot_token or not chat_id:
            return False

        icon = {"BUY": "🟢", "SELL": "🔴", "HOLD": "🟡"}.get(signal.action, "⚪")
        reasons = "\n".join(f"  • {r}" for r in signal.reasons)

        text = (
            f"{icon} *{signal.action} {signal.symbol}* @ ${signal.price:.2f}\n\n"
            f"Confidence: {signal.confidence:.1%}\n"
            f"Strategy: {signal.strategy_name}\n\n"
            f"Reasons:\n{reasons}"
        )

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}

        try:
            resp = requests.post(url, json=payload, timeout=10)
            return resp.ok
        except Exception as e:
            print(f"Telegram alert failed: {e}")
            return False
