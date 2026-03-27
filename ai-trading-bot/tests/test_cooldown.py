"""Tests for alert cooldown system."""
import pytest
from bot.alerts.cooldown import AlertCooldown


class TestAlertCooldown:
    def test_first_alert_allowed(self):
        cd = AlertCooldown(cooldown_minutes=30)
        assert cd.should_alert("AAPL", "RSI Reversal", "BUY") is True

    def test_duplicate_blocked(self):
        cd = AlertCooldown(cooldown_minutes=30)
        cd.should_alert("AAPL", "RSI Reversal", "BUY")
        assert cd.should_alert("AAPL", "RSI Reversal", "BUY") is False

    def test_different_symbol_allowed(self):
        cd = AlertCooldown(cooldown_minutes=30)
        cd.should_alert("AAPL", "RSI Reversal", "BUY")
        assert cd.should_alert("MSFT", "RSI Reversal", "BUY") is True

    def test_different_strategy_allowed(self):
        cd = AlertCooldown(cooldown_minutes=30)
        cd.should_alert("AAPL", "RSI Reversal", "BUY")
        assert cd.should_alert("AAPL", "MACD Crossover", "BUY") is True

    def test_different_action_allowed(self):
        cd = AlertCooldown(cooldown_minutes=30)
        cd.should_alert("AAPL", "RSI Reversal", "BUY")
        assert cd.should_alert("AAPL", "RSI Reversal", "SELL") is True
