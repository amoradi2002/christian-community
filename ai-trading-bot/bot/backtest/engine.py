"""
Backtesting Engine - Replays historical data through strategies.
"""

from bot.data.fetcher import fetch_market_data
from bot.data.indicators import compute_indicators
from bot.data.models import MarketSnapshot
from bot.backtest.portfolio import Portfolio
from bot.backtest.report import generate_report


def run_backtest(strategy, symbol, period="2y", initial_cash=10000.0):
    """Run a backtest for a single strategy on a single symbol."""
    candles = fetch_market_data(symbol, period=period, interval="1d")
    if len(candles) < 200:
        return None

    portfolio = Portfolio(cash=initial_cash)

    for i in range(200, len(candles)):
        window = candles[max(0, i - 200):i + 1]
        indicators = compute_indicators(window)

        snapshot = MarketSnapshot(
            symbol=symbol,
            timeframe="1d",
            candles=window,
            indicators=indicators,
        )

        signal = strategy.analyze(snapshot)
        current_price = candles[i].close
        current_date = candles[i].date

        if signal:
            if signal.action == "BUY":
                portfolio.buy(symbol, current_price, current_date, strategy.name)
            elif signal.action == "SELL":
                portfolio.sell(symbol, current_price, current_date)

        portfolio.snapshot_equity(current_date, {symbol: current_price})

    # Close any remaining positions at last price
    last_price = candles[-1].close
    if symbol in portfolio.positions:
        portfolio.sell(symbol, last_price, candles[-1].date)

    return generate_report(portfolio, symbol, strategy.name)
