"""Tests for Signal dataclass."""
import pytest
from bot.engine.signal import Signal


class TestSignal:
    def test_signal_creation(self, sample_signal):
        assert sample_signal.action == "BUY"
        assert sample_signal.confidence == 0.78
        assert sample_signal.symbol == "AAPL"
        assert sample_signal.strategy_name == "RSI Reversal"

    def test_signal_to_dict(self, sample_signal):
        d = sample_signal.to_dict()
        assert d["action"] == "BUY"
        assert d["confidence"] == 0.78
        assert d["symbol"] == "AAPL"
        assert "stop_loss" in d
        assert "target" in d
        assert "risk_reward" in d

    def test_signal_defaults(self):
        s = Signal(action="HOLD", confidence=0.5)
        assert s.symbol == ""
        assert s.price == 0.0
        assert s.stop_loss == 0.0
        assert s.style == ""

    def test_signal_to_dict_omits_empty(self):
        s = Signal(action="BUY", confidence=0.7, symbol="MSFT", price=400.0)
        d = s.to_dict()
        assert "style" not in d
        assert "stop_loss" not in d  # 0.0 is falsy

    def test_signal_risk_reward(self):
        s = Signal(
            action="BUY", confidence=0.8, symbol="TSLA",
            price=200.0, stop_loss=190.0, target=220.0, risk_reward=2.0,
        )
        assert s.risk_reward == 2.0
        assert s.target > s.price > s.stop_loss
