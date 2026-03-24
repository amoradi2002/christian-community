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


@api_bp.route("/options/recommend")
def recommend_options():
    """
    Get options strategy recommendations. ?symbol=AAPL&direction=bullish&confidence=0.8&dte=30
    """
    symbol = request.args.get("symbol", "").upper()
    if not symbol:
        return jsonify({"error": "symbol parameter required"}), 400

    direction = request.args.get("direction", "bullish")
    if direction not in ("bullish", "bearish", "neutral"):
        return jsonify({"error": "direction must be bullish, bearish, or neutral"}), 400

    try:
        from bot.engine.options_strategies import OptionsEngine
        engine = OptionsEngine()
        setups = engine.recommend(
            symbol=symbol,
            direction=direction,
            confidence=float(request.args.get("confidence", 0.7)),
            target_dte=int(request.args.get("dte", 30)),
        )
        return jsonify({
            "symbol": symbol,
            "direction": direction,
            "strategies": [s.to_dict() for s in setups],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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
    Place a stock order with risk management. JSON body:
    {"symbol": "AAPL", "price": 175.50, "side": "buy", "confidence": 0.8}

    If qty is omitted, the risk manager calculates optimal position size.
    If qty is provided, it overrides risk-based sizing.
    """
    trading_cfg = CONFIG.get("trading", {})
    if not trading_cfg.get("enabled", False):
        return jsonify({"error": "Trading is disabled. Set trading.enabled=true in config.yaml"}), 403

    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    symbol = data.get("symbol", "").upper()
    side = data.get("side", "")
    if not symbol or not side:
        return jsonify({"error": "symbol and side are required"}), 400

    try:
        from bot.engine.trader import place_stock_order
        from bot.engine.risk_manager import RiskManager

        rm = RiskManager()
        qty = data.get("qty")

        # If no qty provided, calculate from risk profile
        if qty is None and side.lower() == "buy":
            price = float(data.get("price", data.get("limit_price", 0)))
            if not price:
                return jsonify({"error": "Need price or limit_price for risk-based sizing"}), 400

            sizing = rm.calculate_position_size(
                symbol=symbol,
                price=price,
                confidence=float(data.get("confidence", 0.65)),
            )

            if not sizing["can_trade"]:
                return jsonify({"error": sizing["reason"], "sizing": sizing}), 403

            qty = sizing["shares"]
            # Include risk info in response
            risk_info = sizing
        else:
            qty = float(qty or 1)
            risk_info = None

        result = place_stock_order(
            symbol=symbol,
            qty=qty,
            side=side,
            order_type=data.get("order_type", trading_cfg.get("default_order_type", "market")),
            limit_price=data.get("limit_price"),
            stop_price=data.get("stop_price"),
            time_in_force=data.get("time_in_force", "day"),
        )

        response = result.to_dict()
        if risk_info:
            response["risk_sizing"] = risk_info

        status_code = 200 if result.success else 400
        return jsonify(response), status_code
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
        from bot.engine.risk_manager import RiskManager

        rm = RiskManager()
        side = data["side"].lower()
        qty = int(data["qty"])
        limit_price = data.get("limit_price")

        # Risk check for buying options
        if side == "buy" and limit_price:
            cost_per_contract = float(limit_price) * 100
            total_cost = cost_per_contract * qty
            sizing = rm.calculate_options_size(
                premium_per_contract=float(limit_price),
                confidence=float(data.get("confidence", 0.65)),
            )
            if not sizing["can_trade"]:
                return jsonify({"error": sizing["reason"], "sizing": sizing}), 403
            # Cap qty at what risk manager allows
            qty = min(qty, sizing["contracts"])
            risk_info = sizing
        else:
            risk_info = None

        result = place_option_order(
            contract_symbol=data["contract"],
            qty=qty,
            side=side,
            order_type=data.get("order_type", "limit"),
            limit_price=limit_price,
            time_in_force=data.get("time_in_force", "day"),
        )

        response = result.to_dict()
        if risk_info:
            response["risk_sizing"] = risk_info

        status_code = 200 if result.success else 400
        return jsonify(response), status_code
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


# --- Unusual Whales API ---

@api_bp.route("/flow")
def get_flow():
    """Get unusual options flow. ?ticker=AAPL&min_premium=100000"""
    try:
        from bot.data.unusual_whales import get_options_flow, get_cached_flow
        ticker = request.args.get("ticker")
        min_premium = int(request.args.get("min_premium", 100000))

        try:
            flows = get_options_flow(ticker=ticker, min_premium=min_premium)
        except ValueError:
            flows = get_cached_flow(ticker=ticker)

        return jsonify([f.to_dict() for f in flows])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/flow/alerts")
def get_whale_alerts():
    """Get whale-level flow alerts (>$500k). ?sentiment=bullish"""
    try:
        from bot.data.unusual_whales import get_flow_alerts
        sentiment = request.args.get("sentiment")
        min_premium = int(request.args.get("min_premium", 500000))
        flows = get_flow_alerts(min_premium=min_premium, sentiment=sentiment)
        return jsonify([f.to_dict() for f in flows])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/flow/sentiment")
def get_market_sentiment():
    """Get market-wide flow sentiment."""
    try:
        from bot.data.unusual_whales import get_flow_sentiment
        return jsonify(get_flow_sentiment())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/flow/sentiment/<ticker>")
def get_stock_flow_sentiment(ticker):
    """Get flow sentiment for a specific ticker."""
    try:
        from bot.data.unusual_whales import get_ticker_sentiment
        return jsonify(get_ticker_sentiment(ticker))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/darkpool")
def get_darkpool():
    """Get dark pool trades. ?ticker=AAPL"""
    try:
        from bot.data.unusual_whales import get_dark_pool
        ticker = request.args.get("ticker")
        trades = get_dark_pool(ticker=ticker)
        return jsonify([t.to_dict() for t in trades])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/congress")
def get_congress():
    """Get congressional trades. ?ticker=AAPL&party=Democrat"""
    try:
        from bot.data.unusual_whales import get_congress_trades
        ticker = request.args.get("ticker")
        party = request.args.get("party")
        trades = get_congress_trades(ticker=ticker, party=party)
        return jsonify([t.to_dict() for t in trades])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- Finviz API ---

@api_bp.route("/fundamentals/<symbol>")
def get_fundamentals(symbol):
    """Get stock fundamentals from Finviz."""
    try:
        from bot.data.finviz_provider import get_stock_fundamentals
        data = get_stock_fundamentals(symbol.upper())
        return jsonify(data.to_dict())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/screener")
def run_screener():
    """
    Run Finviz stock screener.
    ?signal=top_gainers or ?signal=oversold or ?signal=unusual_volume
    """
    try:
        from bot.data.finviz_provider import screen_stocks
        signal = request.args.get("signal", "")
        results = screen_stocks(signal=signal)
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/insider")
def get_insider():
    """Get insider trades. ?symbol=AAPL"""
    try:
        from bot.data.finviz_provider import get_insider_trades
        symbol = request.args.get("symbol")
        trades = get_insider_trades(symbol=symbol)
        return jsonify([t.to_dict() for t in trades])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/news")
def get_news():
    """Get market or stock news. ?symbol=AAPL"""
    try:
        symbol = request.args.get("symbol")
        if symbol:
            from bot.data.finviz_provider import get_stock_news
            return jsonify(get_stock_news(symbol.upper()))
        else:
            from bot.data.finviz_provider import get_market_news
            return jsonify(get_market_news())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- Earnings API ---

@api_bp.route("/earnings/calendar")
def earnings_calendar():
    """Get upcoming earnings calendar. ?days=7"""
    try:
        from bot.data.earnings import get_earnings_calendar
        days = int(request.args.get("days", 7))
        events = get_earnings_calendar(days_ahead=days)
        return jsonify([e.to_dict() for e in events])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/earnings/whisper/<symbol>")
def earnings_whisper(symbol):
    """Get whisper number for a stock."""
    try:
        from bot.data.earnings import get_earnings_whisper
        event = get_earnings_whisper(symbol.upper())
        if event:
            return jsonify(event.to_dict())
        return jsonify({"error": f"No whisper data for {symbol}"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/earnings/history/<symbol>")
def earnings_history(symbol):
    """Get past earnings history. ?quarters=8"""
    try:
        from bot.data.earnings import get_earnings_history
        quarters = int(request.args.get("quarters", 8))
        events = get_earnings_history(symbol.upper(), quarters=quarters)
        return jsonify([e.to_dict() for e in events])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/earnings/watchlist")
def earnings_watchlist():
    """Check which watchlist stocks have upcoming earnings. ?days=30"""
    try:
        from bot.data.earnings import get_watchlist_earnings
        watchlist = CONFIG.get("bot", {}).get("watchlist", [])
        days = int(request.args.get("days", 30))
        events = get_watchlist_earnings(watchlist, days_ahead=days)
        return jsonify([e.to_dict() for e in events])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- Profile & Risk Management API ---

@api_bp.route("/profile", methods=["GET"])
def get_profile():
    """Get your trading profile and risk status."""
    try:
        from bot.engine.risk_manager import RiskManager
        rm = RiskManager()
        return jsonify(rm.get_status())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/profile", methods=["POST"])
def update_user_profile():
    """
    Update your trading profile. JSON body with any of:
    {"starting_capital": 1000, "risk_level": "moderate", "risk_per_trade_pct": 2, ...}
    """
    try:
        from bot.engine.risk_manager import update_profile
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON body required"}), 400

        # Whitelist of fields users can update
        allowed = {
            "starting_capital", "current_capital", "risk_per_trade_pct",
            "max_portfolio_pct", "max_open_positions", "risk_level",
            "daily_loss_limit_pct", "weekly_loss_limit_pct",
            "preferred_strategies",
        }
        filtered = {k: v for k, v in data.items() if k in allowed}

        if not filtered:
            return jsonify({"error": f"No valid fields. Allowed: {sorted(allowed)}"}), 400

        # If setting starting capital for first time, also set current and peak
        if "starting_capital" in filtered and "current_capital" not in filtered:
            filtered["current_capital"] = filtered["starting_capital"]
            filtered["peak_capital"] = filtered["starting_capital"]

        profile = update_profile(**filtered)
        return jsonify(profile.to_dict())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/profile/sync", methods=["POST"])
def sync_profile_with_broker():
    """Sync your profile capital with actual Alpaca account balance."""
    try:
        from bot.engine.risk_manager import RiskManager
        rm = RiskManager()
        rm.update_capital_from_broker()
        return jsonify(rm.get_status())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/risk/calculate", methods=["POST"])
def calculate_risk():
    """
    Calculate position size for a trade. JSON body:
    {"symbol": "AAPL", "price": 175.50, "confidence": 0.8}
    """
    try:
        from bot.engine.risk_manager import RiskManager
        rm = RiskManager()
        data = request.get_json()
        if not data or "symbol" not in data or "price" not in data:
            return jsonify({"error": "Need symbol and price"}), 400

        result = rm.calculate_position_size(
            symbol=data["symbol"],
            price=float(data["price"]),
            stop_loss_pct=data.get("stop_loss_pct"),
            confidence=float(data.get("confidence", 0.65)),
        )
        return jsonify(result)
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
