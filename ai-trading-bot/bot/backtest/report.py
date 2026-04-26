"""
Backtest Reporting - Professional-grade performance analysis.

Computes standard return metrics, risk metrics, trade statistics,
monthly breakdowns, rolling Sharpe, benchmark comparison, and
generates human-readable summaries for Discord/Telegram.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

TRADING_DAYS_PER_YEAR = 252


# ─── Data Classes ────────────────────────────────────────────────────

@dataclass
class MonteCarloResult:
    """Results from a Monte Carlo simulation of trade sequences."""
    num_simulations: int = 0
    median_return_pct: float = 0.0
    mean_return_pct: float = 0.0
    percentile_5: float = 0.0
    percentile_25: float = 0.0
    percentile_75: float = 0.0
    percentile_95: float = 0.0
    worst_return_pct: float = 0.0
    best_return_pct: float = 0.0
    probability_of_profit: float = 0.0
    median_max_drawdown: float = 0.0
    equity_paths: list = field(default_factory=list)  # sampled paths for plotting

    def to_dict(self) -> dict:
        return {
            "num_simulations": self.num_simulations,
            "median_return_pct": round(self.median_return_pct, 2),
            "mean_return_pct": round(self.mean_return_pct, 2),
            "percentile_5": round(self.percentile_5, 2),
            "percentile_25": round(self.percentile_25, 2),
            "percentile_75": round(self.percentile_75, 2),
            "percentile_95": round(self.percentile_95, 2),
            "worst_return_pct": round(self.worst_return_pct, 2),
            "best_return_pct": round(self.best_return_pct, 2),
            "probability_of_profit": round(self.probability_of_profit, 2),
            "median_max_drawdown": round(self.median_max_drawdown, 2),
        }

    def summary_text(self) -> str:
        lines = [
            "--- Monte Carlo Simulation ---",
            f"Simulations: {self.num_simulations}",
            f"Median Return: {self.median_return_pct:.1f}%",
            f"5th - 95th Percentile: {self.percentile_5:.1f}% to {self.percentile_95:.1f}%",
            f"Probability of Profit: {self.probability_of_profit:.1f}%",
            f"Worst Case: {self.worst_return_pct:.1f}%",
            f"Best Case: {self.best_return_pct:.1f}%",
            f"Median Max Drawdown: {self.median_max_drawdown:.1f}%",
        ]
        return "\n".join(lines)


@dataclass
class WalkforwardWindow:
    """Results for a single walk-forward window."""
    train_start: str = ""
    train_end: str = ""
    test_start: str = ""
    test_end: str = ""
    in_sample_return_pct: float = 0.0
    out_of_sample_return_pct: float = 0.0
    in_sample_sharpe: float = 0.0
    out_of_sample_sharpe: float = 0.0
    num_trades: int = 0


@dataclass
class WalkforwardResult:
    """Aggregated walk-forward backtesting results."""
    strategy_name: str = ""
    symbol: str = ""
    train_months: int = 0
    test_months: int = 0
    windows: list = field(default_factory=list)  # list[WalkforwardWindow]
    avg_in_sample_return: float = 0.0
    avg_out_of_sample_return: float = 0.0
    avg_in_sample_sharpe: float = 0.0
    avg_out_of_sample_sharpe: float = 0.0
    total_out_of_sample_return: float = 0.0
    consistency_ratio: float = 0.0  # % of windows where OOS was profitable

    def to_dict(self) -> dict:
        return {
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "train_months": self.train_months,
            "test_months": self.test_months,
            "num_windows": len(self.windows),
            "avg_in_sample_return": round(self.avg_in_sample_return, 2),
            "avg_out_of_sample_return": round(self.avg_out_of_sample_return, 2),
            "avg_in_sample_sharpe": round(self.avg_in_sample_sharpe, 2),
            "avg_out_of_sample_sharpe": round(self.avg_out_of_sample_sharpe, 2),
            "total_out_of_sample_return": round(self.total_out_of_sample_return, 2),
            "consistency_ratio": round(self.consistency_ratio, 2),
            "windows": [
                {
                    "train": f"{w.train_start} to {w.train_end}",
                    "test": f"{w.test_start} to {w.test_end}",
                    "is_return": round(w.in_sample_return_pct, 2),
                    "oos_return": round(w.out_of_sample_return_pct, 2),
                    "trades": w.num_trades,
                }
                for w in self.windows
            ],
        }

    def summary_text(self) -> str:
        lines = [
            f"--- Walk-Forward: {self.strategy_name} on {self.symbol} ---",
            f"Windows: {len(self.windows)} ({self.train_months}m train / {self.test_months}m test)",
            f"Avg In-Sample Return: {self.avg_in_sample_return:.1f}%",
            f"Avg Out-of-Sample Return: {self.avg_out_of_sample_return:.1f}%",
            f"Total OOS Return: {self.total_out_of_sample_return:.1f}%",
            f"Consistency: {self.consistency_ratio:.0f}% of windows profitable OOS",
            f"In-Sample Sharpe: {self.avg_in_sample_sharpe:.2f}",
            f"Out-of-Sample Sharpe: {self.avg_out_of_sample_sharpe:.2f}",
        ]
        return "\n".join(lines)


@dataclass
class BacktestResult:
    """Complete backtest results with all metrics."""
    # Identity
    symbol: str = ""
    strategy_name: str = ""
    period: str = ""
    initial_cash: float = 10000.0

    # Return metrics
    final_equity: float = 0.0
    total_return_pct: float = 0.0
    cagr: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0

    # Risk metrics
    max_drawdown_pct: float = 0.0
    max_drawdown_duration_days: int = 0
    var_95: float = 0.0        # Value at Risk (95%)
    expected_shortfall: float = 0.0  # CVaR / Expected Shortfall

    # Trade metrics
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    avg_win_pct: float = 0.0
    avg_loss_pct: float = 0.0
    avg_trade_pnl: float = 0.0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    expectancy: float = 0.0  # expected $ per trade
    avg_holding_days: float = 0.0
    best_trade_pct: float = 0.0
    worst_trade_pct: float = 0.0
    total_commission: float = 0.0
    total_slippage: float = 0.0

    # Benchmark comparison
    benchmark_return_pct: float = 0.0
    alpha: float = 0.0
    beta: float = 0.0
    information_ratio: float = 0.0

    # Monthly returns
    monthly_returns: dict = field(default_factory=dict)  # "YYYY-MM" -> return_pct
    rolling_sharpe: list = field(default_factory=list)    # list of (date, sharpe)

    # Raw data
    equity_curve: list = field(default_factory=list)
    trades: list = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize to dictionary (excludes large raw data by default)."""
        return {
            "symbol": self.symbol,
            "strategy": self.strategy_name,
            "period": self.period,
            "initial_cash": self.initial_cash,
            "final_equity": round(self.final_equity, 2),
            "total_return_pct": round(self.total_return_pct, 2),
            "cagr": round(self.cagr, 2),
            "sharpe_ratio": round(self.sharpe_ratio, 2),
            "sortino_ratio": round(self.sortino_ratio, 2),
            "calmar_ratio": round(self.calmar_ratio, 2),
            "max_drawdown_pct": round(self.max_drawdown_pct, 2),
            "max_drawdown_duration_days": self.max_drawdown_duration_days,
            "var_95": round(self.var_95, 2),
            "expected_shortfall": round(self.expected_shortfall, 2),
            "total_trades": self.total_trades,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": round(self.win_rate, 1),
            "profit_factor": round(self.profit_factor, 2),
            "avg_win_pct": round(self.avg_win_pct, 2),
            "avg_loss_pct": round(self.avg_loss_pct, 2),
            "avg_trade_pnl": round(self.avg_trade_pnl, 2),
            "max_consecutive_wins": self.max_consecutive_wins,
            "max_consecutive_losses": self.max_consecutive_losses,
            "expectancy": round(self.expectancy, 2),
            "avg_holding_days": round(self.avg_holding_days, 1),
            "best_trade_pct": round(self.best_trade_pct, 2),
            "worst_trade_pct": round(self.worst_trade_pct, 2),
            "total_commission": round(self.total_commission, 2),
            "total_slippage": round(self.total_slippage, 2),
            "benchmark_return_pct": round(self.benchmark_return_pct, 2),
            "alpha": round(self.alpha, 2),
            "beta": round(self.beta, 2),
            "information_ratio": round(self.information_ratio, 2),
            "monthly_returns": {
                k: round(v, 2) for k, v in self.monthly_returns.items()
            },
            "equity_curve": [
                {"date": e.date, "equity": round(e.equity, 2),
                 "drawdown": round(e.drawdown, 2)}
                for e in self.equity_curve
            ] if self.equity_curve and hasattr(self.equity_curve[0], "date") else self.equity_curve,
            "trades": [
                {
                    "symbol": t.symbol,
                    "side": t.side,
                    "entry_date": t.entry_date,
                    "exit_date": t.exit_date,
                    "entry_price": round(t.entry_price, 2),
                    "exit_price": round(t.exit_price, 2),
                    "pnl": round(t.pnl, 2),
                    "pnl_pct": round(t.pnl_pct, 2),
                    "exit_reason": t.exit_reason,
                }
                for t in self.trades
            ] if self.trades and hasattr(self.trades[0], "symbol") else self.trades,
        }

    def summary_text(self) -> str:
        """Generate human-readable summary for Discord/Telegram."""
        lines = [
            f"=== Backtest: {self.strategy_name} on {self.symbol} ===",
            "",
            "-- Returns --",
            f"  Total Return: {self.total_return_pct:+.2f}%",
            f"  CAGR: {self.cagr:+.2f}%",
            f"  Final Equity: ${self.final_equity:,.2f}",
            "",
            "-- Risk --",
            f"  Sharpe Ratio: {self.sharpe_ratio:.2f}",
            f"  Sortino Ratio: {self.sortino_ratio:.2f}",
            f"  Calmar Ratio: {self.calmar_ratio:.2f}",
            f"  Max Drawdown: {self.max_drawdown_pct:.2f}%",
            f"  Max DD Duration: {self.max_drawdown_duration_days} days",
            f"  VaR (95%): {self.var_95:.2f}%",
            f"  Expected Shortfall: {self.expected_shortfall:.2f}%",
            "",
            "-- Trades --",
            f"  Total Trades: {self.total_trades}",
            f"  Win Rate: {self.win_rate:.1f}%",
            f"  Profit Factor: {self.profit_factor:.2f}",
            f"  Avg Win: {self.avg_win_pct:+.2f}%",
            f"  Avg Loss: {self.avg_loss_pct:+.2f}%",
            f"  Expectancy: ${self.expectancy:+.2f}/trade",
            f"  Best Trade: {self.best_trade_pct:+.2f}%",
            f"  Worst Trade: {self.worst_trade_pct:+.2f}%",
            f"  Max Consec Wins: {self.max_consecutive_wins}",
            f"  Max Consec Losses: {self.max_consecutive_losses}",
            f"  Avg Holding: {self.avg_holding_days:.1f} days",
            "",
            "-- Costs --",
            f"  Total Commission: ${self.total_commission:.2f}",
            f"  Total Slippage: ${self.total_slippage:.2f}",
        ]

        if self.benchmark_return_pct != 0:
            lines.extend([
                "",
                "-- vs Benchmark (SPY B&H) --",
                f"  Benchmark Return: {self.benchmark_return_pct:+.2f}%",
                f"  Alpha: {self.alpha:+.2f}%",
                f"  Beta: {self.beta:.2f}",
                f"  Information Ratio: {self.information_ratio:.2f}",
            ])

        if self.monthly_returns:
            lines.extend(["", "-- Monthly Returns --"])
            # Group by year
            years = sorted(set(k[:4] for k in self.monthly_returns))
            months_header = "     " + " ".join(f"{m:>6}" for m in
                                                ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                                                 "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
            lines.append(months_header)
            for year in years:
                row_values = []
                for m in range(1, 13):
                    key = f"{year}-{m:02d}"
                    val = self.monthly_returns.get(key)
                    if val is not None:
                        row_values.append(f"{val:+5.1f}%")
                    else:
                        row_values.append("    --")
                lines.append(f"  {year} " + " ".join(row_values))

        return "\n".join(lines)


# ─── Report Generation ──────────────────────────────────────────────

def generate_report(portfolio, symbol: str, strategy_name: str,
                    benchmark_prices: Optional[list] = None,
                    period: str = "") -> BacktestResult:
    """
    Generate a comprehensive backtest report from a Portfolio.

    Args:
        portfolio: The Portfolio instance after backtesting.
        symbol: Primary symbol tested.
        strategy_name: Name of the strategy.
        benchmark_prices: Optional list of benchmark (SPY) close prices
                          aligned with the equity curve dates.
        period: Description of the test period.

    Returns:
        BacktestResult with all metrics computed.
    """
    result = BacktestResult(
        symbol=symbol,
        strategy_name=strategy_name,
        period=period,
        initial_cash=portfolio.initial_cash,
        equity_curve=portfolio.equity_curve,
        trades=portfolio.trades,
    )

    if not portfolio.trades and not portfolio.equity_curve:
        result.total_trades = 0
        return result

    # ── Equity curve analysis ──────────────────────────────────────
    equities = portfolio.get_equity_series()
    if not equities:
        equities = [portfolio.initial_cash]

    result.final_equity = equities[-1]
    result.total_return_pct = _total_return_pct(equities)

    # CAGR
    num_days = len(equities)
    years = num_days / TRADING_DAYS_PER_YEAR
    if years > 0 and equities[0] > 0 and equities[-1] > 0:
        result.cagr = ((equities[-1] / equities[0]) ** (1 / years) - 1) * 100
    else:
        result.cagr = 0.0

    # Daily returns
    daily_returns = _daily_returns(equities)

    # Sharpe ratio
    result.sharpe_ratio = _sharpe_ratio(daily_returns)

    # Sortino ratio
    result.sortino_ratio = _sortino_ratio(daily_returns)

    # Max drawdown and duration
    result.max_drawdown_pct, result.max_drawdown_duration_days = _max_drawdown(equities)

    # Calmar ratio
    if result.max_drawdown_pct > 0:
        result.calmar_ratio = result.cagr / result.max_drawdown_pct
    else:
        result.calmar_ratio = 0.0

    # VaR and Expected Shortfall
    result.var_95, result.expected_shortfall = _var_and_es(daily_returns)

    # ── Trade analysis ─────────────────────────────────────────────
    trades = portfolio.trades
    result.total_trades = len(trades)

    if trades:
        winning = [t for t in trades if t.pnl > 0]
        losing = [t for t in trades if t.pnl <= 0]

        result.wins = len(winning)
        result.losses = len(losing)
        result.win_rate = (len(winning) / len(trades)) * 100 if trades else 0

        # Profit factor
        gross_profit = sum(t.pnl for t in winning) if winning else 0.0
        gross_loss = abs(sum(t.pnl for t in losing)) if losing else 0.0
        result.profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (
            float("inf") if gross_profit > 0 else 0.0
        )

        # Average win/loss
        result.avg_win_pct = float(np.mean([t.pnl_pct for t in winning])) if winning else 0.0
        result.avg_loss_pct = float(np.mean([t.pnl_pct for t in losing])) if losing else 0.0
        result.avg_trade_pnl = float(np.mean([t.pnl for t in trades]))

        # Expectancy
        if trades:
            win_rate_frac = len(winning) / len(trades)
            avg_win = float(np.mean([t.pnl for t in winning])) if winning else 0.0
            avg_loss = float(np.mean([t.pnl for t in losing])) if losing else 0.0
            result.expectancy = (win_rate_frac * avg_win) + ((1 - win_rate_frac) * avg_loss)

        # Consecutive wins/losses
        result.max_consecutive_wins, result.max_consecutive_losses = _consecutive_streaks(trades)

        # Best / worst trade
        pnl_pcts = [t.pnl_pct for t in trades]
        result.best_trade_pct = max(pnl_pcts)
        result.worst_trade_pct = min(pnl_pcts)

        # Average holding period
        holding_days = []
        for t in trades:
            try:
                entry_dt = _parse_date(t.entry_date)
                exit_dt = _parse_date(t.exit_date)
                if entry_dt and exit_dt:
                    holding_days.append((exit_dt - entry_dt).days)
            except Exception:
                pass
        result.avg_holding_days = float(np.mean(holding_days)) if holding_days else 0.0

        # Total costs
        result.total_commission = sum(t.commission for t in trades)
        result.total_slippage = sum(t.slippage_cost for t in trades)

    # ── Monthly returns ────────────────────────────────────────────
    result.monthly_returns = _compute_monthly_returns(portfolio.equity_curve)

    # ── Rolling Sharpe ─────────────────────────────────────────────
    result.rolling_sharpe = _compute_rolling_sharpe(equities,
                                                     portfolio.get_dates_series(),
                                                     window=30)

    # ── Benchmark comparison ───────────────────────────────────────
    if benchmark_prices and len(benchmark_prices) >= 2:
        result.benchmark_return_pct = (
            (benchmark_prices[-1] - benchmark_prices[0]) / benchmark_prices[0]
        ) * 100

        bench_returns = _daily_returns(benchmark_prices)

        # Align lengths
        min_len = min(len(daily_returns), len(bench_returns))
        if min_len > 1:
            strat_r = np.array(daily_returns[:min_len])
            bench_r = np.array(bench_returns[:min_len])

            # Beta
            cov_matrix = np.cov(strat_r, bench_r)
            bench_var = np.var(bench_r)
            result.beta = float(cov_matrix[0, 1] / bench_var) if bench_var > 0 else 0.0

            # Alpha (annualized)
            strat_ann = float(np.mean(strat_r)) * TRADING_DAYS_PER_YEAR
            bench_ann = float(np.mean(bench_r)) * TRADING_DAYS_PER_YEAR
            result.alpha = (strat_ann - result.beta * bench_ann) * 100

            # Information ratio
            active_returns = strat_r - bench_r
            tracking_error = float(np.std(active_returns)) * np.sqrt(TRADING_DAYS_PER_YEAR)
            if tracking_error > 0:
                result.information_ratio = float(
                    np.mean(active_returns) * TRADING_DAYS_PER_YEAR / tracking_error
                )

    return result


# ─── Metric Computation Helpers ──────────────────────────────────────

def _total_return_pct(equities: list) -> float:
    if not equities or equities[0] == 0:
        return 0.0
    return ((equities[-1] - equities[0]) / equities[0]) * 100


def _daily_returns(values: list) -> list:
    """Compute daily returns from a value series."""
    if len(values) < 2:
        return []
    arr = np.array(values, dtype=float)
    # Avoid division by zero
    prev = arr[:-1]
    prev = np.where(prev == 0, 1e-10, prev)
    returns = (arr[1:] - prev) / prev
    return returns.tolist()


def _sharpe_ratio(daily_returns: list, risk_free_annual: float = 0.0) -> float:
    """Annualized Sharpe ratio from daily returns."""
    if len(daily_returns) < 2:
        return 0.0
    arr = np.array(daily_returns)
    rf_daily = risk_free_annual / TRADING_DAYS_PER_YEAR
    excess = arr - rf_daily
    mean_excess = float(np.mean(excess))
    std = float(np.std(excess, ddof=1))
    if std < 1e-10:
        return 0.0
    return (mean_excess / std) * np.sqrt(TRADING_DAYS_PER_YEAR)


def _sortino_ratio(daily_returns: list, risk_free_annual: float = 0.0) -> float:
    """Annualized Sortino ratio (uses downside deviation only)."""
    if len(daily_returns) < 2:
        return 0.0
    arr = np.array(daily_returns)
    rf_daily = risk_free_annual / TRADING_DAYS_PER_YEAR
    excess = arr - rf_daily
    mean_excess = float(np.mean(excess))
    downside = excess[excess < 0]
    if len(downside) < 1:
        return 0.0 if mean_excess <= 0 else float("inf")
    downside_std = float(np.sqrt(np.mean(downside ** 2)))
    if downside_std < 1e-10:
        return 0.0
    return (mean_excess / downside_std) * np.sqrt(TRADING_DAYS_PER_YEAR)


def _max_drawdown(equities: list) -> tuple:
    """
    Compute max drawdown percentage and max drawdown duration in days.

    Returns:
        (max_drawdown_pct, max_drawdown_duration_days)
    """
    if len(equities) < 2:
        return 0.0, 0

    arr = np.array(equities, dtype=float)
    peak = arr[0]
    max_dd = 0.0
    max_dd_duration = 0
    current_dd_start = 0
    in_drawdown = False

    for i in range(len(arr)):
        if arr[i] > peak:
            if in_drawdown:
                duration = i - current_dd_start
                if duration > max_dd_duration:
                    max_dd_duration = duration
                in_drawdown = False
            peak = arr[i]
        else:
            dd = ((peak - arr[i]) / peak) * 100
            if dd > max_dd:
                max_dd = dd
            if not in_drawdown:
                current_dd_start = i
                in_drawdown = True

    # Check if still in drawdown at end
    if in_drawdown:
        duration = len(arr) - current_dd_start
        if duration > max_dd_duration:
            max_dd_duration = duration

    return max_dd, max_dd_duration


def _var_and_es(daily_returns: list, confidence: float = 0.95) -> tuple:
    """
    Compute historical Value at Risk and Expected Shortfall.

    Returns:
        (var_pct, es_pct) - both as percentages (e.g., -2.5 means a 2.5% loss)
    """
    if len(daily_returns) < 10:
        return 0.0, 0.0

    arr = np.array(daily_returns) * 100  # convert to percentages
    cutoff = np.percentile(arr, (1 - confidence) * 100)
    var_value = float(cutoff)

    # Expected Shortfall: mean of returns below VaR
    tail = arr[arr <= cutoff]
    es_value = float(np.mean(tail)) if len(tail) > 0 else var_value

    return var_value, es_value


def _consecutive_streaks(trades: list) -> tuple:
    """
    Compute max consecutive wins and losses.

    Returns:
        (max_consecutive_wins, max_consecutive_losses)
    """
    if not trades:
        return 0, 0

    max_wins = 0
    max_losses = 0
    current_wins = 0
    current_losses = 0

    for t in trades:
        if t.pnl > 0:
            current_wins += 1
            current_losses = 0
            if current_wins > max_wins:
                max_wins = current_wins
        else:
            current_losses += 1
            current_wins = 0
            if current_losses > max_losses:
                max_losses = current_losses

    return max_wins, max_losses


def _compute_monthly_returns(equity_curve: list) -> dict:
    """
    Compute month-by-month returns from equity curve.

    Returns:
        Dict of "YYYY-MM" -> return percentage
    """
    if not equity_curve or len(equity_curve) < 2:
        return {}

    monthly = {}
    # Group equity points by month
    month_first = {}
    month_last = {}

    for point in equity_curve:
        date_str = point.date if hasattr(point, "date") else point.get("date", "")
        equity = point.equity if hasattr(point, "equity") else point.get("equity", 0)

        if not date_str:
            continue

        # Extract YYYY-MM
        month_key = date_str[:7]  # works for "YYYY-MM-DD" format

        if month_key not in month_first:
            month_first[month_key] = equity
        month_last[month_key] = equity

    # Compute returns
    sorted_months = sorted(month_first.keys())
    prev_equity = None
    for month in sorted_months:
        if prev_equity is not None and prev_equity > 0:
            ret = ((month_last[month] - prev_equity) / prev_equity) * 100
            monthly[month] = ret
        else:
            # First month: return from start of month to end of month
            if month_first[month] > 0:
                ret = ((month_last[month] - month_first[month]) / month_first[month]) * 100
                monthly[month] = ret
        prev_equity = month_last[month]

    return monthly


def _compute_rolling_sharpe(equities: list, dates: list, window: int = 30) -> list:
    """
    Compute rolling Sharpe ratio over a window of trading days.

    Returns:
        List of (date, sharpe) tuples
    """
    if len(equities) < window + 1:
        return []

    result = []
    arr = np.array(equities, dtype=float)

    for i in range(window, len(arr)):
        window_eq = arr[i - window:i + 1]
        prev = window_eq[:-1]
        prev = np.where(prev == 0, 1e-10, prev)
        rets = (window_eq[1:] - prev) / prev
        std = float(np.std(rets, ddof=1))
        if std > 1e-10:
            sharpe = (float(np.mean(rets)) / std) * np.sqrt(TRADING_DAYS_PER_YEAR)
        else:
            sharpe = 0.0

        date_str = dates[i] if i < len(dates) else ""
        result.append((date_str, round(sharpe, 2)))

    return result


def _parse_date(date_str: str) -> Optional[datetime]:
    """Parse a date string, trying common formats."""
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(date_str[:19], fmt)
        except ValueError:
            continue
    return None
