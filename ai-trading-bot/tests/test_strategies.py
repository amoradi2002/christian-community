import unittest
from bot.data.models import Candle, MarketSnapshot, IndicatorSet
from bot.strategies.mentorship import MentorshipStrategy
from bot.strategies.builtin.rsi_reversal import RSIReversalStrategy


class TestMentorshipStrategy(unittest.TestCase):
    def _make_snapshot(self, rsi=25.0, macd_hist=0.5, close=150.0, sma_200=140.0):
        candles = [Candle(date="2024-01-01", open=149, high=151, low=148, close=close, volume=1000000)]
        indicators = IndicatorSet(rsi_14=rsi, macd_histogram=macd_hist, sma_200=sma_200)
        return MarketSnapshot(symbol="AAPL", timeframe="1d", candles=candles, indicators=indicators)

    def test_conditions_met_returns_buy(self):
        strategy = MentorshipStrategy(
            name="Test RSI Dip",
            description="Buy on RSI dip",
            conditions=[
                {"indicator": "rsi_14", "operator": "<=", "value": 30},
                {"indicator": "macd_histogram", "operator": ">", "value": 0},
                {"indicator": "close", "operator": ">", "ref": "sma_200"},
            ],
            signal_action="BUY",
        )
        snapshot = self._make_snapshot(rsi=25, macd_hist=0.5, close=150, sma_200=140)
        signal = strategy.analyze(snapshot)
        self.assertIsNotNone(signal)
        self.assertEqual(signal.action, "BUY")

    def test_conditions_not_met_returns_none(self):
        strategy = MentorshipStrategy(
            name="Test",
            description="",
            conditions=[{"indicator": "rsi_14", "operator": "<=", "value": 30}],
            signal_action="BUY",
        )
        snapshot = self._make_snapshot(rsi=50)
        signal = strategy.analyze(snapshot)
        self.assertIsNone(signal)

    def test_symbol_filter(self):
        strategy = MentorshipStrategy(
            name="Test",
            description="",
            conditions=[{"indicator": "rsi_14", "operator": "<=", "value": 30}],
            signal_action="BUY",
            symbols=["MSFT"],
        )
        snapshot = self._make_snapshot(rsi=25)  # symbol is AAPL
        signal = strategy.analyze(snapshot)
        self.assertIsNone(signal)

    def test_serialization_roundtrip(self):
        strategy = MentorshipStrategy(
            name="Test",
            description="desc",
            conditions=[{"indicator": "rsi_14", "operator": "<=", "value": 30}],
            signal_action="BUY",
            symbols=["AAPL"],
        )
        data = strategy.to_dict()
        restored = MentorshipStrategy.from_dict(data)
        self.assertEqual(restored.name, "Test")
        self.assertEqual(len(restored.conditions), 1)


class TestRSIReversal(unittest.TestCase):
    def _make_snapshot(self, rsi):
        candles = [Candle(date="2024-01-01", open=149, high=151, low=148, close=150, volume=1000000)]
        indicators = IndicatorSet(rsi_14=rsi)
        return MarketSnapshot(symbol="SPY", timeframe="1d", candles=candles, indicators=indicators)

    def test_oversold_buy(self):
        strategy = RSIReversalStrategy()
        signal = strategy.analyze(self._make_snapshot(rsi=25))
        self.assertIsNotNone(signal)
        self.assertEqual(signal.action, "BUY")

    def test_overbought_sell(self):
        strategy = RSIReversalStrategy()
        signal = strategy.analyze(self._make_snapshot(rsi=75))
        self.assertIsNotNone(signal)
        self.assertEqual(signal.action, "SELL")

    def test_neutral_no_signal(self):
        strategy = RSIReversalStrategy()
        signal = strategy.analyze(self._make_snapshot(rsi=50))
        self.assertIsNone(signal)


if __name__ == "__main__":
    unittest.main()
