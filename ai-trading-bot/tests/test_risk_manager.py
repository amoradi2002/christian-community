"""Tests for risk management."""
import pytest
from bot.engine.risk_manager import UserProfile, RiskManager, RISK_PRESETS


class TestUserProfile:
    def test_default_profile(self):
        p = UserProfile()
        assert p.starting_capital == 500.0
        assert p.risk_per_trade_pct == 2.0
        assert p.daily_loss_limit_pct == 3.0

    def test_win_rate_no_trades(self):
        p = UserProfile()
        assert p.win_rate == 0.0

    def test_win_rate_with_trades(self):
        p = UserProfile(total_trades=10, winning_trades=6, losing_trades=4)
        assert p.win_rate == 0.6

    def test_drawdown_calculation(self):
        p = UserProfile(current_capital=900.0, peak_capital=1000.0)
        assert p.drawdown_pct == 10.0

    def test_growth_calculation(self):
        p = UserProfile(starting_capital=500.0, current_capital=750.0)
        assert p.growth_pct == 50.0

    def test_risk_multiplier_winning_streak(self):
        p = UserProfile(current_streak=3)
        assert p.risk_multiplier > 1.0

    def test_risk_multiplier_losing_streak(self):
        p = UserProfile(current_streak=-3)
        assert p.risk_multiplier < 1.0

    def test_risk_multiplier_deep_drawdown(self):
        p = UserProfile(current_capital=800.0, peak_capital=1000.0)  # 20% dd
        assert p.risk_multiplier <= 0.25

    def test_risk_per_trade_dollars(self):
        p = UserProfile(current_capital=10000.0, risk_per_trade_pct=2.0)
        # With no streak/drawdown, multiplier = 1.0
        assert p.risk_per_trade_dollars() == 200.0

    def test_to_dict(self):
        p = UserProfile()
        d = p.to_dict()
        assert "win_rate" in d
        assert "drawdown_pct" in d
        assert "risk_multiplier" in d
        assert "risk_per_trade_dollars" in d


class TestRiskPresets:
    def test_conservative_preset(self):
        preset = RISK_PRESETS["conservative"]
        assert preset["risk_per_trade_pct"] == 1.0
        assert preset["max_open_positions"] == 3

    def test_moderate_preset(self):
        preset = RISK_PRESETS["moderate"]
        assert preset["risk_per_trade_pct"] == 2.0

    def test_aggressive_preset(self):
        preset = RISK_PRESETS["aggressive"]
        assert preset["risk_per_trade_pct"] == 3.0
        assert preset["daily_loss_limit_pct"] == 5.0


class TestPositionSizing:
    def test_basic_position_size(self):
        rm = RiskManager()
        rm.profile = UserProfile(current_capital=10000.0, risk_per_trade_pct=2.0)
        result = rm.calculate_position_size("AAPL", 150.0, stop_loss_pct=5.0)
        assert result["can_trade"] is True
        assert result["shares"] > 0
        assert result["stop_loss_price"] < 150.0
        assert result["take_profit_price"] > 150.0

    def test_position_size_respects_max_portfolio_pct(self):
        rm = RiskManager()
        rm.profile = UserProfile(current_capital=1000.0, max_portfolio_pct=10.0)
        result = rm.calculate_position_size("GOOGL", 170.0, stop_loss_pct=5.0)
        if result["can_trade"]:
            assert result["position_value"] <= 100.0  # 10% of 1000

    def test_insufficient_capital(self):
        rm = RiskManager()
        rm.profile = UserProfile(current_capital=10.0)
        result = rm.calculate_position_size("AAPL", 150.0, stop_loss_pct=5.0)
        assert result["can_trade"] is False

    def test_options_sizing(self):
        rm = RiskManager()
        rm.profile = UserProfile(current_capital=10000.0)
        result = rm.calculate_options_size(contract_price=3.50, confidence=0.8)
        assert result["contracts"] >= 1
        assert result["total_cost"] > 0
