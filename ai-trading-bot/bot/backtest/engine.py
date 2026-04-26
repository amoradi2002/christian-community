"""
Backtesting Engine - Comprehensive strategy backtesting framework.

Supports single and multi-strategy backtesting, multi-symbol universes,
walk-forward analysis, Monte Carlo simulation, benchmark comparison,
and automatic stop-loss/take-profit execution during replay.
"""

import logging
from copy import deepcopy
from dataclasses import dataclass, field

import numpy as np

from bot.data.fetcher import fetch_market_data
from bot.data.indicators import compute_indicators
from bot.data.models import MarketSnapshot
from bot.backtest.portfolio import Portfolio, Position
from bot.backtest.report import (
    generate_report,
    BacktestResult,
    WalkforwardResult,
    WalkforwardWindow,
    MonteCarloResult,
)

logger = logging.getLogger(__name__)

# Minimum candles required to compute full indicator set
MIN_CANDLES = 200


# ─── Configuration ───────────────────────────────────────────────────

@dataclass
class BacktestConfig:
    """Configuration for a backtest run."""
    initial_cash: float = 10000.0
    slippage_pct: float = 0.05
    commission_per_trade: float = 0.0
    max_positions: int = 10
    position_size_pct: float = 10.0
    use_stops: bool = True          # auto-execute stop/target from signals
    trailing_stop_pct: float = 0.0  # global trailing stop (0 = disabled)
    period: str = "2y"
    interval: str = "1d"
    benchmark_symbol: str = "SPY"
    margin_requirement: float = 150.0

    def to_portfolio(self) -> Portfolio:
        """Create a Portfolio configured from these settings."""
        return Portfolio(
            cash=self.initial_cash,
            initial_cash=self.initial_cash,
            slippage_pct=self.slippage_pct,
            commission_per_trade=self.commission_per_trade,
            max_positions=self.max_positions,
            position_size_pct=self.position_size_pct,
            margin_requirement=self.margin_requirement,
        )


# ─── Single Backtest ─────────────────────────────────────────────────

def run_backtest(strategy, symbol: str, period: str = "2y",
                 initial_cash: float = 10000.0, **kwargs) -> BacktestResult | None:
    """
    Run a backtest for a single strategy on a single symbol.

    Args:
        strategy: A Strategy instance with an analyze() method.
        symbol: Ticker symbol to test.
        period: Data period (e.g., "1y", "2y", "5y").
        initial_cash: Starting cash.
        **kwargs: Additional BacktestConfig parameters
                  (slippage_pct, commission_per_trade, max_positions,
                   position_size_pct, use_stops, trailing_stop_pct,
                   benchmark_symbol).

    Returns:
        BacktestResult or None if insufficient data.
    """
    config = BacktestConfig(initial_cash=initial_cash, period=period, **kwargs)
    return _execute_backtest(strategy, symbol, config)


def _execute_backtest(strategy, symbol: str, config: BacktestConfig) -> BacktestResult | None:
    """Core backtest execution logic."""
    candles = fetch_market_data(symbol, period=config.period, interval=config.interval)
    if candles is None or len(candles) < MIN_CANDLES:
        logger.warning("Insufficient data for %s: got %d candles, need %d",
                        symbol, len(candles) if candles else 0, MIN_CANDLES)
        return None

    portfolio = config.to_portfolio()

    # Fetch benchmark data for comparison
    benchmark_prices = _fetch_benchmark_prices(config.benchmark_symbol,
                                                config.period, config.interval,
                                                len(candles))

    for i in range(MIN_CANDLES, len(candles)):
        window = candles[max(0, i - MIN_CANDLES):i + 1]
        indicators = compute_indicators(window)

        snapshot = MarketSnapshot(
            symbol=symbol,
            timeframe=config.interval,
            candles=window,
            indicators=indicators,
        )

        current_candle = candles[i]
        current_price = current_candle.close
        current_date = current_candle.date

        # Build candle data for accurate stop checking
        candle_data = {
            symbol: {"high": current_candle.high, "low": current_candle.low}
        }

        # Check stops BEFORE processing new signals (order matters)
        if config.use_stops:
            portfolio.check_stops(
                {symbol: current_price},
                current_date,
                candle_data=candle_data,
            )

        # Get strategy signal
        signal = strategy.analyze(snapshot)

        if signal:
            _process_signal(portfolio, signal, symbol, current_price,
                            current_date, strategy.name, config)

        # Record equity snapshot
        portfolio.snapshot_equity(current_date, {symbol: current_price})

    # Close remaining positions at last price
    if candles:
        last_candle = candles[-1]
        portfolio.close_all_positions(
            {symbol: last_candle.close},
            last_candle.date,
            exit_reason="backtest_end",
        )

    # Align benchmark prices to equity curve length
    eq_len = len(portfolio.equity_curve)
    if benchmark_prices and len(benchmark_prices) >= eq_len:
        # Take the last eq_len prices to align
        aligned_bench = benchmark_prices[len(benchmark_prices) - eq_len:]
    elif benchmark_prices:
        aligned_bench = benchmark_prices
    else:
        aligned_bench = None

    return generate_report(
        portfolio, symbol, strategy.name,
        benchmark_prices=aligned_bench,
        period=config.period,
    )


