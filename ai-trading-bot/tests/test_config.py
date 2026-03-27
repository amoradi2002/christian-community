"""Tests for configuration loading."""
import pytest
import os
from bot.config.settings import load_config, CONFIG


class TestConfig:
    def test_config_loads(self):
        config = load_config()
        assert isinstance(config, dict)
        assert "bot" in config
        assert "data" in config
        assert "trading" in config

    def test_watchlist_exists(self):
        assert "watchlist" in CONFIG.get("bot", {})
        watchlist = CONFIG["bot"]["watchlist"]
        assert isinstance(watchlist, list)
        assert len(watchlist) > 0

    def test_confidence_threshold(self):
        threshold = CONFIG.get("bot", {}).get("confidence_threshold", 0)
        assert 0 < threshold < 1.0

    def test_database_path(self):
        db_path = CONFIG.get("database", {}).get("path", "")
        assert len(db_path) > 0

    def test_broker_config_exists(self):
        brokers = CONFIG.get("brokers", {})
        assert "default" in brokers
        assert "routing" in brokers

    def test_regime_config_exists(self):
        regime = CONFIG.get("regime", {})
        assert "enabled" in regime
        assert "benchmark" in regime

    def test_scanner_config_exists(self):
        scanner = CONFIG.get("scanner", {})
        assert "day_trade" in scanner
        assert "swing_trade" in scanner

    def test_strategies_config_exists(self):
        strategies = CONFIG.get("strategies", {})
        assert "rsi_reversal" in strategies
        assert "macd_crossover" in strategies

    def test_backtest_config_exists(self):
        backtest = CONFIG.get("backtest", {})
        assert "default_initial_cash" in backtest
        assert backtest["default_initial_cash"] > 0

    def test_ai_config_exists(self):
        ai = CONFIG.get("ai", {})
        assert "model_type" in ai
        assert "walkforward_folds" in ai

    def test_auto_fallback_yfinance(self):
        """If ALPACA_API_KEY is empty, provider should fallback."""
        old_key = os.environ.get("ALPACA_API_KEY", "")
        try:
            os.environ["ALPACA_API_KEY"] = ""
            config = load_config()
            if config.get("data", {}).get("provider") == "alpaca":
                assert config["data"]["provider"] == "yfinance"
        finally:
            os.environ["ALPACA_API_KEY"] = old_key
