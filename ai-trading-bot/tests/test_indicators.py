import unittest
from bot.data.models import Candle
from bot.data.indicators import compute_indicators


class TestIndicators(unittest.TestCase):
    def _make_candles(self, n=250):
        """Generate synthetic candles for testing."""
        candles = []
        price = 100.0
        for i in range(n):
            price += (i % 7 - 3) * 0.5  # zigzag pattern
            candles.append(Candle(
                date=f"2024-01-{(i % 28) + 1:02d}",
                open=price - 0.5,
                high=price + 1.0,
                low=price - 1.0,
                close=price,
                volume=1000000 + i * 1000,
            ))
        return candles

    def test_compute_indicators_returns_values(self):
        candles = self._make_candles(250)
        ind = compute_indicators(candles)

        self.assertGreater(ind.rsi_14, 0)
        self.assertLess(ind.rsi_14, 100)
        self.assertNotEqual(ind.macd_line, 0)
        self.assertNotEqual(ind.sma_20, 0)
        self.assertNotEqual(ind.bb_upper, 0)
        self.assertGreater(ind.bb_upper, ind.bb_lower)

    def test_short_candles_returns_defaults(self):
        candles = self._make_candles(10)
        ind = compute_indicators(candles)
        self.assertEqual(ind.rsi_14, 0.0)

    def test_sma_200_requires_enough_data(self):
        candles = self._make_candles(250)
        ind = compute_indicators(candles)
        self.assertNotEqual(ind.sma_200, 0)


if __name__ == "__main__":
    unittest.main()