def _process_signal(portfolio: Portfolio, signal, symbol: str,
                    current_price: float, current_date: str,
                    strategy_name: str, config: BacktestConfig) -> None:
    """Translate a Signal into portfolio actions."""
    stop_loss = signal.stop_loss if hasattr(signal, "stop_loss") else 0.0
    take_profit = signal.target if hasattr(signal, "target") else 0.0
    trailing = config.trailing_stop_pct

    if signal.action == "BUY":
        portfolio.buy(
            symbol=symbol,
            price=current_price,
            date=current_date,
            strategy_name=strategy_name,
            stop_loss=stop_loss,
            take_profit=take_profit,
            trailing_stop_pct=trailing,
        )
    elif signal.action == "SELL":
        if portfolio.has_position(symbol):
            pos = portfolio.get_position(symbol)
            if pos.side == "long":
                portfolio.sell(symbol, current_price, current_date)
            else:
                portfolio.cover_short(symbol, current_price, current_date)
        else:
            # SELL with no position -> open short if strategy supports it
            style = getattr(signal, "style", "")
            if style in ("short", "bearish") or getattr(signal, "setup", "").lower().find("bear") >= 0:
                portfolio.sell_short(
                    symbol=symbol,
                    price=current_price,
                    date=current_date,
                    strategy_name=strategy_name,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    trailing_stop_pct=trailing,
                )


def _fetch_benchmark_prices(benchmark_symbol: str, period: str,
                             interval: str, target_length: int) -> list | None:
    """Fetch benchmark close prices for comparison."""
    try:
        bench_candles = fetch_market_data(benchmark_symbol, period=period, interval=interval)
        if bench_candles and len(bench_candles) >= MIN_CANDLES:
            # Return closes starting from MIN_CANDLES offset (matching strategy start)
            return [c.close for c in bench_candles[MIN_CANDLES:]]
    except Exception as e:
        logger.warning("Could not fetch benchmark %s: %s", benchmark_symbol, e)
    return None


# ─── Multi-Strategy / Multi-Symbol Backtest ──────────────────────────

def run_multi_backtest(strategies: list, symbols: list,
                       **kwargs) -> list:
    """
    Run backtests for multiple strategies across multiple symbols.

    Args:
        strategies: List of Strategy instances.
        symbols: List of ticker symbols.
        **kwargs: BacktestConfig parameters.

    Returns:
        List of BacktestResult (one per strategy-symbol combination).
        Failed/skipped combinations are omitted.
    """
    results = []

    for strategy in strategies:
        for symbol in symbols:
            logger.info("Backtesting %s on %s...", strategy.name, symbol)
            try:
                result = run_backtest(strategy, symbol, **kwargs)
                if result is not None:
                    results.append(result)
                else:
                    logger.warning("Skipped %s / %s: insufficient data",
                                    strategy.name, symbol)
            except Exception as e:
                logger.error("Error backtesting %s on %s: %s",
                              strategy.name, symbol, e)

    # Sort by total return descending
    results.sort(key=lambda r: r.total_return_pct, reverse=True)

    if results:
        logger.info("Multi-backtest complete: %d results. Best: %s on %s (%.1f%%)",
                      len(results), results[0].strategy_name,
                      results[0].symbol, results[0].total_return_pct)

    return results


# ─── Walk-Forward Backtesting ────────────────────────────────────────

