import numpy as np
from bot.backtest.portfolio import Portfolio


def generate_report(portfolio: Portfolio, symbol: str, strategy_name: str) -> dict:
    """Generate a backtest performance report."""
    trades = portfolio.trades
    equity_curve = portfolio.equity_curve

    if not trades:
        return {
            "symbol": symbol,
            "strategy": strategy_name,
            "total_trades": 0,
            "message": "No trades executed",
        }

    wins = [t for t in trades if t.pnl_pct > 0]
    losses = [t for t in trades if t.pnl_pct <= 0]

    pnl_values = [t.pnl_pct for t in trades]
    equities = [e["equity"] for e in equity_curve] if equity_curve else [10000]

    # Calculate metrics
    total_return = (equities[-1] - equities[0]) / equities[0] * 100 if equities[0] != 0 else 0
    win_rate = len(wins) / len(trades) * 100 if trades else 0
    avg_win = np.mean([t.pnl_pct for t in wins]) if wins else 0
    avg_loss = np.mean([t.pnl_pct for t in losses]) if losses else 0

    # Max drawdown
    peak = equities[0]
    max_dd = 0
    for eq in equities:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak * 100
        if dd > max_dd:
            max_dd = dd

    # Sharpe ratio (simplified daily)
    if len(equities) > 1:
        returns = np.diff(equities) / equities[:-1]
        sharpe = np.mean(returns) / (np.std(returns) + 1e-10) * np.sqrt(252)
    else:
        sharpe = 0

    return {
        "symbol": symbol,
        "strategy": strategy_name,
        "total_trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(win_rate, 1),
        "total_return_pct": round(total_return, 2),
        "avg_win_pct": round(float(avg_win), 2),
        "avg_loss_pct": round(float(avg_loss), 2),
        "max_drawdown_pct": round(max_dd, 2),
        "sharpe_ratio": round(float(sharpe), 2),
        "final_equity": round(equities[-1], 2),
        "equity_curve": equity_curve,
        "trades": [
            {
                "entry_date": t.entry_date,
                "exit_date": t.exit_date,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "pnl_pct": t.pnl_pct,
            }
            for t in trades
        ],
    }
