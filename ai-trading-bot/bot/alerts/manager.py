import json
from bot.alerts.console import ConsoleChannel
from bot.alerts.email import EmailChannel
from bot.alerts.discord import DiscordChannel
from bot.alerts.telegram import TelegramChannel
from bot.engine.signal import Signal
from bot.config.settings import CONFIG
from bot.db.database import get_connection


class AlertManager:
    def __init__(self):
        self.channels = []
        alerts_cfg = CONFIG.get("alerts", {})

        if alerts_cfg.get("console", {}).get("enabled", True):
            self.channels.append(ConsoleChannel())
        if alerts_cfg.get("email", {}).get("enabled", False):
            self.channels.append(EmailChannel())
        if alerts_cfg.get("discord", {}).get("enabled", False):
            self.channels.append(DiscordChannel())
        if alerts_cfg.get("telegram", {}).get("enabled", False):
            self.channels.append(TelegramChannel())

    def dispatch(self, signal: Signal, strategy_id=None):
        """Send alert through all enabled channels and log to database."""
        # Log to database
        conn = get_connection()
        conn.execute(
            """INSERT INTO alerts (strategy_id, symbol, signal, confidence, reasons, price_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                strategy_id,
                signal.symbol,
                signal.action,
                signal.confidence,
                json.dumps(signal.reasons),
                signal.price,
            ),
        )
        conn.commit()
        conn.close()

        # Send through channels
        for channel in self.channels:
            try:
                channel.send(signal)
            except Exception as e:
                print(f"Alert channel {channel.__class__.__name__} failed: {e}")

    def get_alert_history(self, limit=50, symbol=None):
        """Get recent alerts from database."""
        conn = get_connection()
        if symbol:
            rows = conn.execute(
                """SELECT a.*, s.name as strategy_name
                   FROM alerts a LEFT JOIN strategies s ON a.strategy_id = s.id
                   WHERE a.symbol = ? ORDER BY a.created_at DESC LIMIT ?""",
                (symbol, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT a.*, s.name as strategy_name
                   FROM alerts a LEFT JOIN strategies s ON a.strategy_id = s.id
                   ORDER BY a.created_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