def run_walkforward(strategy, symbol: str, train_months: int = 12,
                    test_months: int = 3, **kwargs) -> WalkforwardResult | None:
    """
    Walk-forward backtesting: split history into rolling windows,
    train on in-sample, test on out-of-sample, slide forward.

    This validates that a strategy works on unseen data by testing
    each window independently.

    Args:
        strategy: Strategy instance.
        symbol: Ticker symbol.
        train_months: In-sample training window in months.
        test_months: Out-of-sample testing window in months.
        **kwargs: Additional BacktestConfig parameters.

    Returns:
        WalkforwardResult or None if insufficient data.
    """
    # Fetch enough data for all windows
    total_months = train_months + test_months
    # Request extra data to ensure coverage
    years_needed = max(2, (total_months * 3) / 12)
    period = f"{int(years_needed)}y"

    candles = fetch_market_data(symbol, period=period, interval="1d")
    if candles is None or len(candles) < MIN_CANDLES + 60:
        logger.warning("Insufficient data for walk-forward on %s", symbol)
        return None

    # Estimate trading days per month (~21)
    days_per_month = 21
    train_days = train_months * days_per_month
    test_days = test_months * days_per_month
    window_size = train_days + test_days

    # Build default config
    config_kwargs = {k: v for k, v in kwargs.items()
                     if k in BacktestConfig.__dataclass_fields__}
    config = BacktestConfig(**config_kwargs)

    windows = []
    start_idx = MIN_CANDLES  # need lookback for indicators

    while start_idx + window_size <= len(candles):
        train_start = start_idx
        train_end = start_idx + train_days
        test_start = train_end
        test_end = min(test_start + test_days, len(candles))

        if test_end - test_start < days_per_month:
            break  # not enough test data

        # Run in-sample backtest
        in_sample_candles = candles[:train_end]
        is_result = _run_on_candle_slice(strategy, symbol, in_sample_candles,
                                          train_start, train_end, config)

        # Run out-of-sample backtest
        # Include lookback candles for indicator computation
        oos_candles = candles[:test_end]
        oos_result = _run_on_candle_slice(strategy, symbol, oos_candles,
                                           test_start, test_end, config)

        wf_window = WalkforwardWindow(
            train_start=candles[train_start].date if train_start < len(candles) else "",
            train_end=candles[min(train_end - 1, len(candles) - 1)].date,
            test_start=candles[test_start].date if test_start < len(candles) else "",
            test_end=candles[min(test_end - 1, len(candles) - 1)].date,
            in_sample_return_pct=is_result["return_pct"],
            out_of_sample_return_pct=oos_result["return_pct"],
            in_sample_sharpe=is_result["sharpe"],
            out_of_sample_sharpe=oos_result["sharpe"],
            num_trades=oos_result["num_trades"],
        )
        windows.append(wf_window)

        # Slide forward by test period
        start_idx += test_days

    if not windows:
        logger.warning("No walk-forward windows could be generated for %s", symbol)
        return None

    # Aggregate results
    is_returns = [w.in_sample_return_pct for w in windows]
    oos_returns = [w.out_of_sample_return_pct for w in windows]
    is_sharpes = [w.in_sample_sharpe for w in windows]
    oos_sharpes = [w.out_of_sample_sharpe for w in windows]

    profitable_oos = sum(1 for r in oos_returns if r > 0)

    # Compound OOS returns
    total_oos = 1.0
    for r in oos_returns:
        total_oos *= (1 + r / 100)
    total_oos_pct = (total_oos - 1) * 100

    result = WalkforwardResult(
        strategy_name=strategy.name,
        symbol=symbol,
        train_months=train_months,
        test_months=test_months,
        windows=windows,
        avg_in_sample_return=float(np.mean(is_returns)),
        avg_out_of_sample_return=float(np.mean(oos_returns)),
        avg_in_sample_sharpe=float(np.mean(is_sharpes)),
        avg_out_of_sample_sharpe=float(np.mean(oos_sharpes)),
        total_out_of_sample_return=total_oos_pct,
        consistency_ratio=(profitable_oos / len(windows)) * 100 if windows else 0,
    )

    logger.info("Walk-forward complete for %s on %s: %d windows, "
                 "OOS return %.1f%%, consistency %.0f%%",
                 strategy.name, symbol, len(windows),
                 total_oos_pct, result.consistency_ratio)

    return result


