from flask import Blueprint, jsonify, request
from bot.alerts.manager import AlertManager
from bot.strategies.store import list_strategies
from bot.engine.performance import get_strategy_stats, get_open_positions
from bot.config.settings import CONFIG

api_bp = Blueprint("api", __name__)


@api_bp.route("/signals")
def get_signals():
    alert_mgr = AlertManager()
    alerts = alert_mgr.get_alert_history(limit=20)
    return jsonify(alerts)


@api_bp.route("/strategies")
def get_strategies():
    strategies = list_strategies(active_only=False)
    return jsonify(strategies)


@api_bp.route("/performance")
def get_performance():
    stats = get_strategy_stats()
    positions = get_open_positions()
    return jsonify({"stats": stats, "open_positions": positions})


@api_bp.route("/prices")
def get_prices():
    """Get real-time prices for all watchlist symbols."""
    from bot.data.fetcher import fetch_realtime_price
    watchlist = CONFIG.get("bot", {}).get("watchlist", [])
    symbol = request.args.get("symbol")

    if symbol:
        price = fetch_realtime_price(symbol.upper())
        return jsonify(price if price else {"error": f"Could not fetch {symbol}"})

    prices = {}
    for sym in watchlist:
        price = fetch_realtime_price(sym)
        if price:
            prices[sym] = price

    return jsonify(prices)


@api_bp.route("/health")
def health():
    return jsonify({"status": "ok"})
