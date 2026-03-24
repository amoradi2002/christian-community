import json
from flask import Blueprint, render_template, request, flash, redirect, url_for
from bot.strategies.registry import StrategyRegistry
from bot.backtest.engine import run_backtest

backtest_bp = Blueprint("backtest", __name__)


@backtest_bp.route("/backtest", methods=["GET", "POST"])
def backtest_page():
    registry = StrategyRegistry()
    registry.load_all()
    strategies = registry.get_all()
    report = None

    if request.method == "POST":
        strategy_name = request.form.get("strategy")
        symbol = request.form.get("symbol", "SPY").upper()
        period = request.form.get("period", "2y")

        strategy = registry.get_by_name(strategy_name)
        if not strategy:
            flash(f"Strategy '{strategy_name}' not found.", "error")
            return redirect(url_for("backtest.backtest_page"))

        report = run_backtest(strategy, symbol, period=period)
        if report and "equity_curve" in report:
            # Limit equity curve for JSON rendering
            curve = report["equity_curve"]
            if len(curve) > 200:
                step = len(curve) // 200
                report["equity_curve_chart"] = curve[::step]
            else:
                report["equity_curve_chart"] = curve

    return render_template(
        "backtest.html",
        strategies=strategies,
        report=report,
    )
