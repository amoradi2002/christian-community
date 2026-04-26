"""
Alert Cooldown System - Prevents spamming the same signal repeatedly.

When the bot detects a BUY signal for AAPL via momentum strategy, you don't
want to get pinged every 5 minutes with the same alert. This module keeps
an in-memory cache of recently sent alerts and suppresses duplicates within
a configurable cooldown window.

Configurable via config.yaml:
    alerts:
      cooldown_minutes: 30
"""

from datetime import datetime, timedelta
from bot.config.settings import CONFIG


class AlertCooldown:
    """
    In-memory cooldown tracker for alert deduplication.

    Each alert is keyed by (symbol, strategy_name, action). If an alert
    with the same key was sent within the cooldown window, it is suppressed.
    """

    def __init__(self, default_minutes=30):
        cooldown_cfg = CONFIG.get("alerts", {}).get("cooldown_minutes")
        self.cooldown_minutes = cooldown_cfg if cooldown_cfg is not None else default_minutes
        # {key_string: datetime} — timestamp of last alert sent
        self._cache: dict[str, datetime] = {}

    def _make_key(self, symbol: str, strategy_name: str, action: str) -> str:
        """Build a consistent cache key from the alert components."""
        return f"{symbol.upper()}|{strategy_name}|{action.upper()}"

    def can_alert(self, symbol: str, strategy_name: str, action: str) -> bool:
        """
        Returns True if enough time has passed since the last alert
        for this symbol/strategy/action combination.
        """
        key = self._make_key(symbol, strategy_name, action)
        last_sent = self._cache.get(key)
        if last_sent is None:
            return True
        elapsed = datetime.now() - last_sent
        return elapsed >= timedelta(minutes=self.cooldown_minutes)

    def record_alert(self, symbol: str, strategy_name: str, action: str):
        """Record that an alert was just sent for this combination."""
        key = self._make_key(symbol, strategy_name, action)
        self._cache[key] = datetime.now()

    def clear(self, symbol: str | None = None):
        """
        Clear cooldowns.

        Args:
            symbol: If provided, only clear cooldowns for that symbol.
                    If None, clear all cooldowns.
        """
        if symbol is None:
            self._cache.clear()
            return

        prefix = symbol.upper() + "|"
        keys_to_remove = [k for k in self._cache if k.startswith(prefix)]
        for k in keys_to_remove:
            del self._cache[k]

    def get_active_cooldowns(self) -> list[dict]:
        """
        Return a list of active (non-expired) cooldowns with time remaining.

        Each entry is a dict with:
            - symbol, strategy, action: the alert components
            - sent_at: when the alert was last sent (ISO string)
            - expires_at: when the cooldown expires (ISO string)
            - remaining_seconds: seconds until the cooldown expires
        """
        now = datetime.now()
        window = timedelta(minutes=self.cooldown_minutes)
        active = []

        for key, sent_at in self._cache.items():
            expires_at = sent_at + window
            if expires_at > now:
                parts = key.split("|", 2)
                remaining = (expires_at - now).total_seconds()
                active.append({
                    "symbol": parts[0],
                    "strategy": parts[1],
                    "action": parts[2],
                    "sent_at": sent_at.isoformat(),
                    "expires_at": expires_at.isoformat(),
                    "remaining_seconds": round(remaining),
                })

        # Sort by expiration (soonest first)
        active.sort(key=lambda x: x["remaining_seconds"])
        return active
