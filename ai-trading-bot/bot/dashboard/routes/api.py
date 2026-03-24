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
    """Get real-time prices - uses Alpaca if configured, falls back to Yahoo."""
    provider = CONFIG.get("data", {}).get("provider", "yfinance")
    watchlist = CONFIG.get("bot", {}).get("watchlist", [])
    symbol = request.args.get("symbol")

    if provider == "alpaca":
        try:
            from bot.data.alpaca_provider import fetch_alpaca_realtime, fetch_alpaca_snapshot
            if symbol:
                price = fetch_alpaca_realtime(symbol.upper())
                return jsonify(price if price else {"error": f"Could not fetch {symbol}"})
            # Batch fetch all watchlist prices (single API call)
            return jsonify(fetch_alpaca_snapshot(watchlist))
        except (ImportError, ValueError):
            pass  # Fall through to yfinance

    from bot.data.fetcher import fetch_realtime_price
    if symbol:
        price = fetch_realtime_price(symbol.upper())
        return jsonify(price if price else {"error": f"Could not fetch {symbol}"})

    prices = {}
    for sym in watchlist:
        price = fetch_realtime_price(sym)
        if price:
            prices[sym] = price
    return jsonify(prices)


# --- Options API ---

@api_bp.route("/options/chain")
def get_options_chain():
    """Get options chain for a symbol. ?symbol=AAPL&expiry_max=2025-04-18"""
    symbol = request.args.get("symbol", "").upper()
    if not symbol:
        return jsonify({"error": "symbol parameter required"}), 400

    try:
        from bot.data.options import get_options_chain
        chain = get_options_chain(
            symbol,
            expiry_min=request.args.get("expiry_min"),
            expiry_max=request.args.get("expiry_max"),
            option_type=request.args.get("type"),
        )
        return jsonify(chain.to_dict())
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Options data unavailable: {e}"}), 500


@api_bp.route("/options/quote")
def get_option_quote():
    """Get quote for specific contract. ?contract=AAPL250321C00170000"""
    contract = request.args.get("contract", "")
    if not contract:
        return jsonify({"error": "contract parameter required"}), 400

    try:
        from bot.data.options import get_option_quote
        quote = get_option_quote(contract)
        return jsonify(quote.to_dict() if quote else {"error": "Quote not found"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- Trading API ---

@api_bp.route("/account")
def get_account():
    """Get Alpaca account info (balance, buying power)."""
    try:
        from bot.engine.trader import get_account_info
        return jsonify(get_account_info())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/positions")
def get_trading_positions():
    """Get all open trading positions from Alpaca."""
    try:
        from bot.engine.trader import get_positions
        return jsonify(get_positions())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/orders", methods=["GET"])
def list_orders():
    """Get recent orders. ?status=open|closed|all"""
    try:
        from bot.engine.trader import get_orders
        status = request.args.get("status", "open")
        return jsonify(get_orders(status=status))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/trade/stock", methods=["POST"])
def trade_stock():
    """
    Place a stock order. JSON body:
    {"symbol": "AAPL", "qty": 10, "side": "buy", "order_type": "limit", "limit_price": 170.50}
    """
    trading_cfg = CONFIG.get("trading", {})
    if not trading_cfg.get("enabled", False):
        return jsonify({"error": "Trading is disabled. Set trading.enabled=true in config.yaml"}), 403

    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    required = ["symbol", "qty", "side"]
    missing = [f for f in required if f not in data]
    if missing:
        return jsonify({"error": f"Missing fields: {missing}"}), 400

    try:
        from bot.engine.trader import place_stock_order
        result = place_stock_order(
            symbol=data["symbol"].upper(),
            qty=float(data["qty"]),
            side=data["side"],
            order_type=data.get("order_type", trading_cfg.get("default_order_type", "market")),
            limit_price=data.get("limit_price"),
            stop_price=data.get("stop_price"),
            time_in_force=data.get("time_in_force", "day"),
        )
        status_code = 200 if result.success else 400
        return jsonify(result.to_dict()), status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/trade/option", methods=["POST"])
def trade_option():
    """
    Place an options order. JSON body:
    {"contract": "AAPL250321C00170000", "qty": 1, "side": "buy", "limit_price": 5.50}
    """
    trading_cfg = CONFIG.get("trading", {})
    if not trading_cfg.get("enabled", False):
        return jsonify({"error": "Trading is disabled. Set trading.enabled=true in config.yaml"}), 403

    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    required = ["contract", "qty", "side"]
    missing = [f for f in required if f not in data]
    if missing:
        return jsonify({"error": f"Missing fields: {missing}"}), 400

    try:
        from bot.engine.trader import place_option_order
        result = place_option_order(
            contract_symbol=data["contract"],
            qty=int(data["qty"]),
            side=data["side"],
            order_type=data.get("order_type", "limit"),
            limit_price=data.get("limit_price"),
            time_in_force=data.get("time_in_force", "day"),
        )
        status_code = 200 if result.success else 400
        return jsonify(result.to_dict()), status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/orders/<order_id>", methods=["DELETE"])
def cancel_order_route(order_id):
    """Cancel an open order."""
    try:
        from bot.engine.trader import cancel_order
        success = cancel_order(order_id)
        return jsonify({"success": success})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/health")
def health():
    provider = CONFIG.get("data", {}).get("provider", "yfinance")
    trading_enabled = CONFIG.get("trading", {}).get("enabled", False)
    return jsonify({
        "status": "ok",
        "data_provider": provider,
        "trading_enabled": trading_enabled,
    })