def _run_on_candle_slice(strategy, symbol: str, all_candles: list,
                          start_idx: int, end_idx: int,
                          config: BacktestConfig) -> dict:
    """
    Run a strategy on a specific slice of candle data.

    Used internally by walk-forward to test on sub-windows.

    Returns:
        Dict with return_pct, sharpe, num_trades
    """
    portfolio = config.to_portfolio()

    for i in range(start_idx, end_idx):
        lookback_start = max(0, i - MIN_CANDLES)
        window = all_candles[lookback_start:i + 1]

        if len(window) < 26:  # minimum for indicators
            continue

        indicators = compute_indicators(window)
        snapshot = MarketSnapshot(
            symbol=symbol,
            timeframe=config.interval,
            candles=window,
            indicators=indicators,
        )

        current_candle = all_candles[i]
        current_price = current_candle.close
        current_date = current_candle.date

        # Check stops
        if config.use_stops:
            candle_data = {
                symbol: {"high": current_candle.high, "low": current_candle.low}
            }
            portfolio.check_stops(
                {symbol: current_price},
                current_date,
                candle_data=candle_data,
            )

        signal = strategy.analyze(snapshot)
        if signal:
            _process_signal(portfolio, signal, symbol, current_price,
                            current_date, strategy.name, config)

        portfolio.snapshot_equity(current_date, {symbol: current_price})

    # Close remaining positions
    if end_idx > 0 and end_idx <= len(all_candles):
        last_idx = min(end_idx - 1, len(all_candles) - 1)
        last_candle = all_candles[last_idx]
        portfolio.close_all_positions(
            {symbol: last_candle.close},
            last_candle.date,
            exit_reason="window_end",
        )

    # Compute basic metrics
    equities = portfolio.get_equity_series()
    if equities and len(equities) >= 2 and equities[0] > 0:
        return_pct = ((equities[-1] - equities[0]) / equities[0]) * 100
        daily_rets = np.diff(equities) / np.array(equities[:-1])
        daily_rets = daily_rets[np.isfinite(daily_rets)]
        std = float(np.std(daily_rets, ddof=1)) if len(daily_rets) > 1 else 0
        sharpe = (float(np.mean(daily_rets)) / std * np.sqrt(252)) if std > 1e-10 else 0.0
    else:
        return_pct = 0.0
        sharpe = 0.0

    return {
        "return_pct": return_pct,
        "sharpe": sharpe,
        "num_trades": len(portfolio.trades),
    }


# ─── Monte Carlo Simulation ─────────────────────────────────────────

def run_monte_carlo(trades: list, num_simulations: int = 1000,
                    initial_cash: float = 10000.0) -> MonteCarloResult:
    """
    Monte Carlo simulation: shuffle the order of historical trades
    to estimate the range of possible outcomes.

    This helps answer: "Was my result lucky, or is the strategy robust?"

    Args:
        trades: List of Trade objects from a completed backtest.
        num_simulations: Number of random shuffles to run.
        initial_cash: Starting capital for each simulation.

    Returns:
        MonteCarloResult with distribution statistics.
    """
    if not trades:
        return MonteCarloResult(num_simulations=num_simulations)

    # Extract P&L values (absolute dollars)
    pnl_values = np.array([t.pnl for t in trades], dtype=float)
    num_trades = len(pnl_values)

    final_equities = np.zeros(num_simulations)
    max_drawdowns = np.zeros(num_simulations)
    sample_paths = []

    rng = np.random.default_rng(seed=42)

    for sim in range(num_simulations):
        # Shuffle trade order
        shuffled = rng.permutation(pnl_values)

        # Build equity curve
        equity = np.zeros(num_trades + 1)
        equity[0] = initial_cash
        for j in range(num_trades):
            equity[j + 1] = equity[j] + shuffled[j]

        final_equities[sim] = equity[-1]

        # Compute max drawdown for this path
        peak = equity[0]
        max_dd = 0.0
        for val in equity:
            if val > peak:
                peak = val
            dd = ((peak - val) / peak) * 100 if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd
        max_drawdowns[sim] = max_dd

        # Save a few sample paths for visualization
        if sim < 20:
            sample_paths.append(equity.tolist())

    # Compute returns
    returns = ((final_equities - initial_cash) / initial_cash) * 100

    profitable = np.sum(final_equities > initial_cash)

    result = MonteCarloResult(
        num_simulations=num_simulations,
        median_return_pct=float(np.median(returns)),
        mean_return_pct=float(np.mean(returns)),
        percentile_5=float(np.percentile(returns, 5)),
        percentile_25=float(np.percentile(returns, 25)),
        percentile_75=float(np.percentile(returns, 75)),
        percentile_95=float(np.percentile(returns, 95)),
        worst_return_pct=float(np.min(returns)),
        best_return_pct=float(np.max(returns)),
        probability_of_profit=(float(profitable) / num_simulations) * 100,
        median_max_drawdown=float(np.median(max_drawdowns)),
        equity_paths=sample_paths,
    )

    logger.info("Monte Carlo (%d sims): median return %.1f%%, "
                 "P(profit) %.0f%%, median max DD %.1f%%",
                 num_simulations, result.median_return_pct,
                 result.probability_of_profit, result.median_max_drawdown)

    return result
